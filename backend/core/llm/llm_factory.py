"""
LLMFactory: LLMAPI 单例工厂

确保相同的 (base_url, model) 组合只创建一次，统一管理连接池。
禁止直接 LLMAPI(...)，所有实例必须通过工厂获取。
"""

import threading
from typing import Optional

import config
from core.llm.llm_api import LLMAPI


class LLMFactory:
    """LLM 实例工厂（线程安全）"""

    _instances: dict = {}
    _lock = threading.Lock()

    @classmethod
    def get(cls, api_key: str, base_url: str, model: str) -> LLMAPI:
        """获取或创建 LLMAPI 实例（按 base_url:model 去重）"""
        key = f"{base_url}:{model}"
        with cls._lock:
            if key not in cls._instances:
                cls._instances[key] = LLMAPI(
                    api_key=api_key,
                    base_url=base_url,
                    model=model,
                )
        return cls._instances[key]

    @classmethod
    def get_default(cls) -> LLMAPI:
        """获取默认 DeepSeek 实例（覆盖 90% 调用场景）"""
        return cls.get(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            model=config.DEEPSEEK_MODEL,
        )

    @classmethod
    def reset(cls):
        """重置工厂（仅测试用）"""
        with cls._lock:
            cls._instances.clear()
