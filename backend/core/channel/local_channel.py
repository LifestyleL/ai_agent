"""
LocalChannel — 本地频道（Live2D + TTS + Frontend）
"""

import logging

from backend.core.channel.base import Channel
from backend.core.think_pipeline.context import ThinkContext

logger = logging.getLogger(__name__)


class LocalChannel(Channel):
    """本地 AI 频道：推送 Live2D 表情 + TTS 语音 + Frontend 文本"""

    name = "local"

    def __init__(self, dispatcher=None, frontend=None, tts_manager=None):
        self._dispatcher = dispatcher
        self._frontend = frontend
        self._tts = tts_manager

    @property
    def is_external(self) -> bool:
        return False

    @property
    def template_path(self) -> str:
        return ""  # 使用默认 yume_system.md

    async def pre_process(self, ctx: ThinkContext) -> ThinkContext:
        """推送情绪标签到 Live2D 前端"""
        emotion_label = ctx.memory_context.get("emotion_label", "neutral")
        if self._tts:
            self._tts.current_emotion = emotion_label
        if self._frontend:
            self._frontend.send_live2d_cmd("emotion", emotion=emotion_label)
        return ctx.replace(channel_name="local")

    async def send_response(self, ctx: ThinkContext) -> None:
        """推送最终回复到 TTS 队列 + 前端"""
        if not ctx.response_text:
            return
        if self._dispatcher:
            self._dispatcher.send_to_frontend(ctx.response_text, "chunk")
            # 非流式降级：完整文本播报
            self._dispatcher.speak_complete(ctx.response_text)
