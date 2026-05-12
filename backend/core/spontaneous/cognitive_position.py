"""
认知定位器 — 在发言前回答「此刻我该以什么身份、对什么话题说话」

位于 TriggerPolicy（时机）和 ContentGenerator（内容）之间。
确定性规则覆盖 80% 场景，只在多信号冲突时调子LLM。

输出 CognitiveFrame → ContentGenerator 的 prompt 定位指令。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any


class CognitiveMode(Enum):
    CONVERSING = "conversing"        # 回应用户，锚点=用户刚说的话
    OBSERVING = "observing"          # 观察画面变化，锚点=当前VLM描述
    IDLE_COMMENT = "idle_comment"    # 冷场打破，锚点=当前画面/时间
    SILENT = "silent"                # 不说话（没理由/深夜/被禁止）


@dataclass
class CognitiveFrame:
    mode: CognitiveMode
    anchor: str = ""             # 「我应该围绕什么说话」— 给 ContentGenerator 的核心提示
    confidence: float = 0.5      # 0-1
    forbidden: List[str] = field(default_factory=list)  # 禁止提及的话题关键词
    max_turns: int = 1           # 建议最多说几句
    reason: str = ""             # 决策原因（日志用）

    def to_prompt_hint(self) -> str:
        """生成注入到 ContentGenerator prompt 中的定位指令"""
        mode_hints = {
            CognitiveMode.CONVERSING: "你在和用户对话，直接回应他说的话。",
            CognitiveMode.OBSERVING: "你在观察用户屏幕上的画面变化，评论你看到的。画面是唯一的信息来源。",
            CognitiveMode.IDLE_COMMENT: "用户沉默了很久，你可以轻声说一句打破冷场，但要基于当前画面。",
            CognitiveMode.SILENT: "（不应该说话）",
        }
        lines = [f"【认知定位】", f"模式: {mode_hints.get(self.mode, '')}"]
        if self.anchor:
            lines.append(f"锚点: {self.anchor}")
        if self.forbidden:
            lines.append(f"禁止提及: {', '.join(self.forbidden)}")
        if self.max_turns > 1:
            lines.append(f"最多说 {self.max_turns} 句")
        return "\n".join(lines)


# ── 确定性规则 ──

_SILENCE_COMMANDS = ["闭嘴", "别说话", "别吵", "安静点", "别烦", "烦死了", "别说了", "消停", "吵死了"]

_TOPIC_SHIFT_MARKERS = ["不说这个", "换个话题", "算了", "别管", "你看", "看这个", "这是什么", "那个是什么"]


class CognitivePosition:
    """认知定位器。轻量级，可无 LLM 运行（确定性规则兜底）。"""

    def __init__(self, llm=None):
        self._llm = llm
        self._last_mode: Optional[CognitiveMode] = None
        self._mode_streak: int = 0
        self._forbidden_topics: List[str] = []  # 全局禁止

    # ── 公共 API ──

    def locate(
        self,
        *,
        user_just_spoke: bool = False,
        user_text: str = "",
        visual_changed: bool = False,
        visual_description: str = "",
        silence_seconds: float = 0,
        has_goal: bool = False,
        goal_text: str = "",
        internal_events: Optional[List] = None,
        short_term_count: int = 0,
        hour: int = 12,
    ) -> CognitiveFrame:
        """主入口：确定当前认知定位。规则优先级从高到低。"""

        # 0. 用户要求静默 → 绝对服从
        if any(cmd in user_text for cmd in _SILENCE_COMMANDS):
            self._forbid_forever(user_text)
            return self._make(CognitiveMode.SILENT, reason="用户要求静默")

        # 1. 用户刚说话 → conversing 优先
        if user_just_spoke and user_text.strip():
            forbidden = list(self._forbidden_topics)
            if self._is_topic_shift(user_text):
                forbidden = []
            return self._make(
                CognitiveMode.CONVERSING,
                anchor=user_text[:120],
                confidence=0.95,
                forbidden=forbidden,
                max_turns=3,
                reason="回应用户",
            )

        # 2. 深夜 → 静默
        if 2 <= hour < 5:
            return self._make(CognitiveMode.SILENT, reason="深夜不打扰")

        # 3. 连续观察发言已达上限 → 暂停一轮后重置
        if self._mode_streak >= 3 and self._last_mode == CognitiveMode.OBSERVING:
            self._mode_streak = 0  # 重置，下一轮恢复
            return self._make(CognitiveMode.SILENT, reason="连续观察发言已达上限，暂停一轮")

        # 4. 画面变化 + 有描述 → observing
        if visual_changed and visual_description:
            return self._make(
                CognitiveMode.OBSERVING,
                anchor=visual_description,
                confidence=0.85,
                forbidden=list(self._forbidden_topics),
                max_turns=1,
                reason="画面变化，观察优先",
            )

        # 5. 长时间沉默 + 有画面 → idle_comment（轻量）
        if silence_seconds > 300 and visual_description:
            return self._make(
                CognitiveMode.IDLE_COMMENT,
                anchor=visual_description,
                confidence=0.7,
                forbidden=list(self._forbidden_topics),
                max_turns=1,
                reason=f"沉默 {silence_seconds/60:.0f} 分钟，轻量评论",
            )

        # 6. 多信号冲突 → 子 LLM
        signals = sum([user_just_spoke, visual_changed, has_goal])
        if signals >= 2:
            return self._llm_judge(
                user_text=user_text,
                visual_description=visual_description,
                silence_seconds=silence_seconds,
                goal_text=goal_text,
                events=internal_events or [],
            )

        # 默认：没理由就不说
        return self._make(CognitiveMode.SILENT, reason="无触发信号")

    def update_streak(self, mode: CognitiveMode):
        """发言后更新连续计数"""
        if mode == self._last_mode:
            self._mode_streak += 1
        else:
            self._mode_streak = 1
        self._last_mode = mode

    def forbid_topic(self, topic: str):
        """临时禁止某个话题（如用户说'别提那个了'）"""
        self._forbidden_topics.append(topic)
        if len(self._forbidden_topics) > 5:
            self._forbidden_topics.pop(0)

    # ── 内部 ──

    def _make(self, mode: CognitiveMode, **kwargs) -> CognitiveFrame:
        return CognitiveFrame(mode=mode, **kwargs)

    def _is_topic_shift(self, text: str) -> bool:
        return any(m in text for m in _TOPIC_SHIFT_MARKERS)

    def _forbid_forever(self, text: str):
        # 用户说了"闭嘴"，长期静默交给 SilenceGate 处理
        pass

    def _llm_judge(
        self,
        user_text: str = "",
        visual_description: str = "",
        silence_seconds: float = 0,
        goal_text: str = "",
        events: Optional[List] = None,
    ) -> CognitiveFrame:
        """子LLM判断多信号冲突时的优先级"""
        if not self._llm:
            # 无LLM：保守策略 — 用户 > 画面 > 目标
            if user_text.strip():
                return self._make(
                    CognitiveMode.CONVERSING, anchor=user_text[:120],
                    confidence=0.6, reason="冲突-保守回应用户",
                )
            if visual_description:
                return self._make(
                    CognitiveMode.OBSERVING, anchor=visual_description,
                    confidence=0.6, reason="冲突-保守观察画面",
                )
            return self._make(CognitiveMode.SILENT, reason="冲突-无LLM保守静默")

        events_text = ""
        if events:
            events_text = "\n".join(
                f"- [{e.type}] 强度={e.strength:.1f} {e.summary}" for e in events[-5:]
            )

        prompt = COGNITIVE_JUDGE_PROMPT.format(
            user_text=user_text[:100] or "（用户没说话）",
            visual=visual_description[:120] or "（无画面描述）",
            silence=f"{silence_seconds:.0f}秒",
            goal=goal_text[:80] or "（无目标）",
            events=events_text or "（无内部事件）",
        )

        try:
            result = self._llm.ask_with_system(
                COGNITIVE_JUDGE_SYSTEM, prompt, temperature=0.1
            )
            if result:
                return self._parse_llm_result(result)
        except Exception as e:
            print(f"[CognitivePosition] LLM判断失败: {e}")

        return self._make(CognitiveMode.SILENT, reason="LLM判断失败，静默")

    def _parse_llm_result(self, text: str) -> CognitiveFrame:
        """解析子LLM的JSON输出"""
        import json
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:]) if len(lines) > 1 else text
            if text.endswith("```"):
                text = text[:-3]
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return self._make(CognitiveMode.SILENT, reason="LLM输出解析失败")

        mode_str = data.get("mode", "silent")
        try:
            mode = CognitiveMode(mode_str)
        except ValueError:
            mode = CognitiveMode.SILENT

        return CognitiveFrame(
            mode=mode,
            anchor=data.get("anchor", ""),
            confidence=float(data.get("confidence", 0.5)),
            forbidden=data.get("forbidden", []),
            max_turns=int(data.get("max_turns", 1)),
            reason=data.get("reason", ""),
        )


# ── 子LLM提示词 ──

COGNITIVE_JUDGE_SYSTEM = """你是 yume 的认知定位模块。多个信号同时触发时，你需要判断此刻应该以什么身份说话。

输出纯JSON（不要markdown）：
{"mode": "conversing|observing|idle_comment|silent", "anchor": "围绕什么说话（≤60字）", "confidence": 0.0~1.0, "forbidden": ["禁止提及的关键词"], "max_turns": 1, "reason": "≤15字"}

优先级原则：
- 用户刚说的话 > 画面变化 > 内部目标
- 如果用户转移了话题，放弃旧画面
- 如果画面显示的是全新的活动，别再提旧话题
- 不确定时选 silent"""

COGNITIVE_JUDGE_PROMPT = """判断 yume 此刻应该以什么身份说话：

用户刚说: {user_text}
当前画面: {visual}
沉默时长: {silence}
活跃目标: {goal}
内部事件: {events}

输出JSON决策。"""
