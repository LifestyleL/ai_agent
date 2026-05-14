from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseTool(ABC):
    """底层原子工具基类

    inputSchema: JSON Schema 格式的参数定义，用于 LLM function calling
    outputSchema: 返回值 schema（可选）
    """

    name: str = "base_tool"
    description: str = ""
    inputSchema: dict = {}
    outputSchema: dict = {}

    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        """执行工具并返回结构化结果"""
        pass