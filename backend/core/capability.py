"""
统一 Capability 协议 — 所有可插拔模块的基础接口

每个模块（ASR/TTS/Memory/Emotion/Tools/Skills 等）必须实现此协议，
从而被 DIContainer 和 AgentScheduler 统一管理。

窄接口（TTSCapability, ASRCapability 等）供类型检查和编译期约束使用，
不强制继承——依赖方只依赖窄接口而非具体类。
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from .container import DIContainer


class Capability(ABC):
    """所有模块的统一生命周期协议"""

    @property
    @abstractmethod
    def name(self) -> str:
        """唯一标识，如 'tts', 'asr', 'memory', 'emotion'"""
        ...

    @property
    @abstractmethod
    def version(self) -> str:
        """语义化版本号"""
        ...

    @property
    def enabled(self) -> bool:
        """是否启用。支持运行时禁用某个能力。"""
        return True

    @abstractmethod
    async def initialize(self, container: "DIContainer") -> None:
        """
        异步初始化：连接外部服务、加载数据等。
        由 DIContainer 在 initialize_all() 中按 startup_order 调用。
        """
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """
        优雅关闭：释放连接、刷盘数据等。
        由 DIContainer 在 shutdown_all() 中按逆序调用。
        """
        ...

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """返回当前状态快照，供监控/调试用"""
        ...


# ── 窄接口（Narrow Protocols）──
# 依赖方应依赖这些窄接口而非具体实现类。
# 以下用 ABC 定义（Python 3.10 兼容），
# 后续升级 3.12+ 可迁移到 typing.Protocol。


class TTSCapability(Capability, ABC):
    """TTS 窄接口：只暴露合成能力，不关心音频发往哪里"""

    @abstractmethod
    def synthesize(self, text: str, emotion: str = "neutral") -> bytes:
        """同步合成，返回 PCM 音频字节"""
        ...

    @abstractmethod
    def synthesize_with_visemes(self, text: str, emotion: str = "neutral") -> tuple:
        """合成并返回 (pcm_bytes, viseme_frames)"""
        ...


class ASRCapability(Capability, ABC):
    """ASR 窄接口：只通过回调产出文本，不关心 WebSocket"""

    @abstractmethod
    def set_result_callback(self, callback) -> None:
        """注册识别回调 callback(text: str, is_final: bool)"""
        ...

    @abstractmethod
    async def start_listening(self) -> None:
        """开始监听"""
        ...

    @abstractmethod
    async def stop_listening(self) -> None:
        """停止监听"""
        ...

    @abstractmethod
    def feed_audio(self, audio_bytes: bytes) -> None:
        """喂入音频数据"""
        ...


class MemoryCapability(Capability, ABC):
    """记忆系统窄接口"""

    @abstractmethod
    def add_short_term(self, role: str, content: str) -> None:
        """添加短期记忆"""
        ...

    @abstractmethod
    def get_short_term_context(self, max_turns: int = 20) -> str:
        """获取短期上下文文本"""
        ...

    @abstractmethod
    def search(self, keyword: str, limit: int = 5) -> str:
        """搜索记忆"""
        ...

    @abstractmethod
    def flush(self) -> None:
        """强制刷盘"""
        ...

    @abstractmethod
    def build_structured_sections(self, user_input: str, deep_recall: str = "") -> Dict[str, Any]:
        """构建结构化记忆分区"""
        ...

    @abstractmethod
    def check_cross_day_diary(self) -> None:
        """跨天日记检查"""
        ...

    @abstractmethod
    def detect_activity_type(self, text: str) -> str:
        """检测活动类型"""
        ...

    @abstractmethod
    def get_time_context(self) -> str:
        """获取时间上下文"""
        ...


class EmotionCapability(Capability, ABC):
    """情绪引擎窄接口"""

    @abstractmethod
    def infer_from_text(self, text: str) -> tuple:
        """从文本推断情绪 (type, strength)"""
        ...

    @abstractmethod
    def update_emotion(self, etype: int, strength: float) -> None:
        """更新情绪状态"""
        ...

    @abstractmethod
    def get_emotion_label(self) -> str:
        """返回当前情绪标签 (neutral/happy/sad/angry)"""
        ...

    @abstractmethod
    def get_emotion_dict(self) -> Dict[str, Any]:
        """返回当前情绪字典"""
        ...

    @abstractmethod
    def drift(self) -> None:
        """情绪基线回归"""
        ...
