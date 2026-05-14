"""
ThinkOrchestrator — 思考流水线编排器（v2: ReAct 循环架构）

职责：
- 从 DI 容器组装 ThinkPipeline（Setup + ReAct Loop + Finalize）
- 提供 think(context) 作为 FSM Action 回调
- 替代 actions.py 中 682 行的 God Function
"""

import logging
from typing import Any, Dict, Optional

from backend.core.capability import Capability
from backend.core.state_machine.state_machine import StateMachine, Event

logger = logging.getLogger(__name__)


class ThinkOrchestrator(Capability):
    """组装 ThinkPipeline，提供 FSM Action 回调"""

    name = "think_orchestrator"
    version = "2.0"

    def __init__(self, container):
        self._container = container
        self._pipeline = None
        self._state_machine: Optional[StateMachine] = None

    async def initialize(self, container) -> None:
        self._state_machine = container.resolve("state_machine")

        memory = container.resolve("memory")
        emotion = container.resolve("emotion")
        llm = container.resolve("llm")
        vision_llm = container.resolve("vision_llm")
        dispatcher = container.resolve("response_dispatcher")
        registry = container.resolve("tool_registry")
        self._channel_registry = container.resolve("channel_registry")

        from backend.core.think_pipeline import (
            ThinkPipeline, MemoryRetrieveStage, PromptBuildStage, FinalizeStage,
        )
        from backend.core.think_pipeline.skill_match_stage import (
            SkillMatchStage,
        )
        from backend.core.think_pipeline.llm_chat_stage import LLMChatStage
        from backend.core.think_pipeline.tool_exec_stage import ToolExecStage

        skill_manager = container.resolve("skill_manager")

        goal_tracker = container.resolve("goal_tracker")

        # ── Setup stages（一次性，构建 system_prompt）──
        setup_stages = [
            MemoryRetrieveStage(memory_core=memory, emotion_engine=emotion, dispatcher=dispatcher),
            SkillMatchStage(skill_manager=skill_manager),
            PromptBuildStage(),
        ]

        # ── ReAct LLM 阶段（非流式，支持 tools + vision）──
        llm_stage = LLMChatStage(llm=llm, registry=registry, vision_llm=vision_llm)

        # ── 工具执行阶段 ──
        tool_stage = ToolExecStage(registry=registry)

        # ── 收尾阶段（channel 由 think() 动态注入到 ctx）──
        finalize_stage = FinalizeStage(
            memory_core=memory, dispatcher=dispatcher, goal_tracker=goal_tracker,
        )

        self._pipeline = ThinkPipeline(
            setup_stages=setup_stages,
            llm_stage=llm_stage,
            tool_stage=tool_stage,
            finalize_stage=finalize_stage,
        )

    async def shutdown(self) -> None:
        self._pipeline = None
        self._state_machine = None

    def get_status(self) -> Dict[str, Any]:
        return {
            "state_machine": self._state_machine.current_state.value if self._state_machine else None,
            "pipeline_ready": self._pipeline is not None,
        }

    # ── FSM Action: THINK ──

    async def think(self, context: dict) -> None:
        """FSM Action: 进入 THINK 状态时调用"""
        sm = self._state_machine

        if context.get("is_spontaneous"):
            await self._handle_spontaneous_fast_path(context)
            return

        user_input = context.get("user_input", "")
        recall_injection = context.get("recall_injection", "")
        deep_recall_result = context.get("deep_recall_result", "")
        round_count = context.get("recall_round", 0)
        session_id = context.get("session_id", "")

        from backend.core.think_pipeline.context import ThinkContext

        emotion = self._container.resolve("emotion")
        llm = self._container.resolve("llm")

        # 解析 Channel
        channel = self._channel_registry.resolve(session_id)

        # 情绪标签
        emotion_label = emotion.get_emotion_label() if hasattr(emotion, 'get_emotion_label') else "neutral"

        # 用户主动 look：LLM 意图分类 → 截图（raw base64 直接给主 VLM）
        screenshot_b64 = ""
        if await _detect_look_intent_async(user_input, llm):
            try:
                observer = self._container.resolve("visual_observer")
                screenshot_b64 = await observer.request_look()
            except Exception as e:
                logger.warning("[ThinkOrchestrator] request_look 失败: %s", e)

        ctx = ThinkContext(
            user_input=user_input,
            original_user_input=user_input,
            deep_recall_result=deep_recall_result,
            recall_round=round_count,
            screenshot_b64=screenshot_b64,
            session_id=session_id,
            memory_context={
                "recall_injection": recall_injection,
                "emotion_label": emotion_label,
                "visual_look": "",
            },
        )

        # Channel 预处理：注入频道上下文
        ctx = await channel.pre_process(ctx)

        try:
            ctx = await self._pipeline.execute(ctx)
        except Exception as e:
            logger.error("[ThinkOrchestrator] Pipeline 执行失败: %s", e)
            await sm.trigger(Event.ERROR, {"error": str(e)})
            return

        if ctx.error:
            logger.error("[ThinkOrchestrator] Pipeline 错误: %s", ctx.error)
            await sm.trigger(Event.ERROR, {"error": ctx.error})
            return

        # Channel 后处理：PASS 检测等
        ctx = await channel.post_process(ctx)

        # Channel 输出路由：本地推 TTS/Frontend，QQ 是 no-op（WS handler 自行发送）
        await channel.send_response(ctx)

        await sm.trigger(Event.TASK_COMPLETE)

    # ── FSM Action: DO_TOOL ──

    async def do_tool(self, context: dict) -> None:
        """FSM Action: 进入 DO_TOOL 状态时调用（保留，Phase 3+ 使用）"""
        sm = self._state_machine
        logger.warning("[DO_TOOL] DO_TOOL 状态在 ReAct 架构中不应被触发，透传")
        await sm.trigger(Event.TOOL_RETURN, context)

    # ── 自驱动快速通道 ──

    async def _handle_spontaneous_fast_path(self, context: dict) -> None:
        sm = self._state_machine
        text = context.get("spontaneous_text", "")
        emotion_label = context.get("spontaneous_emotion", "neutral")
        ft = context.get("follow_up_type")
        lw_ctx = context.get("lightweight_context")
        tts_streamed = context.get("tts_streamed", False)

        spontaneous_engine = self._container.resolve("spontaneous_engine")
        if ft and lw_ctx and hasattr(spontaneous_engine, 'content_generator'):
            try:
                enriched = await spontaneous_engine.content_generator.generate_with_context(ft, lw_ctx)
                if enriched:
                    text = enriched
                    tts_streamed = spontaneous_engine.content_generator.last_was_streamed or tts_streamed
            except Exception:
                pass

        logger.info("[ThinkOrchestrator] 自驱动快速通道: '%s...'", text[:30])

        dispatcher = self._container.resolve("response_dispatcher")
        frontend = self._container.resolve("frontend")
        memory = self._container.resolve("memory")

        if not tts_streamed:
            dispatcher.enqueue_tts(text, emotion_label)
        dispatcher.send_to_frontend(text, "chunk")
        frontend.send_live2d_cmd("emotion", emotion=emotion_label)
        memory.add_short_term("assistant", text)

        if hasattr(spontaneous_engine, 'on_ai_spoke'):
            spontaneous_engine.on_ai_spoke(text)

        await sm.trigger(Event.TASK_COMPLETE)


_LOOK_CLASSIFY_PROMPT = (
    "你是一个意图分类器。判断用户是否在请求 AI 查看/描述当前屏幕内容。"
    "只回复 YES 或 NO，不要输出其他内容。"
)


async def _detect_look_intent_async(user_input: str, llm) -> bool:
    """用 LLM 判断用户是否想让 yume 看屏幕"""
    if not user_input or not llm:
        return False
    try:
        result = await llm.ask_with_system_async(
            _LOOK_CLASSIFY_PROMPT,
            f'用户说："{user_input}"\n\n用户是否在请求 AI 看屏幕？只回复 YES 或 NO。',
            temperature=0,
        )
        if result:
            return result.strip().upper().startswith("YES")
    except Exception:
        pass
    return False
