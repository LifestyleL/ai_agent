"""
Stage 1.5: Skill 匹配阶段

插入在 MemoryRetrieveStage 和 PromptBuildStage 之间。
匹配用户输入到已注册的 Skills，将匹配到的经验文本注入 ThinkContext。
无匹配时透传，零性能损耗。
"""

import logging
from typing import Dict, List, Optional

from backend.core.think_pipeline.context import ThinkContext
from backend.core.think_pipeline.pipeline import PipelineStage

logger = logging.getLogger(__name__)


class SkillInfo:
    """技能注册信息（轻量描述）"""

    def __init__(self, name: str, description: str, triggers: List[str]):
        self.name = name
        self.description = description
        self.triggers = triggers


class SkillMatcher:
    """基于关键词的技能匹配器"""

    def __init__(self, skills: Optional[List[SkillInfo]] = None):
        self._skills: Dict[str, SkillInfo] = {}
        for s in (skills or []):
            self._skills[s.name] = s

    def register(self, skill: SkillInfo) -> None:
        self._skills[skill.name] = skill

    def match(self, user_input: str) -> str:
        """匹配用户输入到技能，返回经验文本。无匹配返回空字符串。"""
        user_lower = user_input.lower()
        for skill in self._skills.values():
            for trigger in skill.triggers:
                if trigger.lower() in user_lower:
                    logger.info("[SkillMatch] 匹配到技能 '%s' (触发词: '%s')", skill.name, trigger)
                    return (
                        f"【可用技能】{skill.name}: {skill.description}\n"
                        f"如果你需要执行此技能，请按技能描述调用相关工具。"
                    )
        return ""


class SkillMatchStage(PipelineStage):
    """技能匹配 Pipeline Stage"""

    def __init__(self, matcher: SkillMatcher):
        self._matcher = matcher

    async def process(self, ctx: ThinkContext) -> ThinkContext:
        if not self._matcher:
            return ctx

        skill_text = self._matcher.match(ctx.user_input)
        if skill_text:
            ctx.memory_context["skill_experience"] = skill_text
            logger.info("[SkillMatch] 已注入技能经验到上下文")
        else:
            ctx.memory_context["skill_experience"] = ""

        return ctx


def build_default_matcher() -> SkillMatcher:
    """构建默认技能匹配器（注册内置 Skill）"""
    matcher = SkillMatcher()
    matcher.register(SkillInfo(
        name="memory_summary_skill",
        description="搜索近期记忆并生成归档摘要",
        triggers=["总结", "归档", "摘要", "回顾", "梳理"],
    ))
    return matcher
