from typing import Dict, Any
from plugins.base_tool import BaseTool
from core.memory.memory_facade import MemoryFacade as MemoryCore
from core.memory import tools as mem_tools


class ReadFileAdapter(BaseTool):
    """将 read_file 工具适配为标准 BaseTool"""

    name = "read_file"
    description = "读文件内容（替代 load_memory）。"
    inputSchema = {
        "type": "object",
        "properties": {
            "filenames": {
                "type": "array",
                "items": {"type": "string"},
                "description": "要读取的文件名列表"
            }
        },
        "required": ["filenames"]
    }

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
    inputSchema = {
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "文件名（相对于 memory_root）"
            },
            "content": {
                "type": "string",
                "description": "要写入的内容"
            }
        },
        "required": ["filename", "content"]
    }

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
    inputSchema = {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "搜索关键词"
            }
        },
        "required": ["keyword"]
    }

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
    inputSchema = {
        "type": "object",
        "properties": {
            "max_lines": {
                "type": "integer",
                "description": "最大行数限制"
            }
        }
    }

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
    inputSchema = {
        "type": "object",
        "properties": {
            "target_date": {
                "type": "string",
                "description": "目标日期，格式 YYYY-MM-DD"
            }
        }
    }

    def __init__(self):
        pass

    def execute(self, **kwargs) -> Dict[str, Any]:
        target_date = kwargs.get("target_date")
        llm = kwargs.get("llm")
        result = MemoryCore.tool_write_diary(target_date=target_date, llm=llm)
        if isinstance(result, dict):
            return result
        return {"result": result}


class ListDirectoryAdapter(BaseTool):
    """列出目录内容"""

    name = "list_directory"
    description = "列出指定目录下的文件和子目录。用于探索项目结构、查找文件位置。"
    inputSchema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "目录路径，相对于工作区根目录"
            },
            "recursive": {
                "type": "boolean",
                "description": "是否递归列出子目录"
            },
            "max_depth": {
                "type": "integer",
                "description": "递归最大深度 (默认 2)"
            }
        },
        "required": ["path"]
    }

    def execute(self, **kwargs) -> Dict[str, Any]:
        path = kwargs.get("path", ".")
        recursive = kwargs.get("recursive", False)
        max_depth = kwargs.get("max_depth", 2)
        result = mem_tools.tool_list_directory(
            path=path, recursive=recursive, max_depth=max_depth,
        )
        return {"result": result}


class GrepSearchAdapter(BaseTool):
    """在文件中搜索文本"""

    name = "grep_search"
    description = "在文件内容中搜索指定文本模式。用于查找代码、配置、文档中的特定内容。"
    inputSchema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "要搜索的文本或关键词"
            },
            "path": {
                "type": "string",
                "description": "搜索起始路径（目录或文件），相对于工作区根目录"
            },
            "recursive": {
                "type": "boolean",
                "description": "是否递归搜索子目录 (默认 true)"
            },
            "file_pattern": {
                "type": "string",
                "description": "文件名匹配模式，如 '*.py' (默认 *)"
            },
            "max_results": {
                "type": "integer",
                "description": "最多返回匹配行数 (默认 50)"
            }
        },
        "required": ["pattern", "path"]
    }

    def execute(self, **kwargs) -> Dict[str, Any]:
        pattern = kwargs.get("pattern", "")
        path = kwargs.get("path", ".")
        recursive = kwargs.get("recursive", True)
        file_pattern = kwargs.get("file_pattern", "*")
        max_results = kwargs.get("max_results", 50)
        result = mem_tools.tool_grep_search(
            pattern=pattern, path=path, recursive=recursive,
            file_pattern=file_pattern, max_results=max_results,
        )
        return {"result": result}


class WebSearchAdapter(BaseTool):
    """联网搜索工具"""

    name = "web_search"
    description = "联网搜索，返回标题+链接+摘要。用于查询实时信息、新闻、百科等。"
    inputSchema = {
        "type": "object",
        "properties": {
            "keywords": {
                "type": "string",
                "description": "搜索关键词"
            },
            "max_results": {
                "type": "integer",
                "description": "最大返回结果数 (默认 5)"
            }
        },
        "required": ["keywords"]
    }

    def execute(self, **kwargs) -> Dict[str, Any]:
        keywords = kwargs.get("keywords", "")
        max_results = kwargs.get("max_results", 5)
        result = mem_tools.tool_web_search(keywords=keywords, max_results=max_results)
        return {"result": result}


class RunCodeAdapter(BaseTool):
    """代码执行工具 — 需用户批准"""

    name = "run_code"
    description = "在沙箱中执行代码片段。支持 Python。执行前需用户批准。"
    requires_approval = True
    inputSchema = {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "要执行的代码",
            },
            "language": {
                "type": "string",
                "description": "编程语言 (默认 python)",
            },
        },
        "required": ["code"],
    }

    def __init__(self):
        self._executor = None

    def _get_executor(self):
        if self._executor is None:
            import config
            from backend.core.sandbox.factory import create_executor
            mode = getattr(config, "SANDBOX_MODE", "local")
            self._executor = create_executor(
                mode=mode,
                docker_image=getattr(config, "SANDBOX_DOCKER_IMAGE", "python:3.12-slim"),
                docker_memory_limit=getattr(config, "SANDBOX_DOCKER_MEMORY_LIMIT", "128m"),
                docker_cpu_limit=getattr(config, "SANDBOX_DOCKER_CPU_LIMIT", "0.5"),
            )
        return self._executor

    def execute(self, **kwargs) -> Dict[str, Any]:
        code = kwargs.get("code", "")
        language = kwargs.get("language", "python").lower()
        if not code.strip():
            return {"result": "[run_code] 错误: code 参数为空"}
        if language not in ("python", "py"):
            return {"result": f"[run_code] 不支持的语言: {language}，目前仅支持 python"}
        import config
        timeout = getattr(config, "SANDBOX_TIMEOUT", 10)
        executor = self._get_executor()
        result = executor.execute(code=code, language=language, timeout=timeout)
        return result.to_dict()


class RecognizeImageAdapter(BaseTool):
    """VLM 图片识别工具"""

    name = "recognize_image"
    description = (
        "识别图片内容，返回视觉描述。"
        "当用户发送图片时，用此工具查看图片中有什么。"
        "支持截图、照片、表情包、动漫图片等多种类型。"
    )
    inputSchema = {
        "type": "object",
        "properties": {
            "image_path": {
                "type": "string",
                "description": "图片文件路径（相对或绝对路径）"
            },
            "question": {
                "type": "string",
                "description": "对图片的具体问题，如'这张图里有什么文字'（可选，默认描述整体内容）"
            }
        },
        "required": ["image_path"]
    }

    def execute(self, **kwargs) -> Dict[str, Any]:
        image_path = kwargs.get("image_path", "")
        question = kwargs.get("question", "")
        result = mem_tools.tool_recognize_image(image_path=image_path, question=question)
        return {"result": result}
