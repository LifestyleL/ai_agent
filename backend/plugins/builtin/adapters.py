from typing import Dict, Any
from backend.plugins.base_tool import BaseTool
# 导入原有的工具调用函数
try:
    from core.agent.agent_brain import call_tool
except ImportError:
    # 备用：定义空函数，避免导入失败
    def call_tool(tool_name, params, llm):
        return f"错误：无法导入 call_tool，工具 {tool_name} 无法执行"


class SearchMemoryAdapter(BaseTool):
    """将 search_memory 工具适配为标准 BaseTool"""

    name = "search_memory"
    description = "搜索记忆。有日期则精准溯源，无日期则语义搜索。"

    def __init__(self):
        pass

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        标准接口实现。
        通过原有的 call_tool 函数执行工具。
        返回值必须是 dict，符合旧代码的预期。
        """
        # 提取参数
        params = {}
        if "keyword" in kwargs:
            params["keyword"] = kwargs["keyword"]
        if "target_date" in kwargs:
            params["target_date"] = kwargs["target_date"]
        if "limit" in kwargs:
            params["limit"] = kwargs.get("limit", 5)

        llm = kwargs.get("llm")

        # 调用原有工具逻辑
        result = call_tool(self.name, params, llm)

        # 确保返回字典
        if isinstance(result, dict):
            return result
        else:
            return {"result": result}


class WriteFileAdapter(BaseTool):
    """将 write_file 工具适配为标准 BaseTool"""

    name = "write_file"
    description = "写内容到文件。"

    def __init__(self):
        pass

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        标准接口实现。
        通过原有的 call_tool 函数执行工具。
        """
        # 提取参数
        params = {}
        if "filename" in kwargs:
            params["filename"] = kwargs["filename"]
        if "content" in kwargs:
            params["content"] = kwargs["content"]

        llm = kwargs.get("llm")

        # 调用原有工具逻辑
        result = call_tool(self.name, params, llm)

        if isinstance(result, dict):
            return result
        else:
            return {"result": result}