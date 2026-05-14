"""
轻量 DI 容器 — 无外部依赖，~80 行

职责：
- 按名称注册能力（工厂函数或预构建实例）
- 懒解析（首次 resolve 时执行工厂）
- 按 startup_order 初始化所有能力
- 按逆序关闭所有能力
- 支持嵌套 resolve（工厂接收容器做依赖查找）
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from .capability import Capability

logger = logging.getLogger(__name__)

Factory = Callable[["DIContainer"], Any]


class _Entry:
    """单个注册项（内部使用）"""
    __slots__ = ("factory", "startup_order", "_instance")

    def __init__(self, factory: Factory, startup_order: int):
        self.factory = factory
        self.startup_order = startup_order
        self._instance: Optional[Any] = None


class DIContainer:
    """
    轻量 DI 容器

    用法:
        c = DIContainer()
        c.register("llm", lambda _: LLMFactory.get_default(), startup_order=1)
        c.register("memory", lambda c_: MemoryFacade(llm_api=c_.resolve("llm")), 4)

        await c.initialize_all()
        mem = c.resolve("memory")
        await c.shutdown_all()
    """

    def __init__(self):
        self._entries: Dict[str, _Entry] = {}
        self._initialized = False

    # ── 注册 ──

    def register(self, name: str, factory: Factory, startup_order: int = 100) -> None:
        """
        注册一个能力（工厂函数）

        Args:
            name: 唯一标识
            factory: 接收 DIContainer，返回实例
            startup_order: 初始化顺序（越小越先初始化）
        """
        if name in self._entries:
            logger.warning("[Container] 重复注册 '%s'，覆盖旧条目", name)
        self._entries[name] = _Entry(factory, startup_order)
        logger.debug("[Container] 注册: %s (order=%s)", name, startup_order)

    def register_instance(self, name: str, instance: Any) -> None:
        """
        注册预构建实例（如 EventBus 全局单例）

        实例不参与 initialize/shutdown 自动流程——调用者自行管理生命周期。
        """
        entry = _Entry(lambda _: instance, startup_order=0)
        entry._instance = instance
        self._entries[name] = entry
        logger.debug("[Container] 注册实例: %s", name)

    # ── 解析 ──

    def resolve(self, name: str) -> Any:
        """
        懒解析：首次调用执行工厂，后续返回缓存实例。

        Raises:
            KeyError: 名称未注册
        """
        entry = self._entries.get(name)
        if entry is None:
            raise KeyError(f"[Container] 未注册: '{name}'")
        if entry._instance is None:
            entry._instance = entry.factory(self)
            logger.debug("[Container] 解析: %s -> %s", name, type(entry._instance).__name__)
        return entry._instance

    # ── 生命周期 ──

    async def initialize_all(self) -> None:
        """按 startup_order 升序初始化所有 Capability（幂等）"""
        if self._initialized:
            return
        ordered = sorted(self._entries.items(), key=lambda x: x[1].startup_order)
        for name, entry in ordered:
            instance = self.resolve(name)
            if isinstance(instance, Capability):
                try:
                    logger.info("[Container] 初始化: %s", name)
                    await instance.initialize(self)
                except Exception as e:
                    logger.error("[Container] 初始化失败: %s — %s", name, e)
                    raise
        self._initialized = True

    async def shutdown_all(self) -> None:
        """按 startup_order 逆序关闭所有 Capability"""
        ordered = sorted(self._entries.items(), key=lambda x: -x[1].startup_order)
        for name, entry in ordered:
            instance = entry._instance
            if instance is not None and isinstance(instance, Capability):
                try:
                    logger.info("[Container] 关闭: %s", name)
                    await instance.shutdown()
                except Exception as e:
                    logger.warning("[Container] 关闭异常: %s — %s", name, e)
        self._initialized = False

    # ── 查询 ──

    def get_all_status(self) -> Dict[str, Any]:
        """收集所有 Capability 状态"""
        result = {}
        for name, entry in self._entries.items():
            instance = entry._instance
            if instance is not None and isinstance(instance, Capability):
                try:
                    result[name] = instance.get_status()
                except Exception as e:
                    result[name] = {"error": str(e)}
        return result

    def list_names(self) -> List[str]:
        """列出所有注册名称"""
        return list(self._entries.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._entries
