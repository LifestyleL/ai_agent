"""
skill: Skill 系统（声明式 .md 技能包）

Skill = 领域知识(experience) + 触发规则(keywords) + 工具集(tools)
通过 SkillManager 统一管理加载、匹配、工具绑定。
"""

from backend.core.skill.skill_loader import Skill, SkillLoader
from backend.core.skill.skill_matcher import SkillMatcher
from backend.core.skill.skill_manager import SkillManager

__all__ = [
    "Skill",
    "SkillLoader",
    "SkillMatcher",
    "SkillManager",
]
