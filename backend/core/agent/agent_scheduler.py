"""
AgentScheduler — 中央调度器（门面）

职责：
- 持有 DIContainer，管理所有能力的生命周期
- 路由用户输入/自驱动回调到 StateMachine
- 设置全局事件处理器（instinct、mumble、discovery、surfing）
- 不实例化任何具体模块——全部从容器获取
"""

import asyncio
import logging
import threading
import time
from typing import Any, Dict, Optional

from backend.core.state_machine.state_machine import StateMachine, State, Event
from backend.core.state_machine.transitions import setup_base_transitions
from backend.core.event.event_bus import event_bus, EventType

logger = logging.getLogger(__name__)


class AgentScheduler:
    """中央调度器门面"""

    def __init__(self, container):
        self._container = container
        self._is_running = False
        self._speak_lock = threading.Lock()
        self._thinking = False
        self._query_threads: list = []

    # ── 生命周期 ──

    async def start(self) -> None:
        """启动所有能力"""
        await self._container.initialize_all()

        # 状态机配置
        sm: StateMachine = self._container.resolve("state_machine")
        setup_base_transitions(sm)

        # 绑定 FSM Actions
        orchestrator = self._container.resolve("think_orchestrator")
        sm.register_action(State.THINK, orchestrator.think)
        sm.register_action(State.DO_TOOL, orchestrator.do_tool)

        # 连接 send_queue
        ws_server = self._container.resolve("ws_server")
        frontend = self._container.resolve("frontend")
        tts_manager = self._container.resolve("tts_manager")
        frontend.send_queue = ws_server.send_queue
        if hasattr(tts_manager, 'voice'):
            tts_manager.voice.send_queue = ws_server.send_queue

        # 注册事件处理器
        self._setup_event_handlers()

        # 启动后台引擎
        drive_model = self._container.resolve("drive_model")
        drive_model.start()

        try:
            spontaneous_engine = self._container.resolve("spontaneous_engine")
            spontaneous_engine.start()
            logger.info("[AgentScheduler] 自驱动引擎已启动")
        except Exception:
            pass

        # 启动 GoalTracker 异步循环（如果有）
        try:
            goal_tracker = self._container.resolve("goal_tracker")
            if hasattr(goal_tracker, 'start_loop'):
                loop = asyncio.get_event_loop()
                loop.create_task(goal_tracker.start_loop())
        except Exception:
            pass

        self._is_running = True
        logger.info("[AgentScheduler] Agent 已启动")

    async def shutdown(self) -> None:
        """优雅关闭所有能力"""
        self._is_running = False

        try:
            spontaneous_engine = self._container.resolve("spontaneous_engine")
            if hasattr(spontaneous_engine, 'stop'):
                spontaneous_engine.stop()
        except Exception:
            pass

        await self._container.shutdown_all()

    # ── 事件处理器 ──

    def _setup_event_handlers(self) -> None:
        from backend.core.event.event_bus import event_handler

        llm = self._container.resolve("llm")
        tts_manager = self._container.resolve("tts_manager")

        @event_handler(EventType.THINKING_INTERMEDIATE)
        def handle_thinking_intermediate(event):
            if not self._thinking:
                return
            thought_text = event.data.get("thought", "")
            if not thought_text.strip():
                return
            logger.debug("[ThinkingInteraction] '%s'", thought_text)
            try:
                voice = tts_manager.voice if hasattr(tts_manager, 'voice') else None
                if voice:
                    voice._speak_segment(thought_text, emotion="neutral")
            except Exception as e:
                logger.warning("[ThinkingInteraction] 失败: %s", e)

        @event_handler(EventType.DISCOVERY_MADE)
        def handle_discovery(event):
            topic = event.data.get("topic", "")
            content = event.data.get("content", "")
            if not topic or not content:
                return
            prompt = f"(你刚才自己偷偷查了下{topic})\n查到了：{content}\n用你自己的话感叹或分享一句，不要说你是去查资料的。"
            try:
                text = llm.ask(prompt)
                if text and not text.isspace():
                    tts_manager.enqueue_text(text, "neutral")
            except Exception as e:
                logger.warning("[Discovery] 异常: %s", e)

        @event_handler(EventType.SURFING_REVIEW_NEEDED)
        def handle_surfing_review(event):
            from backend.core.memory.memory_facade import MemoryFacade
            surfing_content = MemoryFacade.load_files(["surfing_memories.md"])
            if not surfing_content or surfing_content.strip() == "":
                return
            prompt = (
                f'你最近偷偷查了一些东西，列在下面。\n'
                f'请判断哪些让你觉得"哇这个好有意思我想记住"。\n\n'
                f'规则：\n- 只有真正触动你的才选，无聊的直接忽略\n'
                f'- 如果都不想记，回复"无"\n'
                f'- 如果有想记的，用你的话重新写一遍\n\n'
                f'你查到的东西：\n{surfing_content}'
            )
            try:
                speaker_response = llm.ask(prompt)
                if speaker_response and speaker_response.strip() != "无" and not speaker_response.isspace():
                    logger.info("[SurfingReview] 已写入长期记忆")
            except Exception as e:
                logger.warning("[SurfingReview] 异常: %s", e)

        # 注册 InstinctHandler（如果容器中有）
        try:
            instinct = self._container.resolve("instinct_handler")
            if hasattr(instinct, 'register'):
                instinct.register(event_bus)
        except Exception:
            pass

        # 注册 MumbleHandler
        try:
            mumble = self._container.resolve("mumble_handler")
            if hasattr(mumble, 'register'):
                mumble.register(event_bus)
        except Exception:
            pass

        logger.info("[AgentScheduler] 事件处理器已注册")

    # ── 用户输入 ──

    def handle_user_input(self, text: str, source: str = "text") -> None:
        """路由用户输入到状态机"""
        if not text.strip():
            return

        memory = self._container.resolve("memory")
        tts_manager = self._container.resolve("tts_manager")

        if source == "voice":
            tts_manager.interrupt()
            frontend = self._container.resolve("frontend")
            frontend.send_interrupt_command()

        memory.check_cross_day_diary()
        recall_injection, recall_count = memory.build_recall_injection()

        try:
            spontaneous = self._container.resolve("spontaneous_engine")
            spontaneous.on_user_activity(text)
            if hasattr(spontaneous, 'engagement_analyzer') and spontaneous.engagement_analyzer:
                spontaneous.engagement_analyzer.record_turn(
                    user_msg=text, ai_msg=None, is_ai_spontaneous=False, timestamp=time.time(),
                )
        except Exception:
            pass

        tts_manager.current_emotion = "neutral"
        activity_type = memory.detect_activity_type(text)
        logger.debug("[AgentScheduler] 活动类型: %s", activity_type)

        self._speak_lock.acquire()
        try:
            event_bus.publish(EventType.USER_INPUT_RECEIVED,
                              source="AgentScheduler", text=text, timestamp=time.time())

            sm: StateMachine = self._container.resolve("state_machine")
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            asyncio.create_task(sm.trigger(Event.USER_INPUT, {
                "user_input": text,
                "recall_injection": recall_injection,
            }))
            logger.debug("[AgentScheduler] 已触发 USER_INPUT")

            event_bus.publish(EventType.THINKING_STARTED,
                              source="AgentScheduler", text=text, timestamp=time.time())
            self._thinking = True

        except Exception as e:
            logger.error("[AgentScheduler] 用户输入异常: %s", e)
            event_bus.publish(EventType.ERROR_OCCURRED,
                              source="AgentScheduler", error=str(e), timestamp=time.time())
        finally:
            self._thinking = False
            event_bus.publish(EventType.USER_INPUT_PROCESSED,
                              source="AgentScheduler", text=text[:100] if text else "", timestamp=time.time())
            self._speak_lock.release()

    # ── 自驱动回调 ──

    def on_spontaneous_speech(self, text: str, context: Dict[str, Any]) -> None:
        """自驱动引擎回调 —— 通过状态机分发"""
        sm: StateMachine = self._container.resolve("state_machine")
        if not sm:
            return

        sm_context = {
            "is_spontaneous": True,
            "spontaneous_text": text,
            "spontaneous_emotion": context.get("emotion", "neutral"),
            "spontaneous_context": context,
            "follow_up_type": context.get("follow_up_type"),
            "lightweight_context": context.get("lightweight_context"),
            "tts_streamed": context.get("tts_streamed", False),
        }

        try:
            spontaneous = self._container.resolve("spontaneous_engine")
            if hasattr(spontaneous, 'engagement_analyzer') and spontaneous.engagement_analyzer:
                spontaneous.engagement_analyzer.record_turn(
                    user_msg=None, ai_msg=text, is_ai_spontaneous=True, timestamp=time.time(),
                )
        except Exception:
            pass

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(sm.trigger(Event.SPONTANEOUS_TRIGGER, sm_context))
            else:
                asyncio.run_coroutine_threadsafe(
                    sm.trigger(Event.SPONTANEOUS_TRIGGER, sm_context), loop)
        except RuntimeError:
            threading.Thread(
                target=lambda: asyncio.run(sm.trigger(Event.SPONTANEOUS_TRIGGER, sm_context)),
                daemon=True,
            ).start()

    @property
    def is_running(self) -> bool:
        return self._is_running
