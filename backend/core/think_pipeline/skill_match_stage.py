"""
Stage: Skill Match（技能匹配阶段）

使用 SkillManager 对用户输入做 LLM 语义匹配（+ 关键词兜底），
将匹配到的技能经验文本注入 ctx.memory_context["skill_experience"]，
供 PromptBuildStage 注入 system prompt。
"""

import logging

from backend.core.think_pipeline.context import ThinkContext
from backend.core.think_pipeline.pipeline import PipelineStage

logger = logging.getLogger(__name__)


class SkillMatchStage(PipelineStage):
    """技能匹配阶段 — 委托 SkillManager 做 LLM 语义匹配"""

    def __init__(self, skill_manager):
        self._manager = skill_manager

    async def process(self, ctx: ThinkContext) -> ThinkContext:
        experience = await self._manager.match(ctx.user_input)
        if experience:
            ctx.memory_context["skill_experience"] = experience
            logger.info("[SkillMatch] 已注入技能经验 (%d chars)", len(experience))
        else:
            ctx.memory_context["skill_experience"] = ""
        return ctx
