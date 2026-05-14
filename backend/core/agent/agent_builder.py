"""
agent_builder — 共享工厂函数

消除 main.py / run_qq.py 之间的重复 DI 代码。
所有模式（local / qq / discord）共享同一套 LLM/Memory/Emotion/Tool/Skill 创建逻辑。
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 核心组件工厂
# ═══════════════════════════════════════════════════════════════


def create_llm():
    """创建默认 LLM（DeepSeek 快速文本）"""
    from backend.core.llm.llm_factory import LLMFactory
    return LLMFactory.get_default()


def create_vision_llm():
    """创建视觉 LLM（Qwen VLM 多模态）"""
    from config import DASHSCOPE_API_KEY, VISION_BASE_URL, VISION_MODEL
    from backend.core.llm.llm_factory import LLMFactory
    return LLMFactory.get(
        api_key=DASHSCOPE_API_KEY,
        base_url=VISION_BASE_URL,
        model=VISION_MODEL,
    )


def create_emotion_engine():
    from backend.core.emotion.emotion_engine import EmotionEngine
    return EmotionEngine()


def create_persona():
    from backend.core.behavior.persona import Persona
    from backend.core.memory import tools
    raw = tools.load_files(["core/personality.md"])
    if raw:
        return Persona.from_markdown(raw)
    return Persona()


def create_prompt_builder(persona):
    from backend.core.behavior.prompt_builder import PromptBuilder
    return PromptBuilder(persona)


def create_memory(llm):
    from backend.core.memory.memory_facade import MemoryFacade
    return MemoryFacade(llm_api=llm)


# ═══════════════════════════════════════════════════════════════
# 工具 & 技能
# ═══════════════════════════════════════════════════════════════


def create_tool_registry(mode: str = "local"):
    """模式特定的工具注册。

    local: 全套工具（含 write_file, run_code, recognize_image）
    qq/discord: 白名单只读 + 日记 + 图片识别
    """
    from backend.plugins.registry import ToolRegistry
    from backend.plugins.builtin.adapters import (
        SearchMemoryAdapter, WriteFileAdapter, ReadFileAdapter,
        SummarizeArchiveAdapter, WriteDiaryAdapter,
        ListDirectoryAdapter, GrepSearchAdapter, WebSearchAdapter,
        RecognizeImageAdapter,
    )

    if mode == "local":
        from backend.plugins.builtin.adapters import RunCodeAdapter
        reg = ToolRegistry()
        reg.register(SearchMemoryAdapter())
        reg.register(WriteFileAdapter())
        reg.register(ReadFileAdapter())
        reg.register(SummarizeArchiveAdapter())
        reg.register(WriteDiaryAdapter())
        reg.register(ListDirectoryAdapter())
        reg.register(GrepSearchAdapter())
        reg.register(WebSearchAdapter())
        reg.register(RecognizeImageAdapter())
        reg.register(RunCodeAdapter())
        return reg

    # qq / discord: 只读白名单 + 文件探索 + 图片识别
    reg = ToolRegistry(allowlist={
        "search_memory", "read_file", "write_diary",
        "list_directory", "grep_search", "web_search",
        "recognize_image",
    })
    reg.register(SearchMemoryAdapter())
    reg.register(ReadFileAdapter())
    reg.register(WriteDiaryAdapter())
    reg.register(ListDirectoryAdapter())
    reg.register(GrepSearchAdapter())
    reg.register(WebSearchAdapter())
    reg.register(RecognizeImageAdapter())
    return reg


def create_skill_manager(llm, registry):
    from backend.core.skill.skill_manager import SkillManager
    mgr = SkillManager(llm=llm, tool_registry=registry)
    count = mgr.load_all()
    logger.info("SkillManager 已加载 %d 个技能", count)
    return mgr


# ═══════════════════════════════════════════════════════════════
# Channel 构建
# ═══════════════════════════════════════════════════════════════


def create_local_channel(dispatcher=None, frontend=None, tts_manager=None, scheduler=None):
    from backend.core.channel.local_channel import LocalChannel
    return LocalChannel(
        dispatcher=dispatcher,
        frontend=frontend,
        tts_manager=tts_manager,
        scheduler=scheduler,
    )


def create_qq_channel(memory=None, emotion=None):
    from backend.core.channel.qq_channel import QQChannel
    return QQChannel(memory=memory, emotion=emotion)


def create_discord_channel(memory=None, emotion=None):
    from backend.core.channel.discord_channel import DiscordChannel
    return DiscordChannel(memory=memory, emotion=emotion)


# ═══════════════════════════════════════════════════════════════
# Pipeline 构建
# ═══════════════════════════════════════════════════════════════


def build_slim_pipeline(llm, memory, emotion, registry, skill_manager, channel,
                        dispatcher=None):
    """构建精简 ThinkPipeline（QQ / Discord 用）。"""
    from backend.core.think_pipeline import (
        ThinkPipeline, MemoryRetrieveStage, PromptBuildStage,
        LLMChatStage, ToolExecStage, FinalizeStage,
        SkillMatchStage,
    )

    setup_stages = [
        MemoryRetrieveStage(
            memory_core=memory,
            emotion_engine=emotion,
            dispatcher=dispatcher,
        ),
        SkillMatchStage(skill_manager=skill_manager),
        PromptBuildStage(),
    ]

    return ThinkPipeline(
        setup_stages=setup_stages,
        llm_stage=LLMChatStage(llm=llm, registry=registry),
        tool_stage=ToolExecStage(registry=registry, channel=channel),
        finalize_stage=FinalizeStage(
            memory_core=memory,
            dispatcher=dispatcher,
            channel=channel,
        ),
    )


# ═══════════════════════════════════════════════════════════════
# Local 模式：完整 DI 容器
# ═══════════════════════════════════════════════════════════════


def build_local_container():
    """构建完整 DI 容器（local 模式）。"""
    from backend.core.container import DIContainer
    from backend.core.event.event_bus import event_bus

    c = DIContainer()

    # ── 基础设施 ──
    c.register_instance("event_bus", event_bus)

    # ── LLM 双实例 ──
    c.register("llm", lambda _: create_llm(), startup_order=1)
    c.register("vision_llm", lambda _: create_vision_llm(), startup_order=1)

    # ── 核心 ──
    c.register("persona", lambda _: create_persona(), startup_order=2)
    c.register("prompt_builder", lambda c_: create_prompt_builder(c_.resolve("persona")), startup_order=2)
    c.register("emotion", lambda _: create_emotion_engine(), startup_order=3)
    c.register("memory", lambda c_: create_memory(c_.resolve("llm")), startup_order=4)

    # ── 工具 & 技能 ──
    c.register("tool_registry", lambda _: create_tool_registry("local"), startup_order=9)
    c.register("skill_manager", lambda c_: create_skill_manager(c_.resolve("llm"), c_.resolve("tool_registry")), startup_order=9)

    # ── Channel ──
    c.register("channel_registry", lambda c_: _make_channel_registry(c_), startup_order=9)

    # ── 本地 AI 组件 ──
    c.register("tts", lambda _: _make_tts_service(), startup_order=5)
    c.register("tts_manager", lambda c_: _make_tts_manager(c_), startup_order=6)
    c.register("frontend", lambda _: _make_frontend(), startup_order=7)
    c.register("response_dispatcher", lambda c_: _make_dispatcher(c_), startup_order=8)
    c.register("drive_model", lambda _: _make_drive_model(), startup_order=10)
    c.register("instinct_handler", lambda c_: _make_instinct_handler(c_), startup_order=11)
    c.register("mumble_handler", lambda c_: _make_mumble_handler(c_), startup_order=11)
    c.register("goal_tracker", lambda c_: _make_goal_tracker(c_), startup_order=12)
    c.register("spontaneous_engine", lambda c_: _make_spontaneous_engine(c_), startup_order=12)
    c.register("visual_observer", lambda c_: _make_visual_observer(c_), startup_order=12)
    c.register("state_machine", lambda _: _make_state_machine(), startup_order=13)
    c.register("think_orchestrator", lambda c_: _make_orchestrator(c_), startup_order=14)
    c.register("agent_scheduler", lambda c_: _make_scheduler(c_), startup_order=15)
    c.register("asr", lambda _: _make_asr(), startup_order=16)
    c.register("ws_server", lambda c_: _make_ws_server(c_), startup_order=17)

    return c


# ── Local 容器内部工厂 ──

def _make_tts_service():
    from backend.services.tts.tts_service import TTSService
    return TTSService()


def _make_tts_manager(c):
    from backend.core.agent.agent_voice import Voice
    from backend.core.agent.tts_manager import TTSManager
    voice = Voice(tts=c.resolve("tts"), llm=c.resolve("llm"))
    voice._ws_server = c.resolve("ws_server")
    return TTSManager(voice=voice, event_bus=c.resolve("event_bus"))


def _make_frontend():
    from backend.core.agent.frontend_bridge import FrontendBridge
    return FrontendBridge(driver=None)


def _make_dispatcher(c):
    from backend.core.think_pipeline.dispatchers import DefaultResponseDispatcher
    return DefaultResponseDispatcher(
        tts_manager=c.resolve("tts_manager"),
        frontend_bridge=c.resolve("frontend"),
    )


def _make_drive_model():
    from backend.core.behavior.drive_model import DriveModel
    return DriveModel()


def _make_instinct_handler(c):
    from backend.core.behavior.instinct_handler import InstinctHandler
    return InstinctHandler(
        llm_api=c.resolve("llm"),
        tts_queue=c.resolve("tts_manager").tts_queue,
        prompt_builder=c.resolve("prompt_builder"),
        drive_model=c.resolve("drive_model"),
    )


def _make_mumble_handler(c):
    from backend.core.behavior.mumble_handler import MumbleHandler
    return MumbleHandler(tts_queue=c.resolve("tts_manager").tts_queue)


def _make_goal_tracker(c):
    from backend.core.spontaneous.goal_tracker import GoalTracker
    return GoalTracker(memory_core=c.resolve("memory"), llm_thinker=c.resolve("llm"))


def _make_spontaneous_engine(c):
    from backend.core.spontaneous.engine import SpontaneousEngine
    return SpontaneousEngine(
        memory_core=c.resolve("memory"),
        llm=c.resolve("llm"),
        goal_tracker=c.resolve("goal_tracker"),
        tts_manager=c.resolve("tts_manager"),
    )


def _make_visual_observer(c):
    from backend.core.vision.visual_observer import VisualObserver
    engine = c.resolve("spontaneous_engine")
    ws = c.resolve("ws_server")
    observer = VisualObserver(engine=engine, ws_server=ws)
    engine._visual_observer = observer
    ws.visual_observer = observer
    return observer


def _make_state_machine():
    from backend.core.state_machine.state_machine import StateMachine
    return StateMachine()


def _make_orchestrator(c):
    from backend.core.agent.think_orchestrator import ThinkOrchestrator
    return ThinkOrchestrator(container=c)


def _make_scheduler(c):
    from backend.core.agent.agent_scheduler import AgentScheduler
    return AgentScheduler(container=c)


def _make_asr():
    from backend.services.asr.speech_recognizer import SpeechRecognizer
    return SpeechRecognizer()


def _make_ws_server(c):
    from backend.api.netwebsocket.ws_server import WSServer
    ws = WSServer()
    ws.send_queue
    ws.set_tts(c.resolve("tts"))
    return ws


def _make_channel_registry(c):
    """构建 ChannelRegistry"""
    from backend.core.channel.base import Channel

    class ChannelRegistry:
        def __init__(self):
            self._channels: dict = {}

        def register(self, ch: Channel):
            self._channels[ch.name] = ch

        def resolve(self, session_id: str) -> Channel:
            for ch in self._channels.values():
                if ch.name == "local":
                    continue
                if session_id and session_id.startswith(f"{ch.name}_"):
                    return ch
            return self._channels.get("local")

    reg = ChannelRegistry()
    reg.register(create_local_channel(
        dispatcher=c.resolve("response_dispatcher"),
        frontend=c.resolve("frontend"),
        tts_manager=c.resolve("tts_manager"),
        scheduler=c.resolve("agent_scheduler"),
    ))
    return reg
