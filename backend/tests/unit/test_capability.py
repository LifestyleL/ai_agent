"""Capability 协议定义测试"""

import pytest
from backend.core.capability import (
    Capability, TTSCapability, ASRCapability,
    MemoryCapability, EmotionCapability,
)


class _MinimalCapability(Capability):
    name = "test"
    version = "1.0"

    async def initialize(self, container):
        pass

    async def shutdown(self):
        pass

    def get_status(self):
        return {"ok": True}


class TestCapabilityProtocol:
    """验证 Capability ABC 约束"""

    def test_cannot_instantiate_abc_directly(self):
        with pytest.raises(TypeError):
            Capability()

    def test_minimal_implementation(self):
        cap = _MinimalCapability()
        assert cap.name == "test"
        assert cap.version == "1.0"
        assert cap.enabled is True
        assert cap.get_status() == {"ok": True}

    def test_disabled_capability(self):
        cap = _MinimalCapability()

        # enabled 默认 True，但可以被覆盖
        class Disabled(_MinimalCapability):
            @property
            def enabled(self):
                return False

        d = Disabled()
        assert d.enabled is False


class TestEmotionCapability:
    """EmotionEngine 满足 EmotionCapability 协议"""

    def test_emotion_engine_satisfies_capability(self):
        from backend.core.emotion.emotion_engine import EmotionEngine
        e = EmotionEngine()
        assert e.name == "emotion"
        assert e.version == "2.0"
        assert e.enabled is True
        status = e.get_status()
        assert "type" in status
        assert "strength" in status


class TestMemoryCapability:
    """MemoryFacade 满足 MemoryCapability 协议"""

    def test_memory_facade_satisfies_capability(self):
        from backend.core.memory.memory_facade import MemoryFacade
        assert MemoryFacade.name == "memory"
        assert MemoryFacade.version == "5.1"
