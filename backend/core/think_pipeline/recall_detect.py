"""
Stage 4: 缓冲语检测 + 子 LLM 深挖 + AI主动查记忆

检测主 LLM 回复中的缓冲信号（"让我想想"等）或 [MEMORY_SEARCH: keyword] 指令，
触发查询子 LLM 执行记忆检索。不负责调用 Pipeline 重入，
只设置 needs_recall_retry 标记。
"""

import asyncio
import logging
import re
from typing import Protocol

from backend.core.think_pipeline.context import ThinkContext
from backend.core.think_pipeline.pipeline import PipelineStage

logger = logging.getLogger(__name__)

# 缓冲语检测模式：主 LLM 输出匹配这些表示"我需要查一下"
_RECALL_SIGNAL_PATTERN = re.compile(
    r'(让我想想|我想想|嗯[.…～~]+|不太确定|不记得了|'
    r'让我回忆|等一下|我查查|我翻翻|让我找找|'
    r'这个嘛|嘶[.…～~]*|诶[.…～~]*|唔[.…～~]+)'
)

# AI 主动查记忆指令
_MEMORY_SEARCH_PATTERN = re.compile(r'\[MEMORY_SEARCH:\s*(.+?)\]', re.IGNORECASE)


class QueryExecutor(Protocol):
    """查询子 LLM 执行器协议"""

    async def execute(self, query_goal: str) -> str:
        ...


def _detect_recall_signal(text: str) -> bool:
    """检测主 LLM 输出是否为记忆查询信号"""
    return _RECALL_SIGNAL_PATTERN.search(text) is not None


def _extract_query_goal(user_input: str, llm_response: str) -> str:
    """从 LLM 的缓冲回复中提取查询目标"""
    return (
        f"用户说：{user_input[:200]}\n"
        f"AI 的初步反应：{llm_response[:100]}\n"
        "请检索与上述内容相关的记忆。"
    )


class RecallDetectStage(PipelineStage):
    """检测缓冲信号 / AI主动查记忆指令，启动查询子 LLM 深挖"""

    def __init__(self, query_executor: QueryExecutor):
        self._query_executor = query_executor

    async def process(self, ctx: ThinkContext) -> ThinkContext:
        if ctx.recall_round >= ctx.max_recall_round:
            return ctx

        # ── 优先检测 [MEMORY_SEARCH: ...] 指令 ──
        m = _MEMORY_SEARCH_PATTERN.search(ctx.response_text)
        if m:
            keyword = m.group(1).strip()
            logger.info("[RecallDetect] AI主动查记忆: '%s'", keyword)
            clean_response = _MEMORY_SEARCH_PATTERN.sub("", ctx.response_text).strip()
            query_goal = f"用户输入：{ctx.original_user_input or ctx.user_input[:200]}\nAI指定关键词：{keyword}\n请用此关键词精确检索相关记忆。"
            try:
                recall_result = await self._query_executor.execute(query_goal)
                logger.info("[RecallDetect] 主动查询结果: %s...", (recall_result or "(空)")[:100])
            except Exception as e:
                logger.error("[RecallDetect] 主动查询失败: %s", e)
                recall_result = f"记忆检索失败: {e}"
            return ctx.replace(
                needs_recall_retry=True,
                deep_recall_result=recall_result,
                response_text=clean_response,
                recall_round=ctx.recall_round + 1,
            )

        # ── 原有缓冲语检测 ──
        is_recall = _detect_recall_signal(ctx.response_text)

        if not is_recall:
            memory_intent = ctx.memory_context.get("_intent", "")
            has_precise = (
                ctx.memory_context.get("precise_query", "")
                != "（本次未触发精准查询）"
            )
            if memory_intent in ("date_query", "keyword_query") and not has_precise:
                is_recall = True
                logger.info("[RecallDetect] 从意图检测触发深挖: %s", memory_intent)

        if not is_recall:
            return ctx

        logger.info("[RecallDetect] 检测到回忆信号: '%s...'", ctx.response_text[:60])

        query_goal = _extract_query_goal(ctx.user_input, ctx.response_text)
        logger.info("[RecallDetect] 启动查询子 LLM: %s...", query_goal[:80])

        try:
            recall_result = await self._query_executor.execute(query_goal)
            logger.info("[RecallDetect] 查询子 LLM 返回: %s...", (recall_result or "(空)")[:100])
        except Exception as e:
            logger.error("[RecallDetect] 查询子 LLM 失败: %s", e)
            recall_result = f"记忆检索失败: {e}"

        return ctx.replace(
            needs_recall_retry=True,
            deep_recall_result=recall_result,
            recall_round=ctx.recall_round + 1,
        )
