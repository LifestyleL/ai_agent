from typing import Dict, Any
from backend.plugins.base_tool import BaseTool
# 导入原有的工具调用函数
try:
    from core.agent.agent_brain import call_tool
except ImportError:
    # 备用：定义空函数，避免导入失败
    def call_tool(tool_name, params, llm):
        return f"错误：无法导入 call_tool，工具 {tool_name} 无法执行"


class ReadFileAdapter(BaseTool):
    """将 read_file 工具适配为标准 BaseTool"""

    name = "read_file"
    description = "读文件内容（替代 load_memory）。"

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
        if "filenames" in kwargs:
            params["filenames"] = kwargs["filenames"]
        elif "files" in kwargs:
            params["files"] = kwargs["files"]

        # 兼容原有参数格式
        if "filename" in kwargs:
            params["files"] = [kwargs["filename"]]

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


class SummarizeArchiveAdapter(BaseTool):
    """将 summarize_and_archive 工具适配为标准 BaseTool"""

    name = "summarize_and_archive"
    description = "记忆满载归档（替代 update_long_term_memory）。"

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
        if "max_lines" in kwargs:
            params["max_lines"] = kwargs["max_lines"]

        llm = kwargs.get("llm")

        # 调用原有工具逻辑
        result = call_tool(self.name, params, llm)

        # 确保返回字典
        if isinstance(result, dict):
            return result
        else:
            return {"result": result}


class WriteDiaryAdapter(BaseTool):
    """将 write_diary 工具适配为标准 BaseTool"""

    name = "write_diary"
    description = "写日记（有日期写该日，无日期自动检测）。"

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
        if "target_date" in kwargs:
            params["target_date"] = kwargs["target_date"]

        llm = kwargs.get("llm")

        # 调用原有工具逻辑
        result = call_tool(self.name, params, llm)

        # 确保返回字典
        if isinstance(result, dict):
            return result
        else:
            return {"result": result}