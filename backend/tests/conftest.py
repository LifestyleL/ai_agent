"""
pytest 全局 fixtures

提供 mock LLM、mock TTS、DI 容器等测试基础设施。
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, AsyncMock

# 确保 backend/ 在 path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def mock_llm():
    """返回一个 mock LLM API 实例"""
    llm = MagicMock()
    llm.ask.return_value = "这是一个测试回复。"
    llm.chat.return_value = {
        "choices": [{"message": {"content": "测试回复"}}]
    }
    llm.ask_with_system.return_value = "带 system prompt 的测试回复。"
    return llm


@pytest.fixture
def mock_tts_queue():
    """返回一个 mock TTS 队列"""
    import queue
    return queue.Queue()


@pytest.fixture
def mock_event_bus():
    """返回一个 mock EventBus"""
    from unittest.mock import MagicMock
    bus = MagicMock()
    bus.subscribe = MagicMock()
    bus.publish = MagicMock()
    return bus


@pytest.fixture
def mock_persona():
    """返回一个默认 Persona 实例"""
    from backend.core.behavior.persona import Persona
    return Persona()


@pytest.fixture
def mock_prompt_builder(mock_persona):
    """返回一个 PromptBuilder"""
    from backend.core.behavior.prompt_builder import PromptBuilder
    return PromptBuilder(mock_persona)


@pytest.fixture
def test_container(mock_llm, mock_tts_queue, mock_persona, mock_prompt_builder):
    """返回一个预配置的 DI 容器（仅含核心模块）"""
    from backend.core.container import DIContainer
    from backend.core.emotion.emotion_engine import EmotionEngine
    from backend.core.behavior.drive_model import DriveModel

    c = DIContainer()
    c.register_instance("llm", mock_llm)
    c.register_instance("persona", mock_persona)
    c.register_instance("prompt_builder", mock_prompt_builder)
    c.register_instance("emotion", EmotionEngine())
    c.register("drive_model", lambda _: DriveModel(), startup_order=10)
    return c
