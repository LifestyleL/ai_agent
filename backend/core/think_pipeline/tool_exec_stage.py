"""
Stage: Tool Exec（ReAct 循环中的工具执行阶段）

执行 ctx.tool_calls 中的所有工具调用，将结果注入 ctx.messages，
供下一轮 LLM 调用时使用。
"""

import json
import logging
from typing import Optional, List

from backend.core.think_pipeline.context import ThinkContext
from backend.core.think_pipeline.pipeline import PipelineStage
from backend.plugins.tool_result import ToolResult

logger = logging.getLogger(__name__)


class ToolExecStage(PipelineStage):
    """工具执行阶段 — 批量执行 tool_calls，注入消息历史"""

    def __init__(self, registry):
        self._registry = registry
        # 重复调用检测
        self._last_calls: List[tuple] = []

    async def process(self, ctx: ThinkContext) -> ThinkContext:
        if not ctx.tool_calls:
            return ctx

        results: list[ToolResult] = []

        for tc in ctx.tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            try:
                params = json.loads(func.get("arguments", "{}"))
            except json.JSONDecodeError:
                params = {}

            # ── 重复调用检测 ──
            call_sig = (tool_name, json.dumps(params, sort_keys=True, ensure_ascii=False))
            if self._is_duplicate(call_sig):
                logger.warning("[ToolExec] duplicate call detected: %s", tool_name)
                duplicate_hint = ToolResult.error_result(
                    f"重复调用警告：你在上一轮已经用相同参数调用过 {tool_name} 了。请基于已有的工具结果直接回复用户，不要再重复查询。"
                )
                results.append(duplicate_hint)
                ctx.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", "unknown"),
                    "content": duplicate_hint.to_message(),
                })
                continue

            self._last_calls.append(call_sig)
            if len(self._last_calls) > 10:
                self._last_calls = self._last_calls[-5:]

            logger.info("[ToolExec] %s(%s)", tool_name, json.dumps(params, ensure_ascii=False)[:100])

            # ── 执行工具 ──
            result = self._registry.call_tool(tool_name, params)
            results.append(result)

            # ── 追加 assistant(tool_calls) + tool result 到消息历史 ──
            assistant_msg = {
                "role": "assistant",
                "tool_calls": [tc],
            }
            # DeepSeek 思维链需传回
            if ctx.reasoning_content:
                assistant_msg["reasoning_content"] = ctx.reasoning_content

            ctx.messages.append(assistant_msg)
            ctx.messages.append({
                "role": "tool",
                "tool_call_id": tc.get("id", "unknown"),
                "content": result.to_message()[:2000],
            })

        ctx.react_round += 1
        ctx.tool_calls = []
        ctx.reasoning_content = ""
        return ctx

    def _is_duplicate(self, call_sig: tuple) -> bool:
        """检测连续重复调用"""
        return len(self._last_calls) >= 1 and self._last_calls[-1] == call_sig

    def reset(self):
        """重置重复检测历史"""
        self._last_calls.clear()
