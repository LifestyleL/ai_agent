"""
Observation Compressor — 防止 ReAct 多轮工具调用后 token 爆炸

在第 4 轮（0-indexed round >= 3）触发：保留最近 1 轮工具结果原文，
将更早轮次的工具调用+结果压缩为一段简短摘要。
"""

import logging
from typing import List

from backend.core.think_pipeline.context import ThinkContext

logger = logging.getLogger(__name__)

_COMPRESS_SYSTEM = (
    "你是一个工具调用历史压缩器。将多轮工具调用和结果压缩为一段简短摘要。"
    "每轮用一句话概括：工具名 + 关键结果。不要遗漏任何轮次。"
    "直接输出摘要文本，不要加前缀或解释。"
)


class ObservationCompressor:
    """ReAct 观察压缩器"""

    def __init__(self, llm):
        self._llm = llm

    async def compress(self, ctx: ThinkContext) -> ThinkContext:
        messages = ctx.messages

        # 定位所有工具相关消息的索引
        tool_indices = _find_tool_message_indices(messages)
        if len(tool_indices) < 4:  # 少于 2 轮工具调用，不压缩
            return ctx

        # 按轮次分组（每轮 = 1 assistant(tool_calls) + N tool results）
        rounds = _group_by_round(messages, tool_indices)
        if len(rounds) <= 1:
            return ctx

        # 保留最近 1 轮的原文，压缩更早的轮次
        recent_round = rounds[-1]
        older_rounds = rounds[:-1]

        # 构建压缩文本
        older_text = _format_rounds_for_compress(messages, older_rounds)
        recent_text = _format_rounds_raw(messages, recent_round)

        try:
            summary = await self._llm.ask_with_system_async(
                _COMPRESS_SYSTEM, older_text, temperature=0.3
            )
            if not summary:
                raise ValueError("empty summary")
        except Exception as e:
            logger.warning("[ObsCompress] LLM 摘要失败: %s，使用截断兜底", e)
            summary = _truncate_summary(older_text)

        # 重建消息列表：system + user + 摘要 + 最近一轮原文 + 后续非工具消息
        new_messages = _rebuild_messages(
            messages, older_rounds, recent_round, summary
        )

        logger.info(
            "[ObsCompress] 压缩 %d 轮 → 摘要(%d chars)，从 %d → %d 条消息",
            len(older_rounds), len(summary), len(messages), len(new_messages),
        )

        return ctx.replace(messages=new_messages)


def _find_tool_message_indices(messages: list) -> List[int]:
    """找到所有工具相关消息的索引"""
    indices = []
    for i, msg in enumerate(messages):
        if msg.get("role") == "tool":
            indices.append(i)
        elif msg.get("role") == "assistant" and msg.get("tool_calls"):
            indices.append(i)
    return indices


def _group_by_round(messages: list, tool_indices: List[int]) -> List[List[int]]:
    """将工具消息索引按轮次分组"""
    rounds = []
    current_round = []
    for idx in tool_indices:
        msg = messages[idx]
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            if current_round:
                rounds.append(current_round)
            current_round = [idx]
        elif msg.get("role") == "tool":
            current_round.append(idx)
    if current_round:
        rounds.append(current_round)
    return rounds


def _format_rounds_for_compress(messages: list, rounds: List[List[int]]) -> str:
    """格式化旧轮次为 LLM 可理解的文本"""
    lines = []
    for i, round_indices in enumerate(rounds):
        lines.append(f"--- 第{i+1}轮 ---")
        for idx in round_indices:
            msg = messages[idx]
            role = msg.get("role", "")
            if role == "assistant":
                for tc in msg.get("tool_calls", []):
                    fn = tc.get("function", {})
                    lines.append(f"调用 {fn.get('name', '?')}({fn.get('arguments', '{}')})")
            elif role == "tool":
                content = msg.get("content", "")
                lines.append(f"结果: {content[:300]}")
    return "\n".join(lines)


def _format_rounds_raw(messages: list, round_indices: List[int]) -> str:
    """格式化保留轮次的原文"""
    parts = []
    for idx in round_indices:
        msg = messages[idx]
        parts.append(f"[{msg.get('role')}] {msg.get('content', '')}")
    return "\n".join(parts)


def _truncate_summary(text: str) -> str:
    """截断兜底摘要"""
    lines = text.split("\n")
    short_lines = []
    for line in lines:
        if len(line) > 150:
            line = line[:147] + "..."
        short_lines.append(line)
    return "[工具历史摘要]\n" + "\n".join(short_lines[:10])


def _rebuild_messages(
    messages: list,
    older_rounds: List[List[int]],
    recent_round: List[int],
    summary: str,
) -> list:
    """重建消息列表，替换旧轮次为摘要"""
    # 收集需要移除的索引
    remove_indices = set()
    for r in older_rounds:
        remove_indices.update(r)

    # 保留最近一轮的索引
    keep_indices = set(recent_round)

    new_messages = []
    summary_inserted = False

    for i, msg in enumerate(messages):
        if i in remove_indices:
            # 在第一个被移除的位置插入摘要
            if not summary_inserted:
                new_messages.append({
                    "role": "system",
                    "content": f"[工具历史摘要] {summary}",
                })
                summary_inserted = True
            continue
        new_messages.append(msg)

    return new_messages
