"""
Stage 5: 收尾 + 异步记忆写入

未通过流式播报的文本补播，触发异步记忆写入 + 日记，
更新 GoalTracker，发布 RESPONSE_READY 事件通知外部适配器。
"""

import logging
from typing import Optional

from backend.core.think_pipeline.context import ThinkContext
from backend.core.think_pipeline.pipeline import PipelineStage, ResponseDispatcher
from backend.core.event.event_bus import event_bus, EventType

logger = logging.getLogger(__name__)


class FinalizeStage(PipelineStage):
    """收尾：补播文本 + 记忆写入 + 目标追踪"""

    def __init__(
        self,
        memory_core,
        dispatcher: Optional[ResponseDispatcher] = None,
        goal_tracker=None,
        channel=None,
    ):
        self._memory = memory_core
        self._dispatcher = dispatcher
        self._goal_tracker = goal_tracker
        self._channel = channel  # 用于判断 is_external

    async def process(self, ctx: ThinkContext) -> ThinkContext:
        is_ext = self._channel.is_external if self._channel else bool(ctx.session_id)

        # 如果流式未播报任何内容，补播完整回复（仅本地会话）
        if not ctx.streamed_to_tts and self._dispatcher and not is_ext:
            import asyncio

            await asyncio.to_thread(self._dispatcher.speak_complete, ctx.response_text)

        # 短期记忆同步写入 + 异步卡片/日记
        if self._memory:
            clean_input = ctx.original_user_input or ctx.user_input
            self._memory.add_short_term("user", clean_input)
            self._memory.add_short_term("assistant", ctx.response_text)
            self._memory.start_async_memory_write(clean_input, ctx.response_text)
            # 用户明确要求"记住"则追加到日记
            if ctx.memory_context.get("write_request"):
                self._memory.append_diary_draft(
                    f"用户明确要求记住：{clean_input[:200]}"
                )

        # 后台更新对话目标
        if self._goal_tracker:
            self._goal_tracker.maybe_update()

        # 通知外部适配器（QQ / Telegram 等）
        if ctx.session_id:
            event_bus.publish(EventType.RESPONSE_READY, source="FinalizeStage",
                              response_text=ctx.response_text, session_id=ctx.session_id)

        logger.info("[Finalize] 收尾完成 response_len=%s", len(ctx.response_text))
        return ctx
