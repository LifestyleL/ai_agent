"""
ThinkPipeline 编排器 + PipelineStage 抽象 + ResponseDispatcher 协议

v2: ReAct 循环架构 — Setup → [LLM ↔ Tool]→ Finalize
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Protocol

from backend.core.think_pipeline.context import ThinkContext

logger = logging.getLogger(__name__)


class ResponseDispatcher(Protocol):
    """LLM Stream Stage 的抽象依赖，隔离 TTS + Live2D 的具体实现"""

    def set_emotion(self, emotion: str) -> None:
        """设置当前情绪：推送 TTS 标签 + Live2D 表情"""
        ...

    def enqueue_tts(self, text: str, emotion: str) -> None:
        """将文本送入 TTS 队列"""
        ...

    def send_to_frontend(self, text: str, msg_type: str) -> None:
        """推送文本到前端（打字机/思考提示）"""
        ...

    def speak_complete(self, text: str) -> None:
        """完整文本直接播报（非流式降级路径）"""
        ...


class PipelineStage(ABC):
    """Pipeline 阶段抽象基类"""

    @abstractmethod
    async def process(self, ctx: ThinkContext) -> ThinkContext:
        """处理上下文，返回新上下文（不可变）"""
        ...


class ThinkPipeline:
    """ReAct 编排器：Setup → [LLM ↔ Tool Exec] × N → Finalize"""

    def __init__(
        self,
        setup_stages: Optional[List[PipelineStage]] = None,
        llm_stage: Optional[PipelineStage] = None,
        tool_stage: Optional[PipelineStage] = None,
        finalize_stage: Optional[PipelineStage] = None,
        compressor=None,
    ):
        self._setup_stages = setup_stages or []
        self._llm_stage = llm_stage
        self._tool_stage = tool_stage
        self._finalize_stage = finalize_stage
        self._compressor = compressor

    async def execute(self, ctx: ThinkContext) -> ThinkContext:
        # ── Phase A: Setup（一次性）──
        for stage in self._setup_stages:
            ctx = await stage.process(ctx)
            if ctx.error:
                return ctx

        # ── Phase B: Build initial messages ──
        ctx = self._build_initial_messages(ctx)

        # ── Phase C: ReAct Loop ──
        final_response_ready = False

        for round_num in range(ctx.max_react_rounds):
            ctx = ctx.replace(react_round=round_num)

            ctx = await self._llm_stage.process(ctx)
            if ctx.error:
                break

            # Observation compression at step 4 (0-indexed round >= 3)
            if round_num >= 3 and self._compressor:
                ctx = await self._compressor.compress(ctx)

            # 有 tool_calls → 执行工具 → 继续循环
            if ctx.tool_calls:
                ctx = await self._tool_stage.process(ctx)
                continue

            # 无 tool_calls → 最终回复 → 退出
            final_response_ready = True
            break

        # max_react_rounds 用尽但仍有 tool_calls → 强制兜底回复
        if not final_response_ready and not ctx.error and self._llm_stage:
            ctx = await self._force_final_response(ctx)

        # ── Phase D: Finalize ──
        if self._finalize_stage:
            ctx = await self._finalize_stage.process(ctx)

        return ctx

    def _build_initial_messages(self, ctx: ThinkContext) -> ThinkContext:
        """从 system_prompt + user_input 构建初始消息列表"""
        messages = [{"role": "system", "content": ctx.system_prompt}]

        if ctx.screenshot_b64 and ctx.screenshot_b64.startswith("data:"):
            user_content = [
                {"type": "text", "text": ctx.user_input},
                {"type": "image_url", "image_url": {"url": ctx.screenshot_b64}},
            ]
        else:
            user_content = ctx.user_input

        messages.append({"role": "user", "content": user_content})
        return ctx.replace(messages=messages)

    async def _force_final_response(self, ctx: ThinkContext) -> ThinkContext:
        """max_react_rounds 用尽，强制 LLM 基于已有工具结果直接回复"""
        logger.warning("[Pipeline] max_react_rounds 用尽，兜底强制回复")
        ctx.messages.append({
            "role": "user",
            "content": (
                "你已经用完了所有工具调用轮次。现在请基于对话中已有的工具查询结果，"
                "尽你所能直接回答用户。不要再说需要更多信息或建议调用工具。"
                "如果确实信息不足，诚实地告诉用户你尽力了。"
            ),
        })
        ctx = ctx.replace(tool_calls=[])
        return await self._llm_stage.process(ctx)
