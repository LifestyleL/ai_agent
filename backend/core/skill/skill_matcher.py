from typing import List, Optional
from .skill_loader import Skill, SkillLoader


class SkillMatcher:
    """根据用户输入，匹配相关的 Skill 经验"""

    def __init__(self, loader: Optional[SkillLoader] = None):
        self.loader = loader or SkillLoader()
        self._skills = self.loader.load_all()

    def reload(self):
        """重新加载（开发阶段热更新用）"""
        self.loader.clear_cache()
        self._skills = self.loader.load_all()

    def match(self, user_input: str) -> List[Skill]:
        """
        返回匹配到的 Skill 列表，按匹配度降序。
        匹配规则：用户输入包含 skill 的任一 keyword。
        """
        input_lower = user_input.lower()
        matched = []

        for skill in self._skills.values():
            hit_keywords = [
                kw for kw in skill.keywords
                if kw.lower() in input_lower
            ]
            if hit_keywords:
                matched.append((skill, len(hit_keywords)))

        # 按命中关键词数量降序
        matched.sort(key=lambda x: x[1], reverse=True)
        return [skill for skill, _ in matched]

    def get_experience_text(self, user_input: str) -> str:
        """
        核心方法：返回拼装好的经验文本，用于注入 prompt。
        无匹配时返回空字符串。
        """
        matched = self.match(user_input)
        if not matched:
            return ""

        parts = []
        for skill in matched:
            parts.append(
                f"### {skill.name}\n{skill.experience}"
            )
        return "\n\n".join(parts)

    def get_related_tools(self, user_input: str) -> List[str]:
        """获取匹配技能相关的工具名称列表（去重）"""
        matched = self.match(user_input)
        tools = []
        for skill in matched:
            tools.extend(skill.tools)
        # 去重并保持顺序
        seen = set()
        unique_tools = []
        for tool in tools:
            if tool not in seen:
                seen.add(tool)
                unique_tools.append(tool)
        return unique_tools