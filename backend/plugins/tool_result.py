"""
工具调用统一返回格式

ToolResult 是所有工具（通过 MCP 或直接调用）的统一返回结构。
区分 "工具成功有数据" (data) / "工具成功但空" (empty) / "工具失败" (error)，
让 LLM 能准确解读执行结果并决定下一步。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """工具执行结果"""

    success: bool
    result_type: str  # "data" | "empty" | "error"
    data: Any = None
    error: str | None = None
    truncated: bool = False
    total_count: int = 0

    @classmethod
    def data_result(cls, data: Any, truncated: bool = False, total_count: int = 0) -> "ToolResult":
        """工具成功且有数据"""
        return cls(
            success=True,
            result_type="data",
            data=data,
            truncated=truncated,
            total_count=total_count or (len(data) if hasattr(data, "__len__") else 0),
        )

    @classmethod
    def empty_result(cls, message: str = "未找到相关信息") -> "ToolResult":
        """工具成功但无结果"""
        return cls(success=True, result_type="empty", data=message)

    @classmethod
    def error_result(cls, error: str) -> "ToolResult":
        """工具执行失败"""
        return cls(success=False, result_type="error", error=error)

    def to_message(self) -> str:
        """转为可注入 LLM 对话的文本"""
        if self.result_type == "error":
            return f"[工具错误] {self.error}"
        if self.result_type == "empty":
            return f"[工具返回] {self.data or '无结果'}"
        prefix = "[工具返回"
        if self.truncated:
            prefix += f"，结果已截断（共 {self.total_count} 条）"
        prefix += "]"
        return f"{prefix}\n{self.data}"
