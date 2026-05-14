"""工具注册/执行测试"""

import pytest
from unittest.mock import MagicMock


class TestToolRegistry:
    """ToolRegistry 注册与执行"""

    def test_register_and_get_tool(self):
        from backend.plugins.registry import ToolRegistry
        from backend.plugins.base_tool import BaseTool

        class FakeTool(BaseTool):
            name = "fake_tool"
            description = "测试工具"

            def execute(self, **kwargs):
                return {"result": "ok"}

        reg = ToolRegistry()
        reg.register(FakeTool())

        tool = reg.get_tool("fake_tool")
        assert tool is not None
        assert tool.name == "fake_tool"

    def test_get_nonexistent_tool(self):
        from backend.plugins.registry import ToolRegistry
        reg = ToolRegistry()
        assert reg.get_tool("nonexistent") is None

    def test_execute_tool(self):
        from backend.plugins.registry import ToolRegistry
        from backend.plugins.base_tool import BaseTool

        class EchoTool(BaseTool):
            name = "echo"
            description = "回显"

            def execute(self, **kwargs):
                return {"echo": kwargs.get("text", "")}

        reg = ToolRegistry()
        reg.register(EchoTool())
        result = reg.execute_tool("echo", text="hello")
        assert result == {"echo": "hello"}

    def test_get_all_tools(self):
        from backend.plugins.registry import ToolRegistry
        from backend.plugins.base_tool import BaseTool

        class Tool1(BaseTool):
            name = "t1"
            description = ""

            def execute(self, **kwargs):
                return {}

        class Tool2(BaseTool):
            name = "t2"
            description = ""

            def execute(self, **kwargs):
                return {}

        reg = ToolRegistry()
        reg.register(Tool1())
        reg.register(Tool2())

        all_tools = reg.get_all_tools()
        assert len(all_tools) == 2
        names = {t.name for t in all_tools}
        assert names == {"t1", "t2"}

    # ── 新接口测试 ──

    def test_list_tools_returns_openai_format(self):
        from backend.plugins.registry import ToolRegistry
        from backend.plugins.base_tool import BaseTool

        class SchemaTool(BaseTool):
            name = "search"
            description = "搜索记忆"
            inputSchema = {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            }

            def execute(self, **kwargs):
                return {"data": "ok"}

        reg = ToolRegistry()
        reg.register(SchemaTool())
        tools = reg.list_tools()
        assert len(tools) == 1
        assert tools[0]["type"] == "function"
        assert tools[0]["function"]["name"] == "search"
        assert "parameters" in tools[0]["function"]

    def test_call_tool_with_valid_name(self):
        from backend.plugins.registry import ToolRegistry
        from backend.plugins.base_tool import BaseTool
        from backend.plugins.tool_result import ToolResult

        class AddTool(BaseTool):
            name = "add"
            description = "加法"

            def execute(self, **kwargs):
                return {"data": kwargs["a"] + kwargs["b"]}

        reg = ToolRegistry()
        reg.register(AddTool())
        result = reg.call_tool("add", {"a": 1, "b": 2})
        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.result_type == "data"
        assert "3" in str(result.data)

    def test_call_tool_with_invalid_name_returns_error(self):
        from backend.plugins.registry import ToolRegistry

        reg = ToolRegistry()
        result = reg.call_tool("nonexistent_tool", {})
        assert result.success is False
        assert result.result_type == "error"
        assert "不存在" in result.error
        assert "可用工具" in result.error

    def test_call_tool_empty_result_when_no_data(self):
        from backend.plugins.registry import ToolRegistry
        from backend.plugins.base_tool import BaseTool
        from backend.plugins.tool_result import ToolResult

        class EmptyTool(BaseTool):
            name = "empty_search"
            description = ""

            def execute(self, **kwargs):
                return {"data": ""}

        reg = ToolRegistry()
        reg.register(EmptyTool())
        result = reg.call_tool("empty_search", {})
        assert result.success is True
        assert result.result_type == "empty"

    def test_tool_result_truncated(self):
        from backend.plugins.registry import ToolRegistry
        from backend.plugins.base_tool import BaseTool
        from backend.plugins.tool_result import ToolResult

        class BigTool(BaseTool):
            name = "big_data"
            description = ""

            def execute(self, **kwargs):
                return {"data": "x" * 2500, "total_count": 100, "truncated": True}

        reg = ToolRegistry()
        reg.register(BigTool())
        result = reg.call_tool("big_data", {})
        assert result.truncated is True
        assert result.total_count == 100
        assert len(str(result.data)) <= 2000

    def test_legacy_execute_tool_still_works(self):
        from backend.plugins.registry import ToolRegistry
        from backend.plugins.base_tool import BaseTool

        class OldStyleTool(BaseTool):
            name = "old_style"
            description = ""

            def execute(self, **kwargs):
                return {"result": "ok", "value": 42}

        reg = ToolRegistry()
        reg.register(OldStyleTool())
        result = reg.execute_tool("old_style", param1="x")
        assert isinstance(result, dict)
        assert result["result"] == "ok"

    # ── Phase 5: 白名单测试 ──

    def test_allowlist_allows_listed_tool(self):
        """白名单内的工具正常执行"""
        from backend.plugins.registry import ToolRegistry
        from backend.plugins.base_tool import BaseTool

        class A(BaseTool):
            name = "read_file"
            description = ""
            def execute(self, **kwargs):
                return {"data": "file content"}

        reg = ToolRegistry(allowlist={"read_file"})
        reg.register(A())
        result = reg.call_tool("read_file", {})
        assert result.success is True

    def test_allowlist_rejects_unlisted_tool(self):
        """白名单外的工具被拒绝"""
        from backend.plugins.registry import ToolRegistry
        from backend.plugins.base_tool import BaseTool

        class A(BaseTool):
            name = "write_file"
            description = ""
            def execute(self, **kwargs):
                return {"data": "ok"}

        reg = ToolRegistry(allowlist={"read_file"})
        reg.register(A())
        result = reg.call_tool("write_file", {})
        assert result.success is False
        assert "不在允许列表中" in result.error

    def test_allowlist_filters_list_tools(self):
        """list_tools() 只返回白名单工具"""
        from backend.plugins.registry import ToolRegistry
        from backend.plugins.base_tool import BaseTool

        class A(BaseTool):
            name = "read_file"
            description = ""
            def execute(self, **kwargs):
                return {}

        class B(BaseTool):
            name = "write_file"
            description = ""
            def execute(self, **kwargs):
                return {}

        reg = ToolRegistry(allowlist={"read_file"})
        reg.register(A())
        reg.register(B())
        tools = reg.list_tools()
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "read_file"

    def test_no_allowlist_allows_all_tools(self):
        """无白名单时所有工具可调用"""
        from backend.plugins.registry import ToolRegistry
        from backend.plugins.base_tool import BaseTool

        class A(BaseTool):
            name = "any_tool"
            description = ""
            def execute(self, **kwargs):
                return {"data": "ok"}

        reg = ToolRegistry()  # no allowlist
        reg.register(A())
        result = reg.call_tool("any_tool", {})
        assert result.success is True

    def test_allowlist_error_message_lists_available(self):
        """白名单拒绝消息包含可用工具列表"""
        from backend.plugins.registry import ToolRegistry
        from backend.plugins.base_tool import BaseTool

        class A(BaseTool):
            name = "blocked"
            description = ""
            def execute(self, **kwargs):
                return {}

        reg = ToolRegistry(allowlist={"read_file", "search_memory"})
        reg.register(A())
        result = reg.call_tool("blocked", {})
        assert "read_file" in result.error
        assert "search_memory" in result.error

    # ── Phase 5: 参数校验测试 ──

    def test_validate_required_params_missing(self):
        """缺少必填参数时返回错误"""
        from backend.plugins.registry import ToolRegistry
        from backend.plugins.base_tool import BaseTool

        class NeedKey(BaseTool):
            name = "need_key"
            description = ""
            inputSchema = {
                "type": "object",
                "properties": {"keyword": {"type": "string"}},
                "required": ["keyword"],
            }
            def execute(self, **kwargs):
                return {"data": "ok"}

        reg = ToolRegistry()
        reg.register(NeedKey())
        result = reg.call_tool("need_key", {})  # 缺少 keyword
        assert result.success is False
        assert "缺少必填参数" in result.error
        assert "keyword" in result.error

    def test_validate_no_schema_skips(self):
        """无 inputSchema 的工具跳过校验"""
        from backend.plugins.registry import ToolRegistry
        from backend.plugins.base_tool import BaseTool

        class NoSchema(BaseTool):
            name = "no_schema"
            description = ""
            def execute(self, **kwargs):
                return {"data": "ok"}

        reg = ToolRegistry()
        reg.register(NoSchema())
        result = reg.call_tool("no_schema", {"anything": 1})
        assert result.success is True
