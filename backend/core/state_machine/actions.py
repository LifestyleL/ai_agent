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
        Path(__file__).parent.parent.parent / "agent_memory" / "personality.md",
        Path(__file__).parent.parent.parent / "core" / "memory" / "personality.md",
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
    """检测主 LLM 输出是否为记忆查询信号"""
    # 短文本 + 匹配缓冲模式 → 查询信号
    if len(text) <= 60 and _RECALL_SIGNAL_PATTERN.search(text):
        return True
    return False


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

        logger.warning(f"[THINK V4.0] 思考中... 输入: {user_input[:30]}... (回忆轮次: {round_count})")

        # --- Step 1: 预检索（grep，无需 LLM，~50ms） ---
        memory_context = ""
        pre_search_result = ""
        if hasattr(driver_instance, 'memory_core') and driver_instance.memory_core:
            mc = driver_instance.memory_core
            # 用 build_context 组装上下文（含 grep 预检索）
            memory_context = mc.build_context(user_input)

            # 同时做关键词直接搜索
            import re as _re
            words = _re.findall(r"[一-鿿\w]{2,}", user_input)
            if words:
                pre_search_result = mc.search_diary(words[0], limit=2)

        # --- Step 2: 构建主 LLM 提示词（无工具定义！） ---
        persona = load_personality()
        yume_template = _load_prompt("yume_system.md")
        if not yume_template:
            yume_template = """你是 yume，一个温柔偶尔傲娇的 AI 女主播。
{persona}

## 记忆参考
{memory_context}

## 对话历史
{history}"""

        # 短期历史
        history_str = ""
        if hasattr(driver_instance, 'memory_core') and driver_instance.memory_core:
            history_str = driver_instance.memory_core.get_short_term_context(max_turns=20) or "（暂无对话记录）"

        system_prompt = yume_template.format(
            persona=persona,
            memory_context=memory_context or "（无相关记忆）",
            history=history_str
        )

        # 如果有前一轮查询子 LLM 的结果，注入
        if deep_recall_result:
            system_prompt += f"\n\n【刚才深入查到的记忆】\n{deep_recall_result}\n请基于这些记忆自然地继续回复用户。"

        # 如果有潜意识碎片，注入
        if recall_injection:
            system_prompt += f"\n{recall_injection}"

        # --- Step 3: 调用主 LLM（纯角色，无工具） ---
        try:
            raw_response = await llm_speaker.ask_with_system_async(system_prompt, user_input, temperature=0.7)
            response_text = raw_response.strip().strip('"').strip("'") if raw_response else ""

            if not response_text or response_text.isspace():
                logger.error("[THINK V4.0] 主 LLM 返回空回复")
                await state_machine.trigger(Event.ERROR, {"error": "主 LLM 返回空回复"})
                return

            logger.warning(f"[THINK V4.0] 主 LLM 回复: {response_text[:80]}...")

        except Exception as e:
            logger.error(f"[THINK V4.0] 主 LLM 调用失败: {e}")
            await state_machine.trigger(Event.ERROR, {"error": str(e)})
            return

        # --- Step 4: 检测是否需要深挖记忆 ---
        is_recall = _detect_recall_signal(response_text)

        if is_recall and round_count < 2 and pre_search_result:
            # 主 LLM 发出了缓冲信号 → 启动查询子 LLM
            logger.warning(f"[THINK V4.0] 检测到回忆信号: '{response_text[:40]}...'")

            # 发送缓冲语到前端（防止冷场）
            if hasattr(driver_instance, 'send_buffer_text'):
                await asyncio.to_thread(driver_instance.send_buffer_text, response_text)
            elif hasattr(driver_instance, 'speak_final_text'):
                await asyncio.to_thread(driver_instance.speak_final_text, response_text)

            # 启动查询子 LLM（在线程中运行，避免阻塞）
            query_goal = _extract_query_goal(user_input, response_text)
            logger.warning(f"[THINK V4.0] 启动查询子 LLM，目标: {query_goal[:80]}...")

            try:
                recall_result = await asyncio.to_thread(
                    _run_memory_query, query_goal, registry
                )
                logger.warning(f"[THINK V4.0] 查询子 LLM 返回: {recall_result[:100] if recall_result else '(空)'}...")
            except Exception as e:
                logger.error(f"[THINK V4.0] 查询子 LLM 失败: {e}")
                recall_result = f"记忆检索失败: {e}"

            # 将结果注入 context，重新进入 THINK
            context["deep_recall_result"] = recall_result
            context["recall_round"] = round_count + 1
            await state_machine.trigger(Event.NEED_TOOL, context)
            return

        # --- Step 5: 正常回复 → 播报 → 完成 ---
        logger.warning(f"[THINK V4.0] 最终回复: {response_text[:100]}...")

        if hasattr(driver_instance, 'speak_final_text'):
            await asyncio.to_thread(driver_instance.speak_final_text, response_text)

        # 异步写入记忆
        if hasattr(driver_instance, 'memory_core') and driver_instance.memory_core:
            driver_instance.memory_core.start_async_memory_write(user_input, response_text)

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
