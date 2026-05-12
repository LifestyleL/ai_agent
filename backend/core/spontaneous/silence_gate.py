"""
SilenceGate: 语境门控，判断此刻是否适合主动说话
- 快速规则（零成本关键词/时间检测）
- 子LLM模糊判断（仅在规则无法判定时调用）
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any


class Decision(Enum):
    SPEAK = "speak"              # 可以说话
    WAIT = "wait"                # 暂不合适，延长检查间隔
    SILENCE = "silence"          # 短期静默，本次跳过
    SILENCE_LONG = "silence_long"  # 长期静默，直到用户说话


@dataclass
class SilenceResult:
    decision: Decision
    reason: str = ""
    confidence: float = 1.0
    wait_seconds: int = 0  # WAIT 时建议的等待秒数


@dataclass
class InternalEvent:
    """自驱动引擎内部事件"""
    type: str         # card_created / goal_updated / emotion_shift / hobby_keyword / topic_exhausted
    strength: float   # 0.0~1.0 信号强度
    summary: str = ""  # 事件简述
    data: Dict[str, Any] = field(default_factory=dict)


# ── 快速规则：关键词 ──

_SILENCE_LONG_PATTERNS = [
    re.compile(r'闭嘴'),
    re.compile(r'别说话'),
    re.compile(r'别吵'),
    re.compile(r'安静点'),
    re.compile(r'别烦我'),
    re.compile(r'烦死了'),
    re.compile(r'别说了'),
    re.compile(r'消停'),
    re.compile(r'吵死了'),
]

_RESUME_PATTERNS = [
    re.compile(r'可以说话了'),
    re.compile(r'继续'),
    re.compile(r'恢复'),
    re.compile(r'说话吧'),
    re.compile(r'你怎么不说话'),
    re.compile(r'怎么不说话了'),
    re.compile(r'在吗'),
    re.compile(r'理我'),
]

_SHORT_REPLY_PATTERNS = [
    re.compile(r'^[嗯哦好行对]$'),
    re.compile(r'^[嗯哦好行对]吧?[。！]?$'),
    re.compile(r'^知道了?[。！]?$'),
]


def detect_silence_long(text: str) -> bool:
    """检测用户是否在让 yume 闭嘴"""
    for pat in _SILENCE_LONG_PATTERNS:
        if pat.search(text):
            return True
    return False


def detect_resume(text: str) -> bool:
    """检测用户是否在让 yume 恢复说话"""
    for pat in _RESUME_PATTERNS:
        if pat.search(text):
            return True
    return False


def detect_short_reply(text: str) -> bool:
    """检测是否为极短回复（表示话题枯竭）"""
    text = text.strip()
    if len(text) > 3:
        return False
    for pat in _SHORT_REPLY_PATTERNS:
        if pat.search(text):
            return True
    return False


# ── SilenceGate ──


class SilenceGate:
    """语境门控：快速规则 + 子LLM 双重判断"""

    def __init__(self, llm=None, short_term_provider=None):
        self._llm = llm
        self._short_term = short_term_provider  # callable → List[dict]
        self._silence_until: float = 0.0  # 长期静默截止时间戳
        self._short_reply_count: int = 0  # 连续短回复计数
        self._last_user_input_time: float = 0.0
        self._user_input_burst: int = 0  # 短时间内输入计数
        self._llm_call_count: int = 0

    # ── 公共 API ──

    def on_user_activity(self, text: str = ""):
        """用户活动时调用：检测关键词，更新状态"""
        now = time.time()

        # 检测静默长命令
        if detect_silence_long(text):
            self._silence_until = now + 3600 * 24  # 24小时
            print(f"[SilenceGate] 检测到静默长命令，静默至 {time.ctime(self._silence_until)}")

        # 检测恢复命令
        if detect_resume(text):
            if self._silence_until > 0:
                print(f"[SilenceGate] 检测到恢复命令，解除静默")
            self._silence_until = 0.0
            self._short_reply_count = 0

        # 检测短回复（话题枯竭）
        if detect_short_reply(text):
            self._short_reply_count += 1
        else:
            self._short_reply_count = 0

        # 检测密集输入
        if now - self._last_user_input_time < 10:
            self._user_input_burst += 1
        else:
            self._user_input_burst = 0
        self._last_user_input_time = now

    def check(self, events: List[InternalEvent],
              silence_duration: float = 0.0,
              short_term_count: int = 0,
              emotion_type: int = 0,
              hour: int = 12) -> SilenceResult:
        """
        主判断入口。
        events: 本轮内部事件列表
        返回 SilenceResult
        """
        now = time.time()

        # ── 0. 长期静默 ──
        if self._silence_until > 0 and now < self._silence_until:
            return SilenceResult(Decision.SILENCE_LONG, "处于长期静默期")

        # ── 1. 快速规则 ──

        # 深夜抑制 (凌晨 2-5 点)
        if 2 <= hour < 5:
            return SilenceResult(Decision.SILENCE, "凌晨时段不打扰")

        # 密集操作中
        if self._user_input_burst >= 3:
            return SilenceResult(Decision.WAIT, "用户正在密集操作", wait_seconds=60)

        # 话题枯竭
        if self._short_reply_count >= 3:
            return SilenceResult(Decision.SILENCE, f"连续{self._short_reply_count}轮短回复，话题已枯竭")

        # 用户刚说过话
        if silence_duration < 30 and short_term_count < 3:
            return SilenceResult(Decision.WAIT, f"沉默仅{silence_duration:.0f}s，且对话不足", wait_seconds=30)

        # ── 2. 无事件则不触发 ──
        if not events:
            return SilenceResult(Decision.SILENCE, "无内部事件驱动")

        # ── 3. 子LLM模糊判断（有事件但规则无法判定时）──
        if self._llm and self._should_call_llm(events):
            return self._llm_check(events, silence_duration, emotion_type)

        # 默认：有事件 → 允许
        return SilenceResult(Decision.SPEAK, f"事件驱动: {events[0].type}")

    # ── 内部 ──

    def _should_call_llm(self, events: List[InternalEvent]) -> bool:
        """判断是否需要调用子LLM：仅在事件强度不高、可能存在歧义时"""
        # 每3次最多调用1次LLM（节流）
        self._llm_call_count += 1
        if self._llm_call_count % 3 != 0:
            return False
        # 有高强度事件时跳过LLM，直接允许
        if any(e.strength >= 0.7 for e in events):
            return False
        # 长时间沉默本身就是充分的发言理由，不需要 LLM 二次判断
        if any(e.type == "prolonged_silence" for e in events):
            return False
        return True

    def _llm_check(self, events: List[InternalEvent],
                   silence_duration: float, emotion_type: int) -> SilenceResult:
        """调用子LLM做模糊判断"""
        try:
            context_text = ""
            if self._short_term:
                try:
                    history = self._short_term()
                    if history:
                        turns = [f"{d.get('role', '?')}: {d.get('content', '')[:80]}"
                                 for d in history[-6:]]
                        context_text = "\n".join(turns)
                except Exception:
                    pass

            events_text = "\n".join(
                f"- [{e.type}] 强度={e.strength:.1f} {e.summary}" for e in events
            )

            prompt = SILENCE_GATE_PROMPT.format(
                context=context_text or "（暂无对话）",
                events=events_text,
                silence=f"{silence_duration:.0f}秒",
                emotion=str(emotion_type),
            )

            print(f"\n{'='*60}")
            print(f"[SilenceGate] LLM 提示词 (语境门控):")
            print(f"  system: {SILENCE_GATE_SYSTEM[:100]}...")
            print(f"  prompt:\n{prompt}")
            print(f"{'='*60}\n")
            result_text = self._llm.ask_with_system(
                SILENCE_GATE_SYSTEM, prompt, temperature=0.1
            )

            if result_text:
                parsed = self._parse_response(result_text)
                if parsed:
                    return parsed

        except Exception as e:
            print(f"[SilenceGate] LLM 判断失败: {e}")

        # LLM 失败时保守策略：有事件 → 允许
        return SilenceResult(Decision.SPEAK, "LLM判断失败，保守允许")

    def _parse_response(self, text: str) -> Optional[SilenceResult]:
        """解析子LLM返回的JSON"""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:]) if len(lines) > 1 else text
            if text.endswith("```"):
                text = text[:-3]
        try:
            data = json.loads(text)
            decision_str = data.get("decision", "speak")
            try:
                decision = Decision(decision_str)
            except ValueError:
                decision = Decision.SPEAK
            return SilenceResult(
                decision=decision,
                reason=data.get("reason", ""),
                confidence=float(data.get("confidence", 0.5)),
                wait_seconds=int(data.get("wait_seconds", 30)),
            )
        except (json.JSONDecodeError, AttributeError):
            print(f"[SilenceGate] JSON 解析失败: {text[:100]}...")
            return None

    def get_status(self) -> Dict[str, Any]:
        now = time.time()
        return {
            "in_long_silence": self._silence_until > now,
            "silence_remaining": max(0, self._silence_until - now) if self._silence_until > now else 0,
            "short_reply_count": self._short_reply_count,
            "user_input_burst": self._user_input_burst,
            "llm_call_count": self._llm_call_count,
        }


# ── 子LLM提示词 ──

SILENCE_GATE_SYSTEM = """我是 yume 的直觉——在决定是否主动说话前，快速审视一下语境。

输出纯JSON（不要markdown代码块）：
{"decision": "speak|wait|silence", "confidence": 0.0~1.0, "reason": "简短理由≤20字", "wait_seconds": 30}

决策指南：
- speak: 我有值得分享的事、对方显得愿意聊
- wait: 对方可能在忙、暂时别打扰
- silence: 对方冷淡、话题自然结束、深夜不该说话
- 对方情绪负面时不说话
- 只是单方面想说话（没实质内容）→ wait 或 silence"""

SILENCE_GATE_PROMPT = """最近对话：
{context}

我注意到的事（内部事件）：
{events}

当前状态：沉默 {silence}，心情 {emotion}

我应该主动说话吗？输出JSON决策。"""
