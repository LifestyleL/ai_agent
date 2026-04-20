import asyncio
import logging
import random
import json
from typing import Dict, List, Any, Optional
from backend.core.state_machine.state_machine import StateMachine, State, Event
from backend.core.llm.llm_api import LLMAPI
from backend.config import QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

logger = logging.getLogger(__name__)

# ------------------------------------------------------------
# 宏观 Action（暂时注释掉，保留以备恢复）
# ------------------------------------------------------------
# def create_think_action(driver_instance: any, state_machine: StateMachine):
#     """
#     工厂函数：生成 THINK 状态的 Action。
#     传入原有的 driver 实例和状态机实例，形成闭包。
#     """
#     print(f"[FSM Action Factory] 创建 THINK Action, driver_instance: {driver_instance}, state_machine: {state_machine}")
#
#     async def action_think(context: dict):
#         user_input = context.get("user_input", "")
#         print(f"[FSM Action] 进入 THINK 状态，准备执行原有逻辑，输入: {user_input[:20]}...")
#
#         try:
#             # 【关键点】使用 asyncio.to_thread 在后台线程执行同步的 handle_user_input
#             # 这样既不改动原函数，又不会阻塞 WebSocket 的异步事件循环
#             if hasattr(driver_instance, 'handle_user_input'):
#                 print(f"[FSM Action] 通过 asyncio.to_thread 调用 driver.handle_user_input")
#                 await asyncio.to_thread(driver_instance.handle_user_input, user_input)
#                 print(f"[M Action] driver.handle_user_input 执行完成")
#             else:
#                 print(f"[FSM Action] 错误: driver_instance 缺少 handle_user_input 方法！")
#
#             print("[FSM Action] 原有逻辑执行完毕，触发 TASK_COMPLETE 回到 IDLE")
#             await state_machine.trigger(Event.TASK_COMPLETE)
#
#         except Exception as e:
#             print(f"[FSM Action] 错误: 原有逻辑执行报错: {e}")
#             await state_machine.trigger(Event.ERROR, {"error": str(e)})
#
#     print(f"[FSM Action Factory] Action 函数创建完成: {action_think}")
#     return action_think

# ------------------------------------------------------------
# 微观 Action 骨架（Phase 2.3-A 验证用）
# ------------------------------------------------------------

def create_micro_think_action(state_machine: StateMachine):
    """
    微观 THINK 动作：模拟主脑（Qwen）的单次思考。
    现实中这里是调用 Qwen API，现在用 Mock 模拟决策。
    """
    async def action_think(context: dict):
        user_input = context.get("user_input", "")
        step = context.get("step", 0)

        logger.warning(f"🧠 [Mock主脑] 正在分析第 {step} 步... 输入: {user_input[:20]}")
        await asyncio.sleep(1)  # 模拟网络延迟

        # Mock 决策逻辑：假设前两步需要工具，第三步直接输出最终答案
        if step < 2:
            logger.warning(f"🧠 [Mock主脑] 决策：需要调用工具！")
            # 将步骤数加1，传递给下一个状态
            context["step"] = step + 1
            context["mock_tool_name"] = "search_memory"
            # 触发跳转到 DO_TOOL
            await state_machine.trigger(Event.NEED_TOOL, context)
        else:
            logger.warning(f"🧠 [Mock主脑] 决策：思考完毕，生成最终回答！")
            # 触发跳转到 IDLE (TASK_COMPLETE)
            await state_machine.trigger(Event.TASK_COMPLETE)

    return action_think


def create_micro_do_tool_action(state_machine: StateMachine, registry: any):
    """
    微观 DO_TOOL 动作：模拟执行者（DeepSeek）调用工具。
    现实中这里是把任务丢给 DeepSeek 并从 ToolRegistry 取工具执行。
    """
    async def action_do_tool(context: dict):
        tool_name = context.get("mock_tool_name", "unknown")
        logger.warning(f"🛠️ [Mock执行者] 收到指令，准备调用工具: {tool_name}")
        await asyncio.sleep(1.5)  # 模拟工具执行时间

        # 现实中这里应该从 registry 取工具并执行，现在只打日志
        # result = await asyncio.to_thread(registry.execute_tool, tool_name, ...)
        mock_result = f"Mock 工具 {tool_name} 返回的假数据"
        logger.warning(f"🛠️ [Mock执行者] 工具执行完毕，结果: {mock_result}")

        # 将结果存入 context，带回给 THINK
        context["tool_result"] = mock_result
        # 触发跳转回 THINK
        await state_machine.trigger(Event.TOOL_RETURN, context)

    return action_do_tool


# ------------------------------------------------------------
# 真实微观 Action（Phase 2.3-B 真实引擎接入）
# ------------------------------------------------------------

def create_real_think_action(state_machine: StateMachine, registry: any, driver_instance: any):
    """
    真实 THINK 动作：调用真实的 DeepSeek API 进行决策判断。

    Args:
        state_machine: 状态机实例
        registry: 工具注册中心实例
        driver_instance: YumeDriver 实例（用于访问 speak_final_text）
    """
    # 初始化 DeepSeek LLM API（用于工具决策）
    llm_deepseek = LLMAPI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, model=DEEPSEEK_MODEL)
    # 初始化 Qwen LLM API（用于生成最终回复）
    llm_qwen = LLMAPI(api_key=QWEN_API_KEY, base_url=QWEN_BASE_URL, model=QWEN_MODEL)

    # DeepSeek 系统提示词（来自 llm_collaborator.py）
    DEEPSEEK_SYSTEM_PROMPT = """你是Agent的决策引擎，仅负责判断是否需要调用工具、输出工具参数，以及判断是否可完成回答，不做任何自然语言解释、不写思考过程。

核心规则
仅返回JSON格式，不输出任何其他文字（包括开场白、结束语、思考过程）；
严格按照以下固定格式输出，参数缺失时，补充合理默认值；
need_tool为true时，必须填写tool_name和params；need_tool为false时，tool_name和params留空；
can_answer为true时，代表当前信息足够回答，可停止工具调用；can_answer为false时，需继续调用工具；
若已调用过工具，需结合工具结果判断是否需要继续调用，避免重复调用。
可用工具列表
{tools_json}

当前对话历史
{history}

用户当前问题
{user_question}

输出格式（必须严格遵守）
{{
"need_tool": true/false,
"can_answer": true/false,
"thought": "简短思考（10字以内）",
"tool_name": "工具名称",
"params": {{}}
}}"""

    async def action_think(context: dict):
        user_input = context.get("user_input", "")
        step = context.get("step", 0)  # 步骤计数器，用于多轮工具调用
        conversation_history = context.get("conversation_history", [])  # 对话历史
        previous_tool_results = context.get("tool_results", [])  # 之前的工具结果

        logger.warning(f"🧠 [真实主脑] 第{step}步思考，输入: {user_input[:30]}...")

        # 构建工具列表 JSON
        tools_schemas = registry.get_legacy_schema()
        tools_json = json.dumps(tools_schemas, ensure_ascii=False, indent=2)

        # 构建对话历史字符串
        history_str = ""
        if conversation_history:
            history_str = "\n".join([f"{msg['role']}: {msg['content'][:100]}..." for msg in conversation_history[-5:]])

        # 构建消息列表
        messages = [
            {"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT.format(
                tools_json=tools_json,
                history=history_str,
                user_question=user_input
            )}
        ]

        # 如果有之前的工具结果，添加到消息中
        if previous_tool_results:
            for i, result in enumerate(previous_tool_results):
                messages.append({"role": "assistant", "content": json.dumps(result.get("decision", {}))})
                messages.append({"role": "user", "content": f"工具调用结果：{result.get('tool_result', '')}"})

        # 调用 DeepSeek API 进行决策
        try:
            response = llm_deepseek.chat(messages, temperature=0.2)

            if "error" in response:
                logger.error(f"🧠 [真实主脑] API调用失败: {response['error']}")
                # 触发错误事件
                await state_machine.trigger(Event.ERROR, {"error": f"API调用失败: {response['error']}"})
                return

            # 解析响应
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                logger.error("🧠 [真实主脑] 响应内容为空")
                await state_machine.trigger(Event.ERROR, {"error": "响应内容为空"})
                return

            # 解析 JSON
            try:
                decision = json.loads(content.strip())
                logger.warning(f"🧠 [真实主脑] 决策: {decision}")

                # 更新上下文
                context["step"] = step + 1
                context["last_decision"] = decision

                # 判断下一步行动
                if decision.get("need_tool", False):
                    # 需要工具
                    tool_name = decision.get("tool_name", "")
                    params = decision.get("params", {})

                    if not tool_name:
                        logger.error("🧠 [真实主脑] 决策需要工具但未指定工具名称")
                        await state_machine.trigger(Event.ERROR, {"error": "未指定工具名称"})
                        return

                    # 准备工具调用上下文
                    context["tool_name"] = tool_name
                    context["tool_params"] = params
                    context["tool_thought"] = decision.get("thought", "")

                    # 触发 NEED_TOOL 事件，跳转到 DO_TOOL
                    await state_machine.trigger(Event.NEED_TOOL, context)

                elif decision.get("can_answer", False):
                    # 可以回答，调用 Qwen 生成最终回复
                    logger.warning("🧠 [真实主脑] 决策：可以生成最终回答，现在调用 Qwen 生成回复")

                    # 构建 Qwen 上下文
                    # 简化版：基于用户输入和之前的工具结果生成回复
                    if "tool_results" in context and context["tool_results"]:
                        # 有工具结果，构建总结
                        tool_summary = "，".join([f"{r.get('tool_name')}的结果" for r in context["tool_results"][-3:]])
                        prompt = f"用户的问题是：{user_input}\n\n我已经通过工具查询了相关信息：{tool_summary}。请用自然、简洁的语气回答用户的问题。"
                    else:
                        # 没有工具结果，直接回答
                        prompt = f"用户的问题是：{user_input}。请用自然、简洁的语气回答。"

                    try:
                        # 调用 Qwen API 生成回复
                        final_reply = llm_qwen.ask(prompt, temperature=0.7)
                        logger.warning(f"🧠 [真实主脑] Qwen 生成回复: {final_reply[:100]}...")

                        # 使用 driver 的 TTS 入口
                        if hasattr(driver_instance, 'speak_final_text'):
                            await asyncio.to_thread(driver_instance.speak_final_text, final_reply)
                        else:
                            logger.error("🧠 [真实主脑] driver 没有 speak_final_text 方法")

                    except Exception as e:
                        logger.error(f"🧠 [真实主脑] Qwen API 调用失败: {e}")
                        # 降级：使用默认回复
                        fallback_reply = f"我了解了。{user_input}的答案是..."
                        if hasattr(driver_instance, 'speak_final_text'):
                            await asyncio.to_thread(driver_instance.speak_final_text, fallback_reply)

                    # 触发 TASK_COMPLETE 事件，回到 IDLE
                    await state_machine.trigger(Event.TASK_COMPLETE)

                else:
                    # 既不需要工具也不能回答，结束循环
                    logger.warning("🧠 [真实主脑] 决策：既不需要工具也不能回答，结束")
                    await state_machine.trigger(Event.TASK_COMPLETE)

            except json.JSONDecodeError as e:
                logger.error(f"🧠 [真实主脑] JSON解析失败: {e}, 原始内容: {content[:200]}")
                await state_machine.trigger(Event.ERROR, {"error": f"JSON解析失败: {e}"})

        except Exception as e:
            logger.error(f"🧠 [真实主脑] 处理异常: {e}")
            await state_machine.trigger(Event.ERROR, {"error": str(e)})

    return action_think


def create_real_do_tool_action(state_machine: StateMachine, registry: any):
    """
    真实 DO_TOOL 动作：调用真实的工具执行。
    """
    # 初始化 DeepSeek LLM API（执行者）
    llm_deepseek = LLMAPI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, model=DEEPSEEK_MODEL)

    async def action_do_tool(context: dict):
        tool_name = context.get("tool_name", "")
        tool_params = context.get("tool_params", {})
        tool_thought = context.get("tool_thought", "")

        logger.warning(f"🛠️ [真实执行者] 准备调用工具: {tool_name}, 参数: {tool_params}")

        if not tool_name:
            logger.error("🛠️ [真实执行者] 工具名称为空")
            await state_machine.trigger(Event.ERROR, {"error": "工具名称为空"})
            return

        try:
            # 从注册中心获取工具并执行
            tool = registry.get_tool(tool_name)
            if not tool:
                logger.error(f"🛠️ [真实执行者] 工具未注册: {tool_name}")
                await state_machine.trigger(Event.ERROR, {"error": f"工具未注册: {tool_name}"})
                return

            # 执行工具，传递 llm 参数（某些工具需要）
            logger.warning(f"🛠️ [真实执行者] 开始执行工具: {tool_name}")
            # 合并参数，添加 llm 实例
            all_params = {**tool_params, "llm": llm_deepseek}
            tool_result = registry.execute_tool(tool_name, **all_params)
            logger.warning(f"🛠️ [真实执行者] 工具执行完毕，结果: {str(tool_result)[:100]}...")

            # 更新上下文
            context["tool_result"] = tool_result

            # 记录到工具结果列表
            if "tool_results" not in context:
                context["tool_results"] = []

            context["tool_results"].append({
                "tool_name": tool_name,
                "params": tool_params,
                "tool_result": tool_result,
                "decision": context.get("last_decision", {})
            })

            # 触发 TOOL_RETURN 事件，回到 THINK
            await state_machine.trigger(Event.TOOL_RETURN, context)

        except Exception as e:
            logger.error(f"🛠️ [真实执行者] 工具执行异常: {e}")
            await state_machine.trigger(Event.ERROR, {"error": f"工具执行异常: {e}"})

    return action_do_tool


# ------------------------------------------------------------
# 兼容层：为 ws_server.py 等旧代码提供 create_think_action
# ------------------------------------------------------------

def create_think_action(driver_instance: any, state_machine: StateMachine):
    """
    兼容函数：为旧代码提供 create_think_action 接口。
    内部使用真实引擎实现。
    """
    print(f"[FSM Action Factory] 创建兼容 THINK Action（使用真实引擎）")

    # 从全局注册中心获取 registry
    from backend.plugins.registry import get_global_registry
    registry = get_global_registry()

    # 使用真实引擎
    real_action = create_real_think_action(
        state_machine=state_machine,
        registry=registry,
        driver_instance=driver_instance
    )

    print(f"[FSM Action Factory] 兼容 Action 创建完成")
    return real_action