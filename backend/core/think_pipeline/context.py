"""
ThinkContext: Pipeline 中流转的不可变数据载体

每个 Stage 通过 ctx.replace() 创建新实例，不修改原实例。
"""

import dataclasses
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ThinkContext:
    """Pipeline 中流转的上下文对象"""

    user_input: str
    original_user_input: str = ""
    memory_context: dict = field(default_factory=dict)
    emotion_state: str = "neutral"
    system_prompt: str = ""
    response_text: str = ""
    streamed_to_tts: bool = False
    recall_round: int = 0
    max_recall_round: int = 2
    deep_recall_result: str = ""
    needs_recall_retry: bool = False
    error: Optional[str] = None
    is_spontaneous: bool = False
    screenshot_b64: str = ""  # 用户主动 look 时的原始截图 base64

    def replace(self, **changes):
        """创建修改后的新实例（不可变模式）"""
        return dataclasses.replace(self, **changes)
