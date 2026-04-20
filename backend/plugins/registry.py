from typing import Dict, List, Any, Optional
from backend.plugins.base_tool import BaseTool


class ToolRegistry:
    """工具注册中心"""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        """注册一个工具实例"""
        self._tools[tool.name] = tool
        print(f"[Registry] 工具已注册: {tool.name}")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """根据名字获取工具实例"""
        return self._tools.get(name)

    def get_all_tools(self) -> List[BaseTool]:
        """获取所有已注册的工具实例"""
        return list(self._tools.values())

    def execute_tool(self, name: str, **kwargs) -> Any:
        """兼容旧代码的直接执行接口"""
        tool = self.get_tool(name)
        if not tool:
            raise ValueError(f"工具未注册: {name}")
        # 调用我们统一规定的 execute 方法
        return tool.execute(**kwargs)

    def get_legacy_schema(self) -> List[Dict[str, Any]]:
        """
        【关键兼容方法】
        扫描所有注册的工具，生成旧代码传给 DeepSeek 的工具描述字典列表。
        具体字段名（如 name, description, parameters）请阅读项目中现有的工具定义文件或 llm_collaborator.py
        中的传参格式，确保生成的字典结构与原有格式 100% 一致！
        """
        schemas = []
        for tool in self.get_all_tools():
            # 根据 tools/tool_docs.md 的格式，每个工具需要名称、描述和参数说明
            # 但当前 BaseTool 只有 name 和 description，没有 parameters 属性
            # 为了兼容，我们生成一个简化的字典，包含必要的字段
            schema = {
                "name": tool.name,
                "description": tool.description,
                # 旧代码可能期望 parameters 字段，但当前工具文档中参数是文本描述
                # 我们暂时留空，或者从工具的额外属性中获取
            }
            # 如果工具有 parameters 属性，添加进去
            if hasattr(tool, 'parameters'):
                schema["parameters"] = getattr(tool, 'parameters')
            schemas.append(schema)
        return schemas


# 全局单例
_tool_registry_instance = ToolRegistry()


def get_global_registry() -> ToolRegistry:
    return _tool_registry_instance