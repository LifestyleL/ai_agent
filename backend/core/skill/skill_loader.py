import os
import yaml
from dataclasses import dataclass, field
from typing import Optional, Dict
from pathlib import Path


@dataclass
class Skill:
    name: str
    description: str
    auto_execute: bool = False
    keywords: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    experience: str = ""


class SkillLoader:
    """加载 skills/ 目录下所有 skill.md 文件"""

    def __init__(self, skills_dir: Optional[str] = None):
        if skills_dir:
            self.skills_dir = Path(skills_dir)
        else:
            # 默认路径: backend/skills
            self.skills_dir = Path(__file__).parent.parent.parent / "skills"
        self._cache: Dict[str, Skill] = {}

    def load_all(self) -> Dict[str, Skill]:
        """加载所有技能，返回名称到Skill对象的映射"""
        if self._cache:
            return self._cache

        if not self.skills_dir.is_dir():
            print(f"[SkillLoader] 技能目录不存在: {self.skills_dir}")
            return self._cache

        for filename in os.listdir(self.skills_dir):
            if not filename.endswith(".md"):
                continue
            filepath = self.skills_dir / filename
            skill = self._parse_file(filepath)
            if skill:
                self._cache[skill.name] = skill
                print(f"[SkillLoader] 加载技能: {skill.name}")

        print(f"[SkillLoader] 共加载 {len(self._cache)} 个技能")
        return self._cache

    def _parse_file(self, filepath: Path) -> Optional[Skill]:
        """解析单个技能文件"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            # skill.md 是 YAML front matter + experience 正文
            # 用 --- 分割
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    meta = yaml.safe_load(parts[1])
                    experience = parts[2].strip()
                else:
                    meta = yaml.safe_load(parts[1])
                    experience = ""
            else:
                # 纯 YAML，无 experience
                meta = yaml.safe_load(content)
                experience = ""

            if not meta or "name" not in meta:
                print(f"[SkillLoader] 文件缺少name字段: {filepath}")
                return None

            return Skill(
                name=meta["name"],
                description=meta.get("description", ""),
                auto_execute=meta.get("auto_execute", False),
                keywords=meta.get("keywords", []),
                tools=meta.get("tools", []),
                experience=experience,
            )
        except Exception as e:
            print(f"[SkillLoader] 解析失败 {filepath}: {e}")
            return None

    def get_skill(self, name: str) -> Optional[Skill]:
        """按名称获取技能"""
        if not self._cache:
            self.load_all()
        return self._cache.get(name)

    def clear_cache(self):
        """清空缓存（用于热重载）"""
        self._cache.clear()