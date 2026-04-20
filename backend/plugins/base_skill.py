from abc import ABC, abstractmethod
from typing import List, Dict, Any

# 注意导入路径，根据你实际创建的 base_tool 位置调整
from backend.plugins.base_tool import BaseTool

class BaseSkill(ABC):
    """高级技能基类：组合一个或多个 Tool 完成特定目标"""
    name: str = "base_skill"
    description: str = ""
    required_tools: List[BaseTool] = []

    def __init__(self, tools: List[BaseTool]):
        self.tools = {t.name: t for t in tools}

    @abstractmethod
    async def run(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行技能流程"""
        pass