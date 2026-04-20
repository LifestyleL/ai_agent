from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseTool(ABC):
    """底层原子工具基类"""
    name: str = "base_tool"
    description: str = ""

    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        """执行工具并返回结构化结果"""
        pass