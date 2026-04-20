#!/usr/bin/env python3
"""
插件体系基类定义

定义统一的插件接口，支持热插拔模块（如TTS、LLM、记忆模块等）。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import importlib


class PluginBase(ABC):
    """插件基类"""

    @abstractmethod
    def initialize(self, config: Dict[str, Any]) -> bool:
        """
        初始化插件

        Args:
            config: 插件配置字典

        Returns:
            bool: 初始化是否成功
        """
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """关闭插件，释放资源"""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """
        获取插件状态

        Returns:
            Dict[str, Any]: 状态信息
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """插件名称"""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """插件版本"""
        pass

    @property
    def enabled(self) -> bool:
        """插件是否启用"""
        return True


class PluginManager:
    """插件管理器"""

    def __init__(self):
        self._plugins: Dict[str, PluginBase] = {}
        self._config: Dict[str, Any] = {}

    def register_plugin(self, plugin: PluginBase) -> bool:
        """注册插件"""
        if plugin.name in self._plugins:
            print(f"[PluginManager] 插件 '{plugin.name}' 已注册，跳过")
            return False

        self._plugins[plugin.name] = plugin
        print(f"[PluginManager] 插件 '{plugin.name}' 注册成功")
        return True

    def load_plugin_from_module(self, module_path: str, class_name: str, plugin_config: Dict[str, Any]) -> bool:
        """
        从模块路径动态加载插件

        Args:
            module_path: 模块路径（如 "services.tts.tts_service"）
            class_name: 类名（如 "TTSService"）
            plugin_config: 插件配置

        Returns:
            bool: 加载是否成功
        """
        try:
            module = importlib.import_module(module_path)
            plugin_class = getattr(module, class_name)
            if not issubclass(plugin_class, PluginBase):
                print(f"[PluginManager] 类 '{class_name}' 不是 PluginBase 的子类")
                return False

            plugin_instance = plugin_class()
            success = plugin_instance.initialize(plugin_config)
            if success:
                self.register_plugin(plugin_instance)
                return True
            else:
                print(f"[PluginManager] 插件 '{class_name}' 初始化失败")
                return False

        except Exception as e:
            print(f"[PluginManager] 加载插件失败 {module_path}.{class_name}: {e}")
            return False

    def get_plugin(self, name: str) -> Optional[PluginBase]:
        """获取插件实例"""
        return self._plugins.get(name)

    def initialize_all(self, config: Dict[str, Any]) -> bool:
        """初始化所有已注册插件"""
        self._config = config
        all_success = True

        for name, plugin in self._plugins.items():
            print(f"[PluginManager] 初始化插件: {name}")
            plugin_config = config.get(name, {})
            if not plugin.initialize(plugin_config):
                print(f"[PluginManager] 插件 '{name}' 初始化失败")
                all_success = False

        return all_success

    def shutdown_all(self) -> None:
        """关闭所有插件"""
        for name, plugin in self._plugins.items():
            try:
                plugin.shutdown()
                print(f"[PluginManager] 插件 '{name}' 已关闭")
            except Exception as e:
                print(f"[PluginManager] 关闭插件 '{name}' 失败: {e}")

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有插件状态"""
        status = {}
        for name, plugin in self._plugins.items():
            status[name] = plugin.get_status()
        return status


# 全局插件管理器实例
_global_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """获取全局插件管理器"""
    global _global_plugin_manager
    if _global_plugin_manager is None:
        _global_plugin_manager = PluginManager()
    return _global_plugin_manager