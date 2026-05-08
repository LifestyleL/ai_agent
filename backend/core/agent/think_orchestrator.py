"""
ThinkOrchestrator — 思考流水线编排器

职责：
- 从 DI 容器组装 ThinkPipeline（Stage 链）
- 提供 think(context) 和 do_tool(context) 作为 FSM Action 回调
- 替代 actions.py 中 682 行的 God Function
"""

import asyncio
import logging
import threading
import time
from typing import Any, Dict, Optional

from backend.core.state_machine.state_machine import StateMachine, Event
from backend.core.llm.llm_api import LLMAPI
from backend.core.llm.llm_factory import LLMFactory
import backend.config as config

logger = logging.getLogger(__name__)


class ThinkOrchestrator:
    """组装 ThinkPipeline，提供 FSM Action 回调"""

    def __init__(self, container):
        self._container = container
        self._pipeline = None
        self._state_machine: Optional[StateMachine] = None

    async def initialize(self, deps) -> None:
        self._state_machine = deps.resolve("state_machine")

        memory = deps.resolve("memory")
        emotion = deps.resolve("emotion")
        llm = deps.resolve("llm")
        dispatcher = deps.resolve("response_dispatcher")
        registry = deps.resolve("tool_registry")
        prompt_builder = deps.resolve("prompt_builder")

        from backend.core.think_pipeline import (
            ThinkPipeline, MemoryRetrieveStage, PromptBuildStage,
            LLMStreamStage, RecallDetectStage, FinalizeStage,
        )
        from backend.core.think_pipeline.skill_match_stage import (
            SkillMatchStage, build_default_matcher,
        )

        skill_matcher = build_default_matcher()

        goal_tracker = deps.resolve("goal_tracker")

        stages = [
            MemoryRetrieveStage(memory_core=memory, emotion_engine=emotion, dispatcher=dispatcher),
            SkillMatchStage(matcher=skill_matcher),
            PromptBuildStage(),
            LLMStreamStage(llm_api=llm, dispatcher=dispatcher),
            RecallDetectStage(query_executor=_QueryExecutorImpl(registry)),
            FinalizeStage(memory_core=memory, dispatcher=dispatcher, goal_tracker=goal_tracker),
        ]
        self._pipeline = ThinkPipeline(stages=stages)

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

        from backend.core.think_pipeline.context import ThinkContext
        from backend.core.emotion.emotion_engine import EmotionEngine

        memory = self._container.resolve("memory")
        emotion = self._container.resolve("emotion")
        frontend = self._container.resolve("frontend")
        tts_manager = self._container.resolve("tts_manager")
        llm = self._container.resolve("llm")

        # 情绪标签推送
        emotion_label = emotion.get_emotion_label() if hasattr(emotion, 'get_emotion_label') else "neutral"
        tts_manager.current_emotion = emotion_label
        frontend.send_live2d_cmd("emotion", emotion=emotion_label)

        # 用户主动 look：LLM 意图分类 → 截图+VLM
        visual_look = ""
        if await _detect_look_intent_async(user_input, llm):
            try:
                observer = self._container.resolve("visual_observer")
                visual_look = await observer.request_look()
            except Exception as e:
                logger.warning("[ThinkOrchestrator] request_look 失败: %s", e)

        ctx = ThinkContext(
            user_input=user_input,
            original_user_input=user_input,
            deep_recall_result=deep_recall_result,
            recall_round=round_count,
            memory_context={
                "recall_injection": recall_injection,
                "emotion_label": emotion_label,
                "visual_look": visual_look,
            },
        )

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

        await sm.trigger(Event.TASK_COMPLETE)

    # ── FSM Action: DO_TOOL ──

    async def do_tool(self, context: dict) -> None:
        """FSM Action: 进入 DO_TOOL 状态时调用"""
        sm = self._state_machine
        registry = self._container.resolve("tool_registry")
        llm = self._container.resolve("llm")

        from backend.core.think_pipeline.query_executor import execute_single_tool

        tool_name = context.get("tool_name", "")
        tool_params = context.get("tool_params", {})
        tool_batch = context.get("tool_batch", [])

        if not tool_name and not tool_batch:
            logger.warning("[DO_TOOL] 空工具调用，跳过")
            await sm.trigger(Event.TOOL_RETURN, context)
            return

        if tool_batch:
            results = []
            for tool_info in tool_batch:
                t_name = tool_info.get("tool_name", "")
                t_params = tool_info.get("params", {})
                if t_name:
                    r = execute_single_tool(registry, t_name, t_params, llm)
                    results.append({"tool_name": t_name, "params": t_params, "tool_result": r})
            context.setdefault("tool_results", []).extend(results)
            context["tool_result"] = results[0]["tool_result"] if results else None
        elif tool_name:
            result = execute_single_tool(registry, tool_name, tool_params, llm)
            context["tool_result"] = result
            context.setdefault("tool_results", []).append({
                "tool_name": tool_name, "params": tool_params, "tool_result": result,
            })

        await sm.trigger(Event.TOOL_RETURN, context)

    # ── 自驱动快速通道 ──

    async def _handle_spontaneous_fast_path(self, context: dict) -> None:
        sm = self._state_machine
        text = context.get("spontaneous_text", "")
        emotion_label = context.get("spontaneous_emotion", "neutral")
        ft = context.get("follow_up_type")
        lw_ctx = context.get("lightweight_context")

        spontaneous_engine = self._container.resolve("spontaneous_engine")
        if ft and lw_ctx and hasattr(spontaneous_engine, 'content_generator'):
            try:
                enriched = await spontaneous_engine.content_generator.generate_with_context(ft, lw_ctx)
                if enriched:
                    text = enriched
            except Exception:
                pass

        logger.info("[ThinkOrchestrator] 自驱动快速通道: '%s...'", text[:30])

        dispatcher = self._container.resolve("response_dispatcher")
        frontend = self._container.resolve("frontend")
        memory = self._container.resolve("memory")

        dispatcher.enqueue_tts(text, emotion_label)
        dispatcher.send_to_frontend(text, "chunk")
        frontend.send_live2d_cmd("emotion", emotion=emotion_label)
        memory.add_short_term("assistant", text)

        if hasattr(spontaneous_engine, 'on_ai_spoke'):
            spontaneous_engine.on_ai_spoke(text)

        await sm.trigger(Event.TASK_COMPLETE)


class _QueryExecutorImpl:
    """将 _run_memory_query 包装为 async 协议"""

    def __init__(self, registry):
        self._registry = registry

    async def execute(self, query_goal: str) -> str:
        from backend.core.think_pipeline.query_executor import run_memory_query
        return await asyncio.to_thread(run_memory_query, query_goal, self._registry)


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
