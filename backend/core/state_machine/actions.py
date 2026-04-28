"""
V4.0 双 LLM 记忆查询架构
- 主 LLM（yume）：纯角色对话，无工具定义
- 查询子 LLM：独立实例，带工具，线程内执行→销毁，只返回摘要
- 预检索（grep）：零延迟，先给主 LLM 参考
"""

import asyncio
import json
import logging
import re
import threading
from pathlib import Path
from typing import Dict, Any, Optional

from backend.core.state_machine.state_machine import StateMachine, State, Event
from backend.core.llm.llm_api import LLMAPI
from backend.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

logger = logging.getLogger(__name__)

# 缓冲语检测模式：主 LLM 输出匹配这些表示"我需要查一下"
_RECALL_SIGNAL_PATTERN = re.compile(
    r'(让我想想|我想想|嗯[.…～~]+|不太确定|不记得了|'
    r'让我回忆|等一下|我查查|我翻翻|让我找找|'
    r'这个嘛|嘶[.…～~]*|诶[.…～~]*|唔[.…～~]+)'
)


def _load_prompt(name: str) -> str:
    """加载提示词文件"""
    prompt_path = Path(__file__).parent.parent.parent / "agent_memory" / "prompts" / name
    if prompt_path.exists():
        try:
            return prompt_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"加载提示词 {name} 失败: {e}")
    return ""


def load_personality() -> str:
    possible_paths = [
        Path(__file__).parent.parent.parent / "agent_memory" / "core" / "personality.md",
        Path(__file__).parent.parent.parent / "agent_memory" / "personality.md",
    ]
    for path in possible_paths:
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception:
                pass
    return "你是 yume，一个有点傲娇、带点毒舌的AI。"


def _detect_recall_signal(text: str) -> bool:
    """检测主 LLM 输出是否为记忆查询信号（不再限制文本长度）"""
    return _RECALL_SIGNAL_PATTERN.search(text) is not None


def _extract_query_goal(user_input: str, llm_response: str) -> str:
    """从 LLM 的缓冲回复中提取查询目标"""
    # 用用户输入 + LLM 缓冲语拼接查询目标
    return f"用户说：{user_input[:200]}\nAI 的初步反应：{llm_response[:100]}\n请检索与上述内容相关的记忆。"


# ================================================================
# 查询子 LLM（独立实例，线程内执行 → 销毁）
# ================================================================

def _run_memory_query(query_goal: str, registry, max_steps: int = 3) -> str:
    """
    在独立线程中运行查询子 LLM。
    创建独立 LLMAPI 实例 → 带工具执行检索 → 返回摘要 → 实例销毁。
    """
    query_llm = None
    try:
        query_llm = LLMAPI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            model=DEEPSEEK_MODEL
        )

        # 加载工具 schema
        tools_schemas = registry.get_legacy_schema() if registry else []
        tools_json = json.dumps(tools_schemas, ensure_ascii=False, indent=2)

        # 加载查询子 LLM 提示词
        query_prompt_template = _load_prompt("query_system.md")
        if not query_prompt_template:
            query_prompt_template = """你是记忆检索助手。
可用工具：{tools_json}
查询目标：{query_goal}
规则：检索相关记忆，返回 JSON 摘要。最多 3 次工具调用。"""

        system_prompt = query_prompt_template.format(
            tools_json=tools_json,
            query_goal=query_goal,
            experience=""
        )

        messages = [{"role": "system", "content": system_prompt}]

        for step in range(max_steps):
            # 同步调用（在线程中运行）
            response = query_llm.chat(messages, temperature=0.2)

            if "error" in response:
                logger.error(f"[查询子LLM] API 错误: {response['error']}")
                break

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                break

            # 尝试解析 JSON 决策
            try:
                decision = json.loads(content.strip())
            except json.JSONDecodeError:
                # 非 JSON，可能是最终摘要
                logger.info(f"[查询子LLM] 第{step+1}步返回非JSON，视为最终摘要")
                return content.strip()

            # 如果是最终结果
            if decision.get("found") is not None:
                summary = decision.get("summary", "")
                detail = decision.get("detail", "")
                return f"{summary}\n{detail}" if detail else summary

            # 如果需要调用工具
            tools_to_call = decision.get("tools", [])
            tool_name = decision.get("tool_name", "")
            params = decision.get("params", {})

            if tools_to_call:
                # 批量工具
                tool_results = []
                for tool_info in tools_to_call:
                    t_name = tool_info.get("tool_name", "")
                    t_params = tool_info.get("params", {})
                    if t_name:
                        result = _execute_single_tool(registry, t_name, t_params, query_llm)
                        tool_results.append(f"[{t_name}] {result}")
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": "工具结果：\n" + "\n".join(tool_results)})
            elif tool_name:
                # 单个工具
                result = _execute_single_tool(registry, tool_name, params, query_llm)
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": f"工具 [{tool_name}] 结果：{result}"})
            else:
                # 没有工具调用，视为最终回复
                return content.strip()

        # 达到最大步数，让 LLM 总结
        messages.append({"role": "user", "content": "请基于以上检索结果，给出最终摘要。"})
        try:
            final = query_llm.chat(messages, temperature=0.2)
            fc = final.get("choices", [{}])[0].get("message", {}).get("content", "")
            return fc.strip() if fc else "检索完成，但未能生成摘要"
        except Exception:
            return "检索完成，但摘要生成失败"

    except Exception as e:
        logger.error(f"[查询子LLM] 执行异常: {e}")
        return f"记忆查询失败: {e}"
    finally:
        # 实例离开作用域，等待 GC 销毁
        del query_llm


def _execute_single_tool(registry, tool_name: str, params: dict, llm) -> str:
    """执行单个工具，返回结果字符串"""
    try:
        if not registry:
            return f"工具注册中心不可用"
        tool = registry.get_tool(tool_name)
        if not tool:
            return f"工具未注册: {tool_name}"
        filtered_params = {k: v for k, v in params.items() if v}
        all_params = {**filtered_params, "llm": llm}
        result = registry.execute_tool(tool_name, **all_params)
        return str(result)[:500]
    except Exception as e:
        return f"工具执行失败: {e}"


# ================================================================
# 真实 THINK Action（V4.0 双 LLM 架构）
# ================================================================

def create_real_think_action(
    state_machine: StateMachine,
    registry: Any,
    driver_instance: Any,
    llm_deepseek: Optional[LLMAPI] = None
):
    """
    V4.0 THINK Action：
    1. grep 预检索 → 注入上下文
    2. 主 LLM（yume，无工具）→ 自然回复或缓冲信号
    3. 缓冲信号 → 启动查询子 LLM 线程 → 摘要注入 → 主 LLM 再回复
    """
    if llm_deepseek is None:
        llm_deepseek = LLMAPI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, model=DEEPSEEK_MODEL)
    llm_speaker = LLMAPI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, model=DEEPSEEK_MODEL)

    async def action_think(context: dict):
        user_input = context.get("user_input", "")
        recall_injection = context.get("recall_injection", "")
        deep_recall_result = context.get("deep_recall_result", "")  # 查询子 LLM 返回的结果
        round_count = context.get("recall_round", 0)  # 防止无限循环

        logger.warning(f"[THINK V5.0] 思考中... 输入: {user_input[:30]}... (回忆轮次: {round_count})")

        # ================================================================
        # Step 0: 记忆意图前置检测 + 结构化搜索（LLM 之前！）
        # ================================================================
        mc = driver_instance.memory_core if hasattr(driver_instance, 'memory_core') else None
        structured = {
            "diary_memory": "（暂无日记记录）",
            "precise_query": "（本次未触发精准查询）",
            "pre_search": "（无预检索结果）",
            "deep_recall": "（无深层记忆浮现）",
            "time_context": mc.get_time_context() if mc else "",
            "write_request": False,
        }

        if mc:
            structured = mc.build_structured_sections(user_input, deep_recall_result)
            # 旧版兼容：如果 deep_recall_result 已有值，覆盖 deep_recall
            if deep_recall_result:
                structured["deep_recall"] = deep_recall_result
            # 旧版兼容：recall_injection 追加到 deep_recall
            if recall_injection:
                if structured["deep_recall"] == "（无深层记忆浮现）":
                    structured["deep_recall"] = recall_injection.replace("【潜意识浮现】", "").strip()
                else:
                    structured["deep_recall"] += "\n" + recall_injection

            # Step 0.5: 情绪推断（从用户输入，纯规则，0延迟）
            if hasattr(mc, '_emotion_engine') and mc._emotion_engine:
                etype, estrength = mc._emotion_engine.infer_from_text(user_input)
                if estrength > 0:
                    mc._emotion_engine.update_emotion(etype, estrength)

        # ================================================================
        # Step 1: 构建结构化系统提示词（V5.0 分区架构）
        # ================================================================
        persona = load_personality()
        yume_template = _load_prompt("yume_system.md")
        if not yume_template:
            # 兜底模板（使用分区格式）
            yume_template = """你是 yume，一个温柔偶尔傲娇的 AI 女主播。
{persona}

## 【上下文】
{time_context}

## 【日记/长期记忆】
{diary_memory}

## 【查询到的记忆】
{precise_query}

## 【预检索参考】
{pre_search}

## 【深层记忆/潜意识】
{deep_recall}

## 【对话历史】
{history}"""

        history_str = mc.get_short_term_context(max_turns=20) if mc else "（暂无对话记录）"

        system_prompt = yume_template.format(
            persona=persona,
            time_context=structured["time_context"] or "",
            diary_memory=structured["diary_memory"],
            precise_query=structured["precise_query"],
            pre_search=structured["pre_search"],
            deep_recall=structured["deep_recall"],
            history=history_str or "（暂无对话记录）",
        )

        # ================================================================
        # Step 2: 情绪标签（供 TTS 使用）
        # ================================================================
        current_emotion = "neutral"
        if mc and hasattr(mc, '_emotion_engine') and mc._emotion_engine:
            from core.emotion.emotion_engine import EmotionEngine
            current_emotion = EmotionEngine.type_to_label(mc._emotion_engine.type)
            if hasattr(driver_instance, 'tts_manager'):
                driver_instance.tts_manager.current_emotion = current_emotion

        # 推送情绪到前端 Live2D（表情 + 体态）
        if hasattr(driver_instance, 'frontend'):
            driver_instance.frontend.send_live2d_cmd("emotion", emotion=current_emotion)

        logger.info(f"[THINK V5.0] 记忆分区: diary={len(structured['diary_memory'])}c, "
                    f"precise={len(structured['precise_query'])}c, "
                    f"presearch={len(structured['pre_search'])}c")

        # ================================================================
        # Step 3: 流式 LLM + 逐句 TTS 流水线
        # ================================================================
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
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
                    clean = sentence.strip()
                    has_content = any(c.isalnum() or '一' <= c <= '鿿' for c in clean)
                    if has_content and len(clean) >= 2:
                        if hasattr(driver_instance, 'tts_manager'):
                            driver_instance.tts_manager.enqueue_text(sentence, current_emotion)
                            streamed_to_tts = True

            if pending.strip():
                clean = pending.strip()
                has_content = any(c.isalnum() or '一' <= c <= '鿿' for c in clean)
                if has_content and len(clean) >= 2:
                    if hasattr(driver_instance, 'tts_manager'):
                        driver_instance.tts_manager.enqueue_text(pending, current_emotion)
                        streamed_to_tts = True

            response_text = response_text.strip().strip('"').strip("'")

        except Exception as e:
            logger.error(f"[THINK V5.0] 流式LLM失败: {e}, 回退到非流式")
            try:
                raw = await llm_speaker.ask_with_system_async(system_prompt, user_input, temperature=0.7)
                response_text = raw.strip().strip('"').strip("'") if raw else ""
                if response_text and hasattr(driver_instance, 'speak_final_text'):
                    await asyncio.to_thread(driver_instance.speak_final_text, response_text)
                    streamed_to_tts = True
            except Exception as e2:
                logger.error(f"[THINK V5.0] 非流式LLM也失败: {e2}")
                await state_machine.trigger(Event.ERROR, {"error": str(e2)})
                return

        if not response_text or response_text.isspace():
            logger.error("[THINK V5.0] 主 LLM 返回空回复")
            await state_machine.trigger(Event.ERROR, {"error": "主 LLM 返回空回复"})
            return

        logger.warning(f"[THINK V5.0] 主 LLM 回复: {response_text[:80]}...")

        # ================================================================
        # Step 4: 检测是否需要深挖记忆（去掉长度限制！）
        # ================================================================
        # 只要 LLM 说了缓冲语，无论多长都要触发查询
        is_recall = _RECALL_SIGNAL_PATTERN.search(response_text) is not None

        # 如果没有缓冲语但有记忆查询意图且精准查询为空，也触发
        if not is_recall and mc:
            intent = mc.detect_memory_intent(user_input)
            if intent["intent"] in ("date_query", "keyword_query") and structured["precise_query"] == "（本次未触发精准查询）":
                is_recall = True
                logger.warning(f"[THINK V5.0] 从意图检测触发深挖: {intent['intent']}")

        if is_recall and round_count < 2:
            logger.warning(f"[THINK V5.0] 检测到回忆信号: '{response_text[:60]}...'")

            # 缓冲语已通过流式送 TTS，通知前端
            if not streamed_to_tts:
                if hasattr(driver_instance, 'send_buffer_text'):
                    await asyncio.to_thread(driver_instance.send_buffer_text, response_text)
                elif hasattr(driver_instance, 'speak_final_text'):
                    await asyncio.to_thread(driver_instance.speak_final_text, response_text)

            if hasattr(driver_instance, 'frontend'):
                driver_instance.frontend.send_text_to_frontend(response_text, "thinking")

            # 启动查询子 LLM（在线程中运行，避免阻塞）
            query_goal = _extract_query_goal(user_input, response_text)
            logger.warning(f"[THINK V5.0] 启动查询子 LLM，目标: {query_goal[:80]}...")

            try:
                recall_result = await asyncio.to_thread(
                    _run_memory_query, query_goal, registry
                )
                logger.warning(f"[THINK V5.0] 查询子 LLM 返回: {recall_result[:100] if recall_result else '(空)'}...")
            except Exception as e:
                logger.error(f"[THINK V5.0] 查询子 LLM 失败: {e}")
                recall_result = f"记忆检索失败: {e}"

            context["deep_recall_result"] = recall_result
            context["recall_round"] = round_count + 1
            # 直接重入 THINK，避免空转 DO_TOOL 增加延迟
            await action_think(context)
            return

        # ================================================================
        # Step 5: 正常回复 → 收尾 + 异步写入
        # ================================================================
        logger.warning(f"[THINK V5.0] 最终回复: {response_text[:100]}...")

        if not streamed_to_tts and hasattr(driver_instance, 'speak_final_text'):
            await asyncio.to_thread(driver_instance.speak_final_text, response_text)

        # 异步记忆写入（含日记 + 短期记忆）
        if mc:
            mc.start_async_memory_write(user_input, response_text)
            # 如果用户请求写入，额外追加到日记
            if structured.get("write_request"):
                mc.append_diary_draft(f"用户明确要求记住：{user_input[:200]}")

        # 后台更新对话目标
        if hasattr(driver_instance, 'goal_tracker') and driver_instance.goal_tracker:
            driver_instance.goal_tracker.maybe_update()

        await state_machine.trigger(Event.TASK_COMPLETE)

    return action_think


# ================================================================
# 真实 DO_TOOL Action（查询子 LLM 的工具执行器）
# ================================================================

def create_real_do_tool_action(
    state_machine: StateMachine,
    registry: Any,
    llm_deepseek: Optional[LLMAPI] = None
):
    """
    V4.0 DO_TOOL Action：
    在查询子 LLM 触发工具调用时执行。
    实际上查询子 LLM 的工具在线程内直接执行，这里作为兜底兼容。
    """
    if llm_deepseek is None:
        llm_deepseek = LLMAPI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, model=DEEPSEEK_MODEL)

    async def action_do_tool(context: dict):
        tool_name = context.get("tool_name", "")
        tool_params = context.get("tool_params", {})
        tool_batch = context.get("tool_batch", [])
        is_batch = context.get("is_batch", False)

        if not tool_name and not tool_batch:
            logger.warning(f"[DO_TOOL V4.0] 空工具调用，跳过 (context keys: {list(context.keys())})")
            await state_machine.trigger(Event.TOOL_RETURN, context)
            return

        logger.warning(f"[DO_TOOL V4.0] 执行工具: {tool_name}, 批量: {is_batch}")

        if is_batch and tool_batch:
            results = []
            for tool_info in tool_batch:
                t_name = tool_info.get("tool_name", "")
                t_params = tool_info.get("params", {})
                if t_name:
                    r = _execute_single_tool(registry, t_name, t_params, llm_deepseek)
                    results.append({"tool_name": t_name, "params": t_params, "tool_result": r})
            if "tool_results" not in context:
                context["tool_results"] = []
            context["tool_results"].extend(results)
            context["tool_result"] = results[0]["tool_result"] if results else None
        elif tool_name:
            result = _execute_single_tool(registry, tool_name, tool_params, llm_deepseek)
            context["tool_result"] = result
            if "tool_results" not in context:
                context["tool_results"] = []
            context["tool_results"].append({
                "tool_name": tool_name,
                "params": tool_params,
                "tool_result": result
            })

        await state_machine.trigger(Event.TOOL_RETURN, context)

    return action_do_tool


# ================================================================
# 兼容层
# ================================================================

def create_think_action(driver_instance: Any, state_machine: StateMachine):
    """兼容旧代码的工厂函数"""
    print(f"[FSM Action Factory] 创建兼容 THINK Action（V4.0 双 LLM 架构）")
    from backend.plugins.registry import get_global_registry
    registry = get_global_registry()
    return create_real_think_action(
        state_machine=state_machine,
        registry=registry,
        driver_instance=driver_instance
    )
