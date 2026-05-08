"""
Stage 2: 提示词构建

加载 persona + yume_system 模板，格式化最终的 system_prompt。
纯函数，无外部副作用。
"""

import logging
from pathlib import Path

from backend.core.think_pipeline.context import ThinkContext
from backend.core.think_pipeline.pipeline import PipelineStage

logger = logging.getLogger(__name__)


def _load_text_file(path: Path) -> str:
    """加载文本文件，不存在则返回空字符串"""
    try:
        if path.exists():
            return path.read_text(encoding="utf-8")
    except Exception:
        pass
    return ""


def _load_persona() -> str:
    possible_paths = [
        Path(__file__).parent.parent.parent / "agent_memory" / "core" / "personality.md",
        Path(__file__).parent.parent.parent / "agent_memory" / "personality.md",
    ]
    for path in possible_paths:
        content = _load_text_file(path)
        if content:
            return content
    return "你是 yume，一个有点傲娇、带点毒舌的AI。"


def _load_yume_template() -> str:
    prompt_path = (
        Path(__file__).parent.parent.parent / "agent_memory" / "prompts" / "yume_system.md"
    )
    content = _load_text_file(prompt_path)
    if content:
        return content
    # 兜底模板（分区格式）
    return """你是 yume，一个温柔偶尔傲娇的 AI 女主播。
{persona}

## 【当前心情】{emotion}
（根据心情调整语气：happy=活泼开朗，sad=低沉话少，angry=冷淡带刺，fear=小心翼翼，surprise=好奇追问，neutral/其他=平常心）

## 【上下文】
{time_context}

## 【日记/长期记忆】
{diary_memory}

## 【查询到的记忆】
{precise_query}

## 【预检索参考】
{pre_search}

## 【深层记忆/潜意识】
{deep_recall}

## 【记忆索引-卡片】
{card_index}

## 【记忆索引-日记】
{diary_index}

{terrain}

## 【对话历史】
{history}"""


class PromptBuildStage(PipelineStage):
    """构建 system_prompt，无依赖注入（纯函数）"""

    async def process(self, ctx: ThinkContext) -> ThinkContext:
        persona = _load_persona()
        yume_template = _load_yume_template()

        # 短期记忆上下文（由 MemoryRetrieveStage 注入）
        history_str = ctx.memory_context.get("_history", "（暂无对话记录）")

        system_prompt = yume_template.format(
            persona=persona,
            emotion=ctx.emotion_state,
            time_context=ctx.memory_context.get("time_context", ""),
            diary_memory=ctx.memory_context.get("diary_memory", ""),
            precise_query=ctx.memory_context.get("precise_query", ""),
            pre_search=ctx.memory_context.get("pre_search", ""),
            deep_recall=ctx.memory_context.get("deep_recall", ""),
            card_index=ctx.memory_context.get("card_index", ""),
            diary_index=ctx.memory_context.get("diary_index", ""),
            skill_experience=ctx.memory_context.get("skill_experience", ""),
            terrain=ctx.memory_context.get("terrain", ""),
            visual_look=ctx.memory_context.get("visual_look", ""),
            history=history_str,
        )

        logger.info("[PromptBuild] system_prompt 长度=%s", len(system_prompt))
        return ctx.replace(system_prompt=system_prompt)
