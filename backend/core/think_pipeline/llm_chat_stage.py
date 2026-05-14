"""
Stage: LLM Chat（ReAct 循环中的 LLM 调用阶段）

使用非流式 chat_async + tools 定义。
返回完整响应后：有 tool_calls → 由 execute() 循环执行工具；有 content → 最终回复。

替换 LLMStreamStage 在 ReAct 管线中的角色。
"""

import logging
from typing import Optional

from backend.core.think_pipeline.context import ThinkContext
from backend.core.think_pipeline.pipeline import PipelineStage

logger = logging.getLogger(__name__)


class LLMChatStage(PipelineStage):
    """ReAct LLM 调用阶段 — 非流式，支持 tools。有截图时自动切 vision_llm。"""

    def __init__(self, llm, registry=None, vision_llm=None):
        self._llm = llm
        self._vision_llm = vision_llm
        self._registry = registry

    def _pick_llm(self, messages: list):
        """有图片内容且 vision_llm 可用时切 VLM"""
        if not self._vision_llm:
            return self._llm
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "image_url":
                        return self._vision_llm
        return self._llm

    async def process(self, ctx: ThinkContext) -> ThinkContext:
        tools_def = self._registry.list_tools() if self._registry else None

        llm = self._pick_llm(ctx.messages)
        response = await llm.chat_async(
            ctx.messages, temperature=0.7, tools=tools_def
        )

        if "error" in response:
            logger.error("[LLMChat] LLM error: %s", response["error"])
            return ctx.replace(error=response["error"])

        choice = response["choices"][0]
        msg = choice.get("message", {})
        finish_reason = choice.get("finish_reason", "")

        # 提取原生 tool_calls
        tool_calls = msg.get("tool_calls", [])

        content = msg.get("content", "")

        if tool_calls:
            logger.info("[LLMChat] tool_calls=%d finish=%s", len(tool_calls), finish_reason)
            return ctx.replace(
                tool_calls=tool_calls,
                reasoning_content=msg.get("reasoning_content", ""),
                response_text="",
            )

        # 无工具调用 → 这是最终文本回复
        logger.info("[LLMChat] text response len=%d finish=%s", len(content), finish_reason)
        return ctx.replace(
            response_text=content.strip() if content else "",
            tool_calls=[],
            reasoning_content=msg.get("reasoning_content", ""),
        )
