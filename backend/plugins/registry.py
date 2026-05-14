import logging
from typing import Dict, List, Any, Optional

from backend.plugins.base_tool import BaseTool
from backend.plugins.tool_result import ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册中心"""

    def __init__(self, allowlist: Optional[set] = None):
        self._tools: Dict[str, BaseTool] = {}
        self._allowlist = allowlist  # None=全部通行, set=仅白名单工具

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

    # ── 新标准接口 ──

    def list_tools(self) -> List[dict]:
        """返回标准化的 tool definitions（OpenAI/MCP tools 格式），受 allowlist 约束"""
        definitions = []
        for tool in self.get_all_tools():
            if self._allowlist is not None and tool.name not in self._allowlist:
                continue
            definition = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                },
            }
            if tool.inputSchema:
                definition["function"]["parameters"] = tool.inputSchema
            definitions.append(definition)
        return definitions

    def call_tool(self, name: str, params: dict) -> ToolResult:
        """统一工具调用入口，返回 ToolResult。受 allowlist 约束 + 参数校验"""
        # ── 白名单检查 ──
        if self._allowlist is not None and name not in self._allowlist:
            available = sorted(self._allowlist)
            return ToolResult.error_result(
                f"工具 '{name}' 不在允许列表中。可用工具: {', '.join(available)}"
            )

        tool = self.get_tool(name)
        if not tool:
            available = [t.name for t in self.get_all_tools()
                         if self._allowlist is None or t.name in self._allowlist]
            return ToolResult.error_result(
                f"工具 '{name}' 不存在。可用工具: {', '.join(available)}"
            )

        # ── 参数校验 ──
        err = self._validate_params(tool, params)
        if err:
            return ToolResult.error_result(err)

        try:
            result = tool.execute(**params)
            if isinstance(result, dict):
                # 如果 dict 有 data/total_count/truncated 字段 → 来自新格式工具
                if "data" in result:
                    data_str = str(result["data"])
                    total = result.get("total_count", 0)
                    truncated = result.get("truncated", False)
                    if not data_str or data_str == "None":
                        return ToolResult.empty_result()
                    return ToolResult.data_result(
                        data_str[:2000],
                        truncated=truncated or len(data_str) > 2000,
                        total_count=total,
                    )
                # 旧格式：dict 本身就是数据（如 {"echo": "hello"}）
                return ToolResult.data_result(result)
            return ToolResult.data_result(str(result)[:2000])
        except Exception as e:
            return ToolResult.error_result(f"工具 '{name}' 执行失败: {e}")

    def _validate_params(self, tool: BaseTool, params: dict) -> Optional[str]:
        """校验参数是否符合 inputSchema。返回 None=通过, str=错误信息"""
        schema = tool.inputSchema
        if not schema:
            return None

        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for field in required:
            if field not in params or params[field] is None:
                return f"工具 '{tool.name}' 缺少必填参数: {field}"

        type_map = {"string": str, "integer": int, "number": (int, float),
                     "boolean": bool, "array": list, "object": dict}
        for field, prop in properties.items():
            if field not in params:
                continue
            expected = prop.get("type")
            if not expected or expected not in type_map:
                continue
            expected_type = type_map[expected]
            if not isinstance(params[field], expected_type):
                logger.warning(
                    "[Registry] 参数类型不匹配: %s.%s 期望 %s, 实际 %s",
                    tool.name, field, expected, type(params[field]).__name__
                )

        return None

    # ── 旧接口（向后兼容） ──

    def execute_tool(self, name: str, **kwargs) -> Any:
        """[deprecated] 旧代码的直接执行接口，推荐用 call_tool()"""
        result = self.call_tool(name, kwargs)
        if not result.success:
            raise ValueError(result.error)
        return result.data

    def unregister(self, name: str) -> bool:
        """注销工具，返回是否成功"""
        if name in self._tools:
            del self._tools[name]
            return True
        return False

    def get_legacy_schema(self) -> List[Dict[str, Any]]:
        """[deprecated] 生成旧代码传给 DeepSeek 的 functions 格式"""
        schemas = []
        for tool in self.get_all_tools():
            schema = {
                "name": tool.name,
                "description": tool.description,
            }
            if tool.inputSchema:
                schema["parameters"] = tool.inputSchema
            elif hasattr(tool, "parameters"):
                schema["parameters"] = getattr(tool, "parameters")
            schemas.append(schema)
        return schemas
