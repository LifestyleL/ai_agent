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
