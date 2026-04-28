from typing import Dict, Any
from plugins.base_tool import BaseTool
from core.memory.memory_core import MemoryCore


class ReadFileAdapter(BaseTool):
    """将 read_file 工具适配为标准 BaseTool"""

    name = "read_file"
    description = "读文件内容（替代 load_memory）。"

    def __init__(self):
        pass

    def execute(self, **kwargs) -> Dict[str, Any]:
        params = {}
        if "filenames" in kwargs:
            params["filenames"] = kwargs["filenames"]
        elif "files" in kwargs:
            params["files"] = kwargs["files"]
        if "filename" in kwargs:
            params["files"] = [kwargs["filename"]]

        files = params.get("filenames", params.get("files", []))
        result = MemoryCore.tool_read_file(files)
        if isinstance(result, dict):
            return result
        return {"result": result}


class WriteFileAdapter(BaseTool):
    """将 write_file 工具适配为标准 BaseTool"""

    name = "write_file"
    description = "写内容到文件。"

    def __init__(self):
        pass

    def execute(self, **kwargs) -> Dict[str, Any]:
        filename = kwargs.get("filename", "")
        content = kwargs.get("content", "")
        result = MemoryCore.tool_write_file(filename, content)
        if isinstance(result, dict):
            return result
        return {"result": result}


class SearchMemoryAdapter(BaseTool):
    """将 search_memory 工具适配为标准 BaseTool"""

    name = "search_memory"
    description = "搜索记忆。有日期则精准溯源，无日期则语义搜索。"

    def __init__(self):
        pass

    def execute(self, **kwargs) -> Dict[str, Any]:
        keyword = kwargs.get("keyword", "")
        target_date = kwargs.get("target_date")
        limit = kwargs.get("limit", 5)
        llm = kwargs.get("llm")
        result = MemoryCore.tool_search_memory(keyword=keyword, llm=llm)
        if isinstance(result, dict):
            return result
        return {"result": result}


class SummarizeArchiveAdapter(BaseTool):
    """将 summarize_and_archive 工具适配为标准 BaseTool"""

    name = "summarize_and_archive"
    description = "记忆满载归档（替代 update_long_term_memory）。"

    def __init__(self):
        pass

    def execute(self, **kwargs) -> Dict[str, Any]:
        max_lines = kwargs.get("max_lines", 50)
        llm = kwargs.get("llm")
        result = MemoryCore.tool_summarize_and_archive(max_lines=max_lines, llm=llm)
        if isinstance(result, dict):
            return result
        return {"result": result}


class WriteDiaryAdapter(BaseTool):
    """将 write_diary 工具适配为标准 BaseTool"""

    name = "write_diary"
    description = "写日记（有日期写该日，无日期自动检测）。"

    def __init__(self):
        pass

    def execute(self, **kwargs) -> Dict[str, Any]:
        target_date = kwargs.get("target_date")
        llm = kwargs.get("llm")
        result = MemoryCore.tool_write_diary(target_date=target_date, llm=llm)
        if isinstance(result, dict):
            return result
        return {"result": result}
