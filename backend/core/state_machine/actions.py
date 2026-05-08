"""
V4.0+ 状态机 Action 工厂函数

辅助函数已迁移至:
- backend.core.think_pipeline.query_executor (execute_single_tool, run_memory_query)
- backend.core.think_pipeline.recall_detect (_detect_recall_signal)
- backend.core.think_pipeline.prompt_build (_load_persona)

本模块提供工厂函数，从 DI 容器或旧式 driver 创建 FSM Action 回调。
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Optional

from backend.core.state_machine.state_machine import StateMachine, Event
from backend.core.llm.llm_api import LLMAPI
from backend.core.llm.llm_factory import LLMFactory

logger = logging.getLogger(__name__)

# 重新导出自 query_executor，保持向后兼容
from backend.core.think_pipeline.query_executor import (
    execute_single_tool as _execute_single_tool,
    run_memory_query as _run_memory_query,
)

_USE_NEW_ARCH = os.environ.get("USE_NEW_ARCH") == "true"


# ─────────────────────────────────────────────────────────
# 新架构：容器驱动工厂（Step 5 精简后）
# ─────────────────────────────────────────────────────────


def create_think_action(container):
    """新架构工厂：从 DI 容器获取 ThinkOrchestrator.think"""
    orchestrator = container.resolve("think_orchestrator")
    return orchestrator.think


def create_do_tool_action(container):
    """新架构工厂：从 DI 容器获取 ThinkOrchestrator.do_tool"""
    orchestrator = container.resolve("think_orchestrator")
    return orchestrator.do_tool


# ─────────────────────────────────────────────────────────
# 旧架构工厂（过渡期保留，ws_server.py 仍在使用）
# ─────────────────────────────────────────────────────────

_LOOK_CLASSIFY_PROMPT = (
    "你是一个意图分类器。判断用户是否在请求 AI 查看/描述当前屏幕内容。"
    "只回复 YES 或 NO，不要输出其他内容。"
)


async def _detect_look_intent_async(user_input: str, llm_speaker) -> bool:
    """用 LLM 判断用户是否想让 yume 看屏幕"""
    if not user_input or not llm_speaker:
        return False
    try:
        result = await llm_speaker.ask_with_system_async(
            _LOOK_CLASSIFY_PROMPT,
            f'用户说："{user_input}"\n\n用户是否在请求 AI 看屏幕？只回复 YES 或 NO。',
            temperature=0,
        )
        if result:
            return result.strip().upper().startswith("YES")
    except Exception:
        pass
    return False


def create_real_do_tool_action(
    state_machine: StateMachine,
    registry: Any,
    llm_deepseek: Optional[LLMAPI] = None,
):
    """旧版 DO_TOOL Action — ws_server.py 过渡期使用"""
    if llm_deepseek is None:
        llm_deepseek = LLMFactory.get_default()

    async def action_do_tool(context: dict):
        tool_name = context.get("tool_name", "")
        tool_params = context.get("tool_params", {})
        tool_batch = context.get("tool_batch", [])

        if not tool_name and not tool_batch:
            logger.warning("[DO_TOOL] 空工具调用，跳过")
            await state_machine.trigger(Event.TOOL_RETURN, context)
            return

        logger.info("[DO_TOOL] 执行工具: %s", tool_name)

        if tool_batch:
            results = []
            for tool_info in tool_batch:
                t_name = tool_info.get("tool_name", "")
                t_params = tool_info.get("params", {})
                if t_name:
                    r = _execute_single_tool(registry, t_name, t_params, llm_deepseek)
                    results.append({"tool_name": t_name, "params": t_params, "tool_result": r})
            context.setdefault("tool_results", []).extend(results)
            context["tool_result"] = results[0]["tool_result"] if results else None
        elif tool_name:
            result = _execute_single_tool(registry, tool_name, tool_params, llm_deepseek)
            context["tool_result"] = result
            if "tool_results" not in context:
                context["tool_results"] = []
            context["tool_results"].append({
                "tool_name": tool_name, "params": tool_params, "tool_result": result,
            })

        await state_machine.trigger(Event.TOOL_RETURN, context)

    return action_do_tool


def create_real_think_action(
    state_machine: StateMachine,
    registry: Any,
    driver_instance: Any,
    llm_deepseek: Optional[LLMAPI] = None,
):
    """旧版 THINK Action — ws_server.py 过渡期使用"""
    import re

    if llm_deepseek is None:
        llm_deepseek = LLMFactory.get_default()
    llm_speaker = LLMFactory.get_default()

    from backend.core.think_pipeline.recall_detect import (
        _detect_recall_signal, _extract_query_goal, _MEMORY_SEARCH_PATTERN,
    )
    from backend.core.think_pipeline.prompt_build import (
        _load_persona, _load_yume_template,
    )

    async def action_think(context: dict):
        # 自驱动快速通道
        if context.get("is_spontaneous"):
            text = context.get("spontaneous_text", "")
            emotion = context.get("spontaneous_emotion", "neutral")
            logger.info("[THINK] 自驱动快速通道: '%s...'", text[:30])
            if driver_instance and hasattr(driver_instance, 'tts_manager'):
                driver_instance.tts_manager.on_spontaneous_speech(text, {"emotion": emotion})
            if driver_instance and hasattr(driver_instance, 'frontend'):
                driver_instance.frontend.send_live2d_cmd("emotion", emotion=emotion)
            if driver_instance and hasattr(driver_instance, 'memory_core'):
                driver_instance.memory_core.add_short_term("assistant", text)
            await state_machine.trigger(Event.TASK_COMPLETE)
            return

        user_input = context.get("user_input", "")
        recall_injection = context.get("recall_injection", "")
        deep_recall_result = context.get("deep_recall_result", "")
        round_count = context.get("recall_round", 0)

        logger.info("[THINK] 思考中... 输入: %s... (回忆轮次: %s)", user_input[:30], round_count)

        mc = driver_instance.memory_core if hasattr(driver_instance, 'memory_core') else None

        # 构建结构化分区
        structured = mc.build_structured_sections(user_input, deep_recall_result) if mc else {}
        if deep_recall_result:
            structured["deep_recall"] = deep_recall_result
        if recall_injection:
            if structured.get("deep_recall", "") == "（无深层记忆浮现）":
                structured["deep_recall"] = recall_injection.replace("【潜意识浮现】", "").strip()
            else:
                structured["deep_recall"] = structured.get("deep_recall", "") + "\n" + recall_injection

        # 情绪推断
        if mc and hasattr(mc, '_emotion_engine') and mc._emotion_engine:
            etype, estrength = mc._emotion_engine.infer_from_text(user_input)
            if estrength > 0:
                mc._emotion_engine.update_emotion(etype, estrength)

        # 构建 system prompt
        persona = _load_persona()
        yume_template = _load_yume_template()
        history_str = mc.get_short_term_context(max_turns=20) if mc else "（暂无对话记录）"

        emotion_label = "neutral"
        if mc and hasattr(mc, '_emotion_engine') and mc._emotion_engine:
            emotion_label = mc._emotion_engine.type_to_label(mc._emotion_engine.type)

        # 用户主动 look：LLM 意图分类 → 截图+VLM
        visual_look = ""
        if await _detect_look_intent_async(user_input, llm_speaker):
            try:
                from api.netwebsocket.ws_server import WSServer
                ws = WSServer()
                if hasattr(ws, 'visual_observer') and ws.visual_observer:
                    visual_look = await ws.visual_observer.request_look()
            except Exception as e:
                logger.warning("[THINK] request_look 失败: %s", e)

        system_prompt = yume_template.format(
            persona=persona,
            emotion=emotion_label,
            time_context=structured.get("time_context", ""),
            diary_memory=structured.get("diary_memory", ""),
            precise_query=structured.get("precise_query", ""),
            pre_search=structured.get("pre_search", ""),
            deep_recall=structured.get("deep_recall", ""),
            card_index=structured.get("card_index", ""),
            diary_index=structured.get("diary_index", ""),
            terrain=structured.get("terrain", ""),
            visual_look=visual_look,
            history=history_str,
        )

        # 推送情绪
        if hasattr(driver_instance, 'tts_manager'):
            driver_instance.tts_manager.current_emotion = emotion_label
        if hasattr(driver_instance, 'frontend'):
            driver_instance.frontend.send_live2d_cmd("emotion", emotion=emotion_label)

        # 流式 LLM + 逐句 TTS
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        response_text = ""
        streamed_to_tts = False

        try:
            pending = ""
            async for token in llm_speaker.chat_stream_async(messages, temperature=0.7):
                if token.startswith("[ERROR]"):
                    raise RuntimeError(f"流式中断: {token}")
                response_text += token
                pending += token

                cut = -1
                for p in ["。", "！", "？", "\n"]:
                    pos = pending.find(p)
                    if pos != -1 and (cut == -1 or pos < cut):
                        cut = pos

                if cut != -1:
                    sentence = pending[:cut + 1]
                    pending = pending[cut + 1:]
                    sentence = _MEMORY_SEARCH_PATTERN.sub("", sentence)
                    clean = sentence.strip()
                    has_content = any(c.isalnum() or '一' <= c <= '鿿' for c in clean)
                    if has_content and len(clean) >= 2:
                        if hasattr(driver_instance, 'tts_manager'):
                            driver_instance.tts_manager.enqueue_text(sentence, emotion_label)
                            streamed_to_tts = True

            if pending.strip():
                pending = _MEMORY_SEARCH_PATTERN.sub("", pending)
                clean = pending.strip()
                has_content = any(c.isalnum() or '一' <= c <= '鿿' for c in clean)
                if has_content and len(clean) >= 2:
                    if hasattr(driver_instance, 'tts_manager'):
                        driver_instance.tts_manager.enqueue_text(pending, emotion_label)
                        streamed_to_tts = True

            response_text = response_text.strip().strip('"').strip("'")
        except Exception as e:
            logger.error("[THINK] 流式LLM失败: %s", e)
            try:
                raw = await llm_speaker.ask_with_system_async(system_prompt, user_input, temperature=0.7)
                response_text = raw.strip().strip('"').strip("'") if raw else ""
                if response_text and hasattr(driver_instance, 'speak_final_text'):
                    await asyncio.to_thread(driver_instance.speak_final_text, response_text)
                    streamed_to_tts = True
            except Exception as e2:
                logger.error("[THINK] 非流式LLM也失败: %s", e2)
                await state_machine.trigger(Event.ERROR, {"error": str(e2)})
                return

        if not response_text or response_text.isspace():
            logger.error("[THINK] 主 LLM 返回空回复")
            await state_machine.trigger(Event.ERROR, {"error": "主 LLM 返回空回复"})
            return

        # ── 优先检测 [MEMORY_SEARCH: ...] 指令 ──
        m = _MEMORY_SEARCH_PATTERN.search(response_text)
        if m:
            keyword = m.group(1).strip()
            logger.info("[THINK] AI主动查记忆: '%s'", keyword)
            response_text = _MEMORY_SEARCH_PATTERN.sub("", response_text).strip()
            if response_text and not streamed_to_tts and hasattr(driver_instance, 'speak_final_text'):
                await asyncio.to_thread(driver_instance.speak_final_text, response_text)
            query_goal = f"用户输入：{context.get('original_user_input', user_input)[:200]}\nAI指定关键词：{keyword}\n请用此关键词精确检索相关记忆。"
            recall_result = await asyncio.to_thread(
                _run_memory_query, query_goal, registry, llm_deepseek
            )
            logger.info("[THINK] 主动查询结果: %s...", (recall_result or "(空)")[:100])
            context["deep_recall_result"] = recall_result
            context["recall_round"] = round_count + 1
            if "original_user_input" not in context:
                context["original_user_input"] = user_input
            context["user_input"] = (
                f"<system>\n"
                f"你刚才在回答用户问题时使用了主动记忆查询，查询已完成。\n"
                f"你之前已经回答过原始问题了，现在只需要补充你没想到的新内容。\n"
                f"</system>\n\n"
                f"<recall_result>\n{recall_result}\n</recall_result>\n\n"
                f"<original_question>\n{context['original_user_input']}\n</original_question>\n\n"
                f"<guidelines>\n"
                f"  <rule>只补充你刚才没想到的新内容，不要重复已经说过的话</rule>\n"
                f"  <rule>如果查询结果没有实质新信息，说一句自然的收尾</rule>\n"
                f"  <rule>保持简短，1-2句话即可</rule>\n"
                f"</guidelines>"
            )
            await action_think(context)
            return

        # 检测缓冲信号 → 查询子 LLM
        is_recall = _detect_recall_signal(response_text)
        if not is_recall and mc:
            intent = mc.detect_memory_intent(user_input)
            if intent["intent"] in ("date_query", "keyword_query") and structured.get("precise_query") == "（本次未触发精准查询）":
                is_recall = True

        if is_recall and round_count < 2:
            logger.info("[THINK] 检测到回忆信号: '%s...'", response_text[:60])
            if not streamed_to_tts and hasattr(driver_instance, 'speak_final_text'):
                await asyncio.to_thread(driver_instance.speak_final_text, response_text)

            query_goal = _extract_query_goal(user_input, response_text)
            recall_result = await asyncio.to_thread(
                _run_memory_query, query_goal, registry, llm_deepseek
            )
            logger.info("[THINK] 查询子 LLM 返回: %s...", (recall_result or "(空)")[:100])

            context["deep_recall_result"] = recall_result
            context["recall_round"] = round_count + 1
            if "original_user_input" not in context:
                context["original_user_input"] = user_input
            context["user_input"] = (
                f"<system>\n"
                f"你刚才在回答用户问题时触发了内部记忆查询，查询已完成。\n"
                f"你之前已经回答过原始问题了，现在只需要补充你没想到的新内容。\n"
                f"</system>\n\n"
                f"<recall_result>\n{recall_result}\n</recall_result>\n\n"
                f"<original_question>\n{context['original_user_input']}\n</original_question>\n\n"
                f"<guidelines>\n"
                f"  <rule>只补充你刚才没想到的新内容，不要重复已经说过的话</rule>\n"
                f"  <rule>如果查询结果没有实质新信息，说一句自然的收尾</rule>\n"
                f"  <rule>保持简短，1-2句话即可</rule>\n"
                f"</guidelines>"
            )
            await action_think(context)
            return

        # 正常回复
        if not streamed_to_tts and hasattr(driver_instance, 'speak_final_text'):
            await asyncio.to_thread(driver_instance.speak_final_text, response_text)

        if mc:
            clean_user_input = context.get("original_user_input", user_input)
            mc.start_async_memory_write(clean_user_input, response_text)
            if structured.get("write_request"):
                mc.append_diary_draft(f"用户明确要求记住：{clean_user_input[:200]}")

        # 后台更新对话目标
        if hasattr(driver_instance, 'goal_tracker') and driver_instance.goal_tracker:
            driver_instance.goal_tracker.maybe_update()

        await state_machine.trigger(Event.TASK_COMPLETE)

    return action_think
