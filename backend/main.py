"""
main.py — AI Agent 入口

新架构（USE_NEW_ARCH=true）：声明式 DI 容器装配，AgentScheduler 门面。
旧架构（默认）：YumeDriver 直接装配（过渡期保留）。
"""

import asyncio
import os
import signal
import sys
import threading
import time


def _ensure_path():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)


_ensure_path()

from api.netwebsocket.ws_server import WSServer
from config import WS_PORT, validate_config

_shutdown_requested = False


# ═══════════════════════════════════════════════════════════════
# 新架构：声明式容器装配
# ═══════════════════════════════════════════════════════════════


def _build_container():
    """声明式 DI 容器装配"""
    from backend.core.container import DIContainer
    from backend.core.event.event_bus import event_bus

    c = DIContainer()

    # ── 基础设施（startup_order 0） ──
    c.register_instance("event_bus", event_bus)

    # ── LLM 单实例 ──
    c.register("llm", lambda _: _make_llm(), startup_order=1)

    # ── 纯数据 ──
    c.register("persona", lambda _: _make_persona(), startup_order=2)
    c.register("prompt_builder", lambda c_: _make_prompt_builder(c_), startup_order=2)

    # ── 引擎 ──
    c.register("emotion", lambda _: _make_emotion_engine(), startup_order=3)
    c.register("memory", lambda c_: _make_memory(c_), startup_order=4)

    # ── TTS ──
    c.register("tts", lambda _: _make_tts_service(), startup_order=5)
    c.register("tts_manager", lambda c_: _make_tts_manager(c_), startup_order=6)

    # ── 前端桥接 ──
    c.register("frontend", lambda _: _make_frontend(), startup_order=7)
    c.register("response_dispatcher", lambda c_: _make_dispatcher(c_), startup_order=8)

    # ── 工具 & 技能 ──
    c.register("tool_registry", lambda _: _build_tool_registry(), startup_order=9)

    # ── 行为模型 ──
    c.register("drive_model", lambda _: _make_drive_model(), startup_order=10)
    c.register("instinct_handler", lambda c_: _make_instinct_handler(c_), startup_order=11)
    c.register("mumble_handler", lambda c_: _make_mumble_handler(c_), startup_order=11)

    # ── 自驱动 ──
    c.register("goal_tracker", lambda c_: _make_goal_tracker(c_), startup_order=12)
    c.register("spontaneous_engine", lambda c_: _make_spontaneous_engine(c_), startup_order=12)
    c.register("visual_observer", lambda c_: _make_visual_observer(c_), startup_order=12)

    # ── 调度核心 ──
    c.register("state_machine", lambda _: _make_state_machine(), startup_order=13)
    c.register("think_orchestrator", lambda c_: _make_orchestrator(c_), startup_order=14)
    c.register("agent_scheduler", lambda c_: _make_scheduler(c_), startup_order=15)

    # ── IO ──
    c.register("asr", lambda _: _make_asr(), startup_order=16)
    c.register("ws_server", lambda c_: _make_ws_server(c_), startup_order=17)

    return c


# ── 工厂函数 ──


def _make_llm():
    from backend.core.llm.llm_factory import LLMFactory
    return LLMFactory.get_default()


def _make_persona():
    from backend.core.behavior.persona import Persona
    from backend.core.memory import tools
    raw = tools.load_files(["core/personality.md"])
    if raw:
        return Persona.from_markdown(raw)
    return Persona()


def _make_prompt_builder(c):
    from backend.core.behavior.prompt_builder import PromptBuilder
    return PromptBuilder(c.resolve("persona"))


def _make_emotion_engine():
    from backend.core.emotion.emotion_engine import EmotionEngine
    return EmotionEngine()


def _make_memory(c):
    from backend.core.memory.memory_facade import MemoryFacade
    return MemoryFacade(llm_api=c.resolve("llm"))


def _make_tts_service():
    from backend.services.tts.tts_service import TTSService
    return TTSService()


def _make_tts_manager(c):
    from backend.core.agent.agent_voice import Voice
    from backend.core.agent.tts_manager import TTSManager
    voice = Voice(tts=c.resolve("tts"), llm=c.resolve("llm"))
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


def _build_tool_registry():
    from backend.plugins.registry import ToolRegistry
    from backend.plugins.builtin.adapters import (
        SearchMemoryAdapter, WriteFileAdapter, ReadFileAdapter,
        SummarizeArchiveAdapter, WriteDiaryAdapter,
    )
    reg = ToolRegistry()
    reg.register(SearchMemoryAdapter())
    reg.register(WriteFileAdapter())
    reg.register(ReadFileAdapter())
    reg.register(SummarizeArchiveAdapter())
    reg.register(WriteDiaryAdapter())
    return reg


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
    ws = WSServer()
    ws.send_queue  # ensure initialized
    return ws


# ═══════════════════════════════════════════════════════════════
# 新架构启动
# ═══════════════════════════════════════════════════════════════


async def _start_new_architecture():
    """使用 DI 容器 + AgentScheduler 启动"""
    global _shutdown_requested

    validate_config()

    container = _build_container()
    print(f"[Main] DI 容器已创建，注册 {len(container.list_names())} 个能力")

    scheduler = container.resolve("agent_scheduler")
    await scheduler.start()

    # 连接 send_queue
    ws_server = container.resolve("ws_server")
    frontend = container.resolve("frontend")
    tts_manager = container.resolve("tts_manager")
    frontend.send_queue = ws_server.send_queue
    if hasattr(tts_manager, 'voice'):
        tts_manager.voice.send_queue = ws_server.send_queue

    # 启动 WebSocket
    try:
        server = await ws_server.start_server()
        print(f"\n[OK] 系统就绪！前端连接 ws://localhost:{WS_PORT} | 终端直接打字对话\n")
    except Exception as e:
        print(f"[ERROR] WebSocket 启动失败: {e}")
        sys.exit(1)

    # 终端输入线程
    loop = asyncio.get_running_loop()
    stdin_stop = threading.Event()

    def stdin_loop():
        print()
        print("[CHAT] ================================")
        print("[CHAT]   在这里直接打字按回车即可对话")
        print("[CHAT] ================================")
        print()
        while not stdin_stop.is_set():
            try:
                text = input("user：")
                if text.strip() == "/trigger":
                    se = container.resolve("spontaneous_engine")
                    if se:
                        asyncio.run_coroutine_threadsafe(se.manual_trigger_async(), loop)
                        print("[TEST] 已调度手动自驱动触发")
                    continue
                if text.strip() == "/spstatus":
                    se = container.resolve("spontaneous_engine")
                    if se:
                        status = se.get_status()
                        print(f"[自驱动] 运行中: {status.get('is_running')}, 沉默: {status.get('silence_duration', 0)/60:.1f}min")
                    continue
                if text.strip():
                    scheduler.handle_user_input(text.strip())
            except EOFError:
                break
            except Exception as e:
                print(f"[ERROR] 输入异常: {e}")

    threading.Thread(target=stdin_loop, daemon=True).start()

    # 信号处理
    shutdown_event = asyncio.Event()

    def _on_signal(signum, frame):
        global _shutdown_requested
        if _shutdown_requested:
            return
        _shutdown_requested = True
        print("\n[STOP] 收到退出信号，正在优雅关闭...")
        loop.call_soon_threadsafe(shutdown_event.set)

    try:
        signal.signal(signal.SIGINT, _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)
    except ValueError:
        pass

    await shutdown_event.wait()

    # 优雅关闭
    print("[STOP] 正在关闭 WebSocket 服务...")
    try:
        server.close()
        await asyncio.wait_for(server.wait_closed(), timeout=3)
    except Exception as e:
        print(f"[STOP] WebSocket 关闭: {e}")

    print("[STOP] 正在停止终端输入...")
    stdin_stop.set()

    print("[STOP] 正在停止 Agent...")
    await scheduler.shutdown()

    print("[OK] 系统已关闭")
    os._exit(0)


# ═══════════════════════════════════════════════════════════════
# 旧架构启动（过渡期保留）
# ═══════════════════════════════════════════════════════════════


async def _start_legacy_architecture():
    """旧版 YumeDriver 路径，原始代码保留"""
    from core.state_machine.state_machine import StateMachine, State, Event
    from core.state_machine.transitions import setup_base_transitions
    from core.state_machine.actions import create_real_think_action, create_real_do_tool_action
    from backend.plugins.registry import ToolRegistry
    from backend.core.llm.llm_factory import LLMFactory
    from backend.plugins.builtin.adapters import (
        SearchMemoryAdapter, WriteFileAdapter, ReadFileAdapter,
        SummarizeArchiveAdapter, WriteDiaryAdapter,
    )

    global _shutdown_requested

    ws_instance = WSServer()
    validate_config()

    llm_deepseek = LLMFactory.get_default()

    print("=" * 50)
    print("[1] [主线程] 准备拉起 Agent 后台线程...")
    print("=" * 50)

    try:
        from core.agent.agent_driver import YumeDriver
        driver = YumeDriver()
        ws_instance.driver = driver

        driver.frontend.send_queue = ws_instance.send_queue
        driver.voice.send_queue = ws_instance.send_queue

        print("[Main] 配置状态机（真实引擎模式）...")
        sm = StateMachine()
        ws_instance.state_machine = sm
        setup_base_transitions(sm)

        print("[Main] 工具系统插件化注册...")
        reg = ToolRegistry()
        ws_instance.tool_registry = reg
        reg.register(SearchMemoryAdapter())
        reg.register(WriteFileAdapter())
        reg.register(ReadFileAdapter())
        reg.register(SummarizeArchiveAdapter())
        reg.register(WriteDiaryAdapter())
        driver.tool_registry = reg
        print(f"[Main] 工具注册完成，已注册 {len(reg.get_all_tools())} 个工具")

        # 视觉观察器（VLM 多模态）
        if hasattr(driver, 'spontaneous_engine') and driver.spontaneous_engine:
            from backend.core.vision.visual_observer import VisualObserver
            observer = VisualObserver(engine=driver.spontaneous_engine, ws_server=ws_instance)
            driver.spontaneous_engine._visual_observer = observer
            ws_instance.visual_observer = observer
            print("[Main] VisualObserver 已挂载")

        print("[Main] 绑定真实 Action 引擎...")
        real_think = create_real_think_action(
            state_machine=sm, registry=reg, driver_instance=driver, llm_deepseek=llm_deepseek)
        real_do_tool = create_real_do_tool_action(state_machine=sm, registry=reg, llm_deepseek=llm_deepseek)
        sm.register_action(State.THINK, real_think)
        sm.register_action(State.DO_TOOL, real_do_tool)
        driver.state_machine = sm

        print("=" * 50)
        print("[2] [主线程] 启动 Agent 独白守护...")
        print("=" * 50)
        driver.start()
    except Exception as e:
        print(f"[ERROR] Agent 启动失败: {e}")
        sys.exit(1)

    loop = asyncio.get_running_loop()

    stdin_stop = threading.Event()

    def stdin_loop():
        print()
        print("[CHAT] ================================")
        print("[CHAT]   在这里直接打字按回车即可对话")
        print("[CHAT] ================================")
        print()
        while not stdin_stop.is_set():
            try:
                text = input("user：")
                if text.strip() == "/trigger":
                    if hasattr(driver, 'spontaneous_engine') and driver.spontaneous_engine:
                        coro = driver.spontaneous_engine.manual_trigger_async()
                        asyncio.run_coroutine_threadsafe(coro, loop)
                        print("[TEST] 已调度手动自驱动触发")
                    continue
                if text.strip() == "/spstatus":
                    if hasattr(driver, 'spontaneous_engine') and driver.spontaneous_engine:
                        status = driver.spontaneous_engine.get_status()
                        print(f"[自驱动] 沉默: {status.get('silence_duration', 0)/60:.1f}min")
                    continue
                if text.strip():
                    if hasattr(driver, 'state_machine'):
                        coro = driver.state_machine.trigger(Event.USER_INPUT, {"user_input": text.strip()})
                        asyncio.run_coroutine_threadsafe(coro, loop)
                    else:
                        driver.handle_user_input(text.strip())
            except EOFError:
                break
            except Exception as e:
                print(f"[ERROR] 输入异常: {e}")

    print("=" * 50)
    print(f"[3] [主线程] 准备开启 WebSocket {WS_PORT} 端口...")
    print("=" * 50)
    try:
        server = await ws_instance.start_server()
        print(f"\n[OK] 系统就绪！前端连接 ws://localhost:{WS_PORT} | 终端直接打字对话\n")
    except Exception as e:
        print(f"[ERROR] WebSocket 启动失败: {e}")
        sys.exit(1)

    threading.Thread(target=stdin_loop, daemon=True).start()

    shutdown_event = asyncio.Event()

    def _on_signal(signum, frame):
        global _shutdown_requested
        if _shutdown_requested:
            return
        _shutdown_requested = True
        print("\n[STOP] 收到退出信号，正在优雅关闭...")
        loop.call_soon_threadsafe(shutdown_event.set)

    try:
        signal.signal(signal.SIGINT, _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)
    except ValueError:
        pass

    await shutdown_event.wait()

    print("[STOP] 正在关闭 WebSocket 服务...")
    try:
        server.close()
        await asyncio.wait_for(server.wait_closed(), timeout=3)
    except Exception as e:
        print(f"[STOP] WebSocket 关闭: {e}")

    print("[STOP] 正在停止终端输入...")
    stdin_stop.set()

    print("[STOP] 正在停止 Agent...")
    try:
        await asyncio.wait_for(asyncio.to_thread(driver.shutdown), timeout=8)
    except Exception as e:
        print(f"[STOP] Agent 停止: {e}")

    print("[OK] 系统已关闭")
    os._exit(0)


# ═══════════════════════════════════════════════════════════════
# 统一入口
# ═══════════════════════════════════════════════════════════════


async def main():
    if os.environ.get("USE_NEW_ARCH") == "true":
        print("[Main] 使用新架构 (DI Container + AgentScheduler)")
        await _start_new_architecture()
    else:
        print("[Main] 使用旧架构 (YumeDriver)")
        await _start_legacy_architecture()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[STOP] 系统已关闭")
        os._exit(0)
