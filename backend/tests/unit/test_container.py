"""DI 容器核心功能测试"""

import pytest
from backend.core.container import DIContainer


class TestDIContainer:
    """DIContainer 单元测试"""

    def test_register_and_resolve(self):
        c = DIContainer()
        c.register("test", lambda _: "hello", startup_order=1)
        assert c.resolve("test") == "hello"

    def test_resolve_is_lazy(self):
        called = []

        def factory(_c):
            called.append(True)
            return "lazy"

        c = DIContainer()
        c.register("lazy", factory, startup_order=1)
        assert len(called) == 0
        result = c.resolve("lazy")
        assert result == "lazy"
        assert len(called) == 1
        # second resolve uses cache
        c.resolve("lazy")
        assert len(called) == 1

    def test_resolve_unregistered_raises(self):
        c = DIContainer()
        with pytest.raises(KeyError):
            c.resolve("nonexistent")

    def test_register_instance(self):
        c = DIContainer()
        obj = {"key": "value"}
        c.register_instance("obj", obj)
        assert c.resolve("obj") is obj

    def test_list_names(self):
        c = DIContainer()
        c.register("a", lambda _: 1, 1)
        c.register("b", lambda _: 2, 2)
        names = c.list_names()
        assert "a" in names
        assert "b" in names
        assert len(names) == 2

    def test_contains(self):
        c = DIContainer()
        c.register("x", lambda _: None, 1)
        assert "x" in c
        assert "y" not in c

    def test_duplicate_register_overwrites(self):
        c = DIContainer()
        c.register("dup", lambda _: 1, 1)
        c.register("dup", lambda _: 2, 2)
        assert c.resolve("dup") == 2
