"""
群聊回复决策器 — 双态 + 双阈值 + 退出条件 + 冷却/预算

IDLE → 高阈值(0.65)，长冷却(15s)，不主动搭话
ENGAGED → 低阈值(0.45)，短冷却(5s)，持续追踪对话

硬规则（@、指令、唤醒词）强制进入 ENGAGED，高分搭话也可拉入 ENGAGED。

零外部依赖（无 embedding、无 LLM），纯启发式判断。
"""

from dataclasses import dataclass, field
from collections import defaultdict, deque
from enum import Enum
import hashlib
import logging
import random
import time

logger = logging.getLogger(__name__)

# ── 唤醒词 ──
_WAKE_WORDS = ["小梦", "梦梦", "yume", "梦酱", "小梦梦"]

# ── 指令前缀 ──
_COMMAND_PREFIXES = ("/", "#")

# ── 问句标记 ──
_QUESTION_MARKS = "吗呢？?？"

# ── 强对话信号（有人想跟 bot 聊，应该降低门槛） ──
_ENGAGEMENT_SIGNALS = [
    "有人吗", "在吗", "在不在", "人呢", "怎么不", "回答", "回应",
    "说话", "出来", "理我", "回我", "看看我", "hello", "hi",
    "有ai吗", "有AI吗", "ai在吗", "bot在吗", "机器人",
    # 扩展：覆盖更多口语化呼叫
    "还在否", "还在吗", "在不在啊", "在不在呀",
    "回复一下", "回一下", "回个话", "说句话", "冒个泡",
    "出来聊天", "出来说话", "出来玩", "快来",
    "听见没", "听到没", "看到没", "看见没",
    "说话啊", "说话呀", "理我一下",
    "你在哪", "你在哪里", "你在不在",
    "回来", "复活", "活了没", "掉线了",
    "叫你", "喊你", "找你",
    "聊会", "聊会儿", "陪聊",
]

# ── 话题锚点词 ──
_TOPIC_HOOKS = [
    "ai", "AI", "机器人", "bot", "直播", "开播", "代码", "游戏",
    "猫耳", "猫娘", "yume", "梦", "虚拟", "live2d", "模型",
    "程序", "bug", "debug", "测试", "记忆", "日记",
]


class GroupStateEnum(Enum):
    IDLE = "idle"
    ENGAGED = "engaged"


@dataclass
class GroupState:
    """单个群的运行时状态"""
    mode: GroupStateEnum = GroupStateEnum.IDLE
    engaged_at: float = 0.0
    last_ai_reply_time: float = 0.0
    consecutive_replies: int = 0
    forced_entry: bool = False  # 是否由 @/指令/唤醒词 强制进入

    # ── 评分追踪 ──
    low_relevance_count: int = 0
    last_msg_texts: deque = field(default_factory=lambda: deque(maxlen=5))
    last_msg_scores: deque = field(default_factory=lambda: deque(maxlen=5))

    # ── bot 自身发言追踪（用于话题相关性） ──
    bot_recent_replies: deque = field(default_factory=lambda: deque(maxlen=3))
    bot_topic_words: deque = field(default_factory=lambda: deque(maxlen=30))

    # ── 探头追踪（同一用户反复试探 → 自动拉回 ENGAGED） ──
    last_prober_id: str = ""
    probe_count: int = 0
    probe_window_start: float = 0.0
    just_probe_reengaged: bool = False  # 本轮刚被探头拉回，允许跳过一次冷却
    cooldown_bypass_next: bool = False  # 强制回应后允许下一条跟进消息跳过冷却

    # ── 群聊上下文（存储所有观测到的消息，包括未回复的）──
    group_context: deque = field(default_factory=lambda: deque(maxlen=10))

    # ── 频控 ──
    hourly_reply_times: list = field(default_factory=list)
    message_times: list = field(default_factory=list)
    last_msg_hash: str = ""
    last_msg_time: float = 0.0

    # ── 属性 ──

    @property
    def activity_count(self) -> int:
        """最近 30 秒内消息数"""
        cutoff = time.time() - 30
        self.message_times = [t for t in self.message_times if t > cutoff]
        return len(self.message_times)

    @property
    def hourly_count(self) -> int:
        """最近一小时内回复数"""
        cutoff = time.time() - 3600
        self.hourly_reply_times = [t for t in self.hourly_reply_times if t > cutoff]
        return len(self.hourly_reply_times)


class GroupResponseDecider:
    """群聊回复决策器 — 双态 + 双阈值 + 退出条件 + LLM灰区判断"""

    # 极轻量 LLM 判断 prompt（评估是否回应 + 是否退出）
    _LLM_JUDGE_SYSTEM = (
        "你是群聊对话评估。yume(白色长发猫耳AI)在群里。"
        "给你最近的群聊上下文和当前消息，判断：yume应该出声回应吗？"
        "规则："
        "1. 如果消息明显是跟别人说的（@别人、回复别人的话题），不要回应"
        "2. 如果消息是跟yume说或提到yume相关话题，应该回应"
        "3. 如果群里在闲聊且消息有趣/可以接话，可以回应"
        "4. 如果只是表情包、单字、无意义的短句，不要回应"
        "只输出JSON，不要其他内容：{\"respond\": true/false, \"exit\": true/false}"
    )

    def __init__(
        self,
        self_id: str = "1910867718",
        wake_words: list | None = None,
        llm=None,  # 可选 LLM，用于灰区语义判断
        # 阈值
        idle_threshold: float = 0.65,
        engaged_threshold: float = 0.45,
        # 退出条件
        exit_low_score_threshold: float = 0.35,
        exit_low_score_count: int = 3,
        exit_silence_timeout: float = 120.0,
        max_consecutive_turns: int = 5,
        # 冷却
        cooldown_idle: float = 15.0,
        cooldown_idle_jitter: float = 8.0,
        cooldown_engaged: float = 3.0,
        cooldown_engaged_jitter: float = 2.0,
        # 预算（IDLE 限频严格，ENGAGED 宽松）
        max_replies_per_hour: int = 8,
        max_replies_per_hour_engaged: int = 20,
    ):
        self._self_id = self_id
        self._wake_words = wake_words or _WAKE_WORDS
        self._llm = llm  # 可选：灰区语义判断

        # 阈值
        self._idle_threshold = idle_threshold
        self._engaged_threshold = engaged_threshold

        # 退出
        self._exit_low_threshold = exit_low_score_threshold
        self._exit_low_count = exit_low_score_count
        self._exit_silence = exit_silence_timeout
        self._max_turns = max_consecutive_turns

        # 冷却
        self._cooldown_idle = cooldown_idle
        self._cooldown_idle_jitter = cooldown_idle_jitter
        self._cooldown_engaged = cooldown_engaged
        self._cooldown_engaged_jitter = cooldown_engaged_jitter

        # 预算
        self._max_per_hour_idle = max_replies_per_hour
        self._max_per_hour_engaged = max_replies_per_hour_engaged

        self._states: dict[str, GroupState] = defaultdict(GroupState)

    # ── 公共 API ──

    def observe(self, group_id: str, message: str, sender: str = ""):
        """每条群消息都调用，维护活动窗口 + 群聊上下文"""
        now = time.time()
        state = self._states[group_id]
        state.message_times.append(now)
        # 清理 30s 外的旧记录
        cutoff = now - 30
        state.message_times = [t for t in state.message_times if t > cutoff]
        # 存入群聊上下文（LLM 评估 + 回复时可用）
        if message.strip():
            state.group_context.append({
                "sender": sender or "群友",
                "text": message.strip()[:120],
                "time": now,
            })

    def should_respond(self, group_id: str, user_id: str, message: str) -> tuple[bool, str]:
        """返回 (是否回复, 原因标签)"""
        state = self._states[group_id]
        msg = message.strip()

        # ── 第1层：硬规则（强制通过，进入 ENGAGED） ──
        forced = False
        reason = ""

        if self._is_at_me(message):
            forced, reason = True, "at_bot"
        elif self._is_command(msg):
            forced, reason = True, "command"
        elif self._is_wake_word(msg):
            forced, reason = True, "wake_word"

        if forced:
            if self._is_duplicate(state, self._hash_msg(group_id, message)):
                return False, "duplicate_at"
            state.last_msg_hash = self._hash_msg(group_id, message)
            state.last_msg_time = time.time()
            state.cooldown_bypass_next = True  # 下一条跟进消息跳过冷却
            self._enter_engaged(state, forced_entry=True)
            return True, reason

        # ── 第2层：退出检查（ENGAGED 下先判断是否该退出） ──
        if state.mode == GroupStateEnum.ENGAGED and self._should_exit(state):
            self._exit_engaged(state)

        # ── 第2.5层：探头重入检测（同用户反复试探 → 拉回 ENGAGED） ──
        if state.mode == GroupStateEnum.IDLE:
            if self._detect_persistent_prober(state, user_id, msg):
                self._enter_engaged(state, forced_entry=False)
                state.just_probe_reengaged = True

        threshold = self._engaged_threshold if state.mode == GroupStateEnum.ENGAGED else self._idle_threshold

        # ── 第3层：冷却/预算检查 ──
        if not self._check_cooldown(state):
            # 探头重入允许跳过一次冷却（用户明显在等回复，且已有频控保护）
            if state.just_probe_reengaged:
                state.just_probe_reengaged = False
            else:
                return False, "cooldown"

        if not self._check_budget(state):
            return False, "budget_exceeded"

        # ── 第4层：评分 ──
        score = self._calculate_score(state, user_id, msg)
        state.last_msg_texts.append(msg)
        state.last_msg_scores.append(score)

        # ENGAGED 下更新低分计数
        if state.mode == GroupStateEnum.ENGAGED:
            if score < self._exit_low_threshold:
                state.low_relevance_count += 1
            else:
                state.low_relevance_count = 0

        # ── 第4.5层：LLM 判定已合并到管线（judge+reply 一次调用）──
        # 启发式评分过线 → 进入管线，由 LLM 根据群聊上下文决定是否出声
        if score >= threshold:
            if state.mode == GroupStateEnum.IDLE:
                self._enter_engaged(state, forced_entry=False)
            return True, f"score_{score:.2f}"

        return False, f"low_{score:.2f}"

    def on_bot_reply(self, group_id: str, reply_text: str):
        """bot 回复后调用：更新轮次、冷却、话题缓存"""
        now = time.time()
        state = self._states[group_id]
        state.last_ai_reply_time = now
        state.hourly_reply_times.append(now)

        if state.mode == GroupStateEnum.ENGAGED:
            state.consecutive_replies += 1

        # 回复后重置探头状态（对方被回应了，下一轮从头计）
        state.probe_count = 0
        state.last_prober_id = ""
        state.just_probe_reengaged = False

        # 缓存 bot 发言（用于后续相关性评分）
        state.bot_recent_replies.append(reply_text[:120])
        for word in _TOPIC_HOOKS:
            if word.lower() in reply_text.lower():
                state.bot_topic_words.append(word)

    # ── 群聊上下文 ──

    def get_group_context(self, group_id: str, limit: int = 8) -> str:
        """获取最近 N 条群聊消息（含发送者），供 LLM 评估和回复时使用"""
        state = self._states[group_id]
        if not state.group_context:
            return "（暂无群聊上下文）"
        entries = list(state.group_context)[-limit:]
        lines = []
        for e in entries:
            lines.append(f"{e['sender']}: {e['text'][:100]}")
        # 高亮 bot 最近发言，帮助 LLM 锚定上下文（"怎么样"等指代词能关联到刚聊的内容）
        if state.bot_recent_replies:
            last_reply = state.bot_recent_replies[-1][:100]
            lines.append(f"[你刚才说：{last_reply}]")
        return "\n".join(lines)

    # ── 状态机 ──

    def _enter_engaged(self, state: GroupState, forced_entry: bool):
        """进入 ENGAGED 状态"""
        state.mode = GroupStateEnum.ENGAGED
        state.engaged_at = time.time()
        state.consecutive_replies = 0
        state.low_relevance_count = 0
        state.forced_entry = forced_entry
        logger.debug("[Decider] → ENGAGED (forced=%s)", forced_entry)

    def _exit_engaged(self, state: GroupState):
        """退出 ENGAGED"""
        state.mode = GroupStateEnum.IDLE
        state.low_relevance_count = 0
        state.consecutive_replies = 0
        state.forced_entry = False
        state.cooldown_bypass_next = False
        logger.debug("[Decider] → IDLE")

    def _should_exit(self, state: GroupState) -> bool:
        """ENGAGED 退出条件检查"""
        if state.consecutive_replies >= self._max_turns:
            logger.debug("[Decider] exit: max_turns=%d", state.consecutive_replies)
            return True
        if state.low_relevance_count >= self._exit_low_count:
            logger.debug("[Decider] exit: low_relevance=%d", state.low_relevance_count)
            return True
        if state.last_ai_reply_time > 0:
            if time.time() - state.last_ai_reply_time > self._exit_silence:
                logger.debug("[Decider] exit: silence=%.0fs", time.time() - state.last_ai_reply_time)
                return True
        return False

    # ── LLM 灰区判断 ──

    def _llm_judge_sync(self, state: GroupState, current_msg: str, group_id: str = "") -> dict | None:
        """同步 LLM 判断：这条消息值得回应吗？返回 {'respond': bool, 'exit': bool} 或 None"""
        if not self._llm:
            return None

        # 组装对话上下文：群聊上下文 + bot 发言 + 当前消息
        lines = []
        if group_id:
            group_ctx = self._states[group_id].group_context
            recent = list(group_ctx)[-8:]
            lines.append("【最近群聊记录】")
            for e in recent:
                lines.append(f"{e['sender']}: {e['text'][:100]}")
        else:
            for msg in list(state.last_msg_texts)[-4:]:
                lines.append(f"群友: {msg[:80]}")
        lines.append("")
        lines.append("【当前要判断的消息】")
        lines.append(f">>> {current_msg[:150]}")

        prompt = "\n".join(lines)

        try:
            raw = self._llm.ask_with_system(
                self._LLM_JUDGE_SYSTEM, prompt, temperature=0.0
            )
            if not raw:
                return None
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
            if raw.endswith("```"):
                raw = raw[:-3]
            import json
            data = json.loads(raw)
            return {"respond": bool(data.get("respond")), "exit": bool(data.get("exit"))}
        except Exception:
            return None

    # ── 硬规则检测 ──

    def _is_at_me(self, message: str) -> bool:
        return f"[CQ:at,qq={self._self_id}]" in message

    def _is_command(self, message: str) -> bool:
        return message.startswith(_COMMAND_PREFIXES)

    def _is_wake_word(self, message: str) -> bool:
        return any(w in message for w in self._wake_words)

    def _is_engagement_signal(self, message: str) -> bool:
        """检测强对话信号（有人想跟 bot 聊）"""
        return any(s in message for s in _ENGAGEMENT_SIGNALS)

    def _detect_persistent_prober(self, state: GroupState, user_id: str, message: str) -> bool:
        """同一用户 60s 内 ≥2 条对话信号消息 → 自动重入 ENGAGED"""
        now = time.time()
        msg_clean = message.strip()

        # 重置条件：不同用户 或 窗口过期
        if user_id != state.last_prober_id or (now - state.probe_window_start) > 60:
            state.last_prober_id = user_id
            state.probe_count = 0
            state.probe_window_start = now

        # 只统计对话信号消息
        if self._is_engagement_signal(msg_clean) or self._is_wake_word(msg_clean):
            state.probe_count += 1
        else:
            # 非信号消息不计数但不重置（可能是正常聊天夹带了其他内容）
            pass

        return state.probe_count >= 2

    # ── 频控 ──

    def _check_cooldown(self, state: GroupState) -> bool:
        if state.last_ai_reply_time == 0:
            return True
        if state.cooldown_bypass_next:
            state.cooldown_bypass_next = False
            logger.debug("[Decider] cooldown bypass (after forced response)")
            return True
        if state.mode == GroupStateEnum.ENGAGED:
            cd = self._cooldown_engaged + random.random() * self._cooldown_engaged_jitter
        else:
            cd = self._cooldown_idle + random.random() * self._cooldown_idle_jitter
        return (time.time() - state.last_ai_reply_time) >= cd

    def _check_budget(self, state: GroupState) -> bool:
        limit = self._max_per_hour_engaged if state.mode == GroupStateEnum.ENGAGED else self._max_per_hour_idle
        return state.hourly_count < limit

    def _is_duplicate(self, state: GroupState, msg_hash: str) -> bool:
        if msg_hash == state.last_msg_hash:
            return (time.time() - state.last_msg_time) < 2.0
        return False

    # ── 评分（四维加权） ──

    def _calculate_score(self, state: GroupState, user_id: str, message: str) -> float:
        rel = self._relevance_score(message, state)       # 权重 0.40
        ctx = self._context_score(message, state)          # 权重 0.30
        role = self._role_score(state)                     # 权重 0.20
        hist = 0.5                                         # 权重 0.10（Phase 2）
        return round(rel * 0.40 + ctx * 0.30 + role * 0.20 + hist * 0.10, 3)

    def _relevance_score(self, message: str, state: GroupState) -> float:
        """话题相关性：消息与 bot 近期发言的关键词重叠"""
        if not state.bot_topic_words and not state.bot_recent_replies:
            return 0.30

        msg_lower = message.lower()

        # 关键词命中
        topic_hits = sum(1 for w in state.bot_topic_words if w.lower() in msg_lower)

        # 子串匹配（bot 最近发言中的短词出现在消息里）
        substring_bonus = 0.0
        for reply in state.bot_recent_replies:
            reply_lower = reply.lower()
            # 从 bot 发言中取 ≥4 字片段，检查是否出现在消息中
            for i in range(len(reply_lower) - 3):
                chunk = reply_lower[i:i + 4]
                if chunk in msg_lower and chunk.strip():
                    substring_bonus = max(substring_bonus, 0.15)
                    break
            if substring_bonus > 0:
                break

        if topic_hits >= 3:
            return 0.90
        if topic_hits >= 2:
            return 0.75 + substring_bonus
        if topic_hits >= 1:
            return 0.55 + substring_bonus
        if substring_bonus > 0:
            return 0.40
        return 0.20

    def _context_score(self, message: str, state: GroupState) -> float:
        """语境合适度：对话信号加分 + 长度惩罚 + 活跃度惩罚 + 近接奖励"""
        score = 0.50

        # 强对话信号（"有人吗"/"回答我"等）→ 大幅加分
        if self._is_engagement_signal(message):
            score += 0.35
        elif any(c in message for c in _QUESTION_MARKS):
            score += 0.25

        # 近接奖励：bot 刚回复过，有人接话 ≈ 在跟 bot 说话
        if state.last_ai_reply_time > 0:
            elapsed = time.time() - state.last_ai_reply_time
            if elapsed < 30:
                score += 0.20

        # 长度：太短或太长都降分
        length = len(message)
        if length < 4:
            score -= 0.20
        elif length > 60:
            score -= 0.10

        # 活跃度：刷屏降分
        n = state.activity_count
        if n > 5:
            score -= 0.20
        elif n > 3:
            score -= 0.05

        return max(0.0, min(1.0, score))

    def _role_score(self, state: GroupState) -> float:
        """角色定位：ENGAGED 时更愿意多说"""
        if state.mode == GroupStateEnum.ENGAGED:
            return 0.85 if state.forced_entry else 0.70
        return 0.45

    # ── 工具 ──

    @staticmethod
    def _hash_msg(group_id: str, message: str) -> str:
        return hashlib.md5(f"{group_id}:{message}".encode()).hexdigest()
