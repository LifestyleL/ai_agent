"""
SkillManager — 统一技能管理器

合并 System A（管线内 SkillMatchStage）和 System B（core/skill/ 文件加载），
提供：加载/卸载/重载 + LLM 语义匹配 + 关键词兜底 + 自动工具绑定。
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Dict, Optional

from backend.core.skill.skill_loader import Skill, SkillLoader
from backend.core.skill.skill_matcher import SkillMatcher

logger = logging.getLogger(__name__)

_LLM_MATCH_PROMPT = (
    "你是意图分类器。根据用户输入判断最匹配的技能。"
    "只回复技能名称（精确匹配），无匹配回复 NONE。"
    "不要输出其他内容。"
)

_LLM_MATCH_TIMEOUT = float(os.environ.get("SKILL_LLM_TIMEOUT", "5.0"))


class SkillManager:
    """统一技能管理器：加载 .md 技能包，LLM 语义匹配，工具绑定"""

    def __init__(self, loader=None, llm=None, tool_registry=None):
        self._loader = loader or SkillLoader()
        self._matcher = SkillMatcher(self._loader)
        self._llm = llm
        self._registry = tool_registry
        # 跟踪每个技能启用的工具名
        self._skill_tools: Dict[str, list] = {}

    # ── 生命周期 ──

    def load_all(self) -> int:
        """加载全部 .md 技能文件，自动绑定工具。返回加载数量"""
        skills = self._loader.load_all()
        for skill in skills.values():
            self._register_tools(skill)
        logger.info("[SkillManager] 加载完成: %d 个技能, 工具绑定: %s",
                     len(skills), dict(self._skill_tools))
        return len(skills)

    def load_skill(self, path: str) -> Optional[Skill]:
        """加载单个技能文件"""
        filepath = Path(path)
        if not filepath.is_absolute():
            filepath = self._loader.skills_dir / filepath
        skill = self._loader._parse_file(filepath)
        if skill:
            self._loader._cache[skill.name] = skill
            self._register_tools(skill)
            logger.info("[SkillManager] 热加载技能: %s", skill.name)
        return skill

    def unload_skill(self, name: str) -> bool:
        """卸载技能，注销工具，清除缓存"""
        skill = self._loader._cache.pop(name, None)
        if not skill:
            return False
        self._unregister_tools(skill)
        logger.info("[SkillManager] 卸载技能: %s", name)
        return True

    def reload(self) -> int:
        """清缓存并重新加载全部"""
        self._loader.clear_cache()
        self._skill_tools.clear()
        return self.load_all()

    # ── 匹配 ──

    async def match(self, user_input: str) -> str:
        """LLM 语义匹配 → 返回格式化经验文本；无匹配返回空字符串"""
        if not user_input:
            return ""

        # 主路径：LLM 语义匹配
        skill = await self._llm_match(user_input)
        if skill is None:
            # Fallback：关键词匹配
            skill = self._keyword_match(user_input)

        if skill is None:
            logger.info("[SkillManager] 无匹配技能: '%s'", user_input[:40])
            return ""

        logger.info("[SkillManager] 匹配技能 '%s' for '%s'", skill.name, user_input[:40])
        return f"### {skill.name}\n{skill.experience}"

    async def _llm_match(self, user_input: str) -> Optional[Skill]:
        """LLM 语义匹配"""
        if not self._llm:
            return None

        skills = self._loader._cache
        if not skills:
            return None

        # 构建分类 prompt
        skill_list = "\n".join(
            f"- {s.name}: {s.description}" for s in skills.values()
        )
        user_prompt = (
            f"用户输入: \"{user_input}\"\n\n"
            f"可用技能:\n{skill_list}\n\n"
            "哪个技能最匹配用户意图？只回复技能名称，无匹配回复 NONE。"
        )

        try:
            result = await asyncio.wait_for(
                self._llm.ask_with_system_async(
                    _LLM_MATCH_PROMPT, user_prompt, temperature=0
                ),
                timeout=_LLM_MATCH_TIMEOUT,
            )
            if not result:
                return None
            name = result.strip().upper()
            if name == "NONE":
                return None
            # 按名称查找（不区分大小写）
            for skill_name, skill in skills.items():
                if skill_name.lower() == name.lower():
                    return skill
        except asyncio.TimeoutError:
            logger.warning("[SkillManager] LLM 匹配超时，降级关键词")
        except Exception as e:
            logger.warning("[SkillManager] LLM 匹配异常: %s，降级关键词", e)

        return None

    def _keyword_match(self, user_input: str) -> Optional[Skill]:
        """关键词匹配兜底"""
        matched = self._matcher.match(user_input)
        return matched[0] if matched else None

    # ── 工具绑定 ──

    def _register_tools(self, skill: Skill):
        """记录技能工具绑定（Phase 3 不影响 list_tools 可见性）"""
        self._skill_tools[skill.name] = list(skill.tools)

    def _unregister_tools(self, skill: Skill):
        """移除技能工具绑定记录"""
        self._skill_tools.pop(skill.name, None)

    # ── 查询 ──

    @property
    def active_skills(self) -> Dict[str, Skill]:
        """当前已加载的技能"""
        return dict(self._loader._cache)

    @property
    def active_tools(self) -> Dict[str, list]:
        """当前技能→工具映射"""
        return dict(self._skill_tools)
