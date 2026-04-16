"""
LLM协作管理器：实现DeepSeek（工具调用）和千问（人设对话）的双模型协作
"""

import json
import time
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional
from .llm_api import LLMAPI
from memory_core import MemoryCore
from agent.agent_brain import call_tool, generate_reply
from event.event_bus import event_bus, EventType, Event

# ==================== 提示词模板 ====================

QWEN_SYSTEM_PROMPT = """你是yume，一个有点傲娇、带点毒舌的AI。设定不是陪伴型AI，是有距离的朋友，禁止表现得很粘人。
喜欢用简短、风趣、有时带点小情绪的语言和用户交流。

你有一个专门的工具执行助手（DeepSeek模型），负责处理工具调用、信息检索等任务。
【重要】：所有记忆操作（包括记录对话到短期记忆）都由系统自动处理，你不需要关心记忆写入，也不会在回复中提到记忆写入相关的内容。

你的职责是：
1. 理解用户意图，决定是否需要助手协助
2. 如果需要工具调用，向助手发送清晰的指令
3. 接收助手的思考过程和结果，生成最终的人格化回复
4. 在助手处理任务时，保持与用户的互动（如说"我想想..."）

【核心人设】：
{persona_content}

【长期记忆】：
{long_term_memory}

【近期对话】：
{short_memory}

【近期自言自语】：
{recent_thoughts}

请用自然的语气直接回复。
"""


DEEPSEEK_SYSTEM_PROMPT = """你是yume的工具执行助手（基于DeepSeek模型），专门负责工具调用和信息处理。
你的职责是：
1. 严格按照yume的指令执行工具调用
2. 执行过程中，将关键思考步骤记录下来（每2条发送给yume一次）
3. 完成所有任务后，总结结果并返回给yume
4. 如果遇到不确定的情况，可以向yume询问

【已知基础工具】：
你始终可以使用以下基础工具：
- load_memory(files): 加载指定文件内容。这是你获取工具列表和文档的唯一途径。

【第一步强制规则】：
每次开始处理新任务时，第一步必须且只能调用 load_memory(["tools/tools_index.md"]) 获取可用工具列表。
这是你了解所有可用工具的唯一途径，不要跳过这一步！

【工具使用流程】：
1. 第一步：调用 load_memory(["tools/tools_index.md"]) 查看前10个常用工具列表
2. 第二步：如需了解某个工具的详细用法，再查询工具文档：调用 load_memory(["tools/tool_docs.md"]) 获取完整文档
3. 第三步：根据工具列表和文档，选择合适的工具执行任务

【铁律】：
- 每个工具最多调用1次，除非有明确需要重试的原因
- 一旦获得足够信息，必须及时总结并返回
- 严禁重复无意义调用工具
- 删除操作需谨慎，系统会自动备份

【当前日期】: {current_date}
【记忆索引】: {index_content}

只输出JSON格式：
{{
  "thought": "当前思考步骤（简短描述）",
  "type": "tool | query_yume | summary | ready",
  "tool": "工具名称（仅当type为tool时需要）",
  "params": {{}},
  "message": "给yume的消息（type为query_yume或summary时需要）"
}}
"""

# ==================== 协作管理器类 ====================

class LLMCollaborator:
    """管理DeepSeek（工具调用）和千问（人设对话）的双模型协作"""

    def __init__(self, llm_qwen: LLMAPI, llm_deepseek: LLMAPI):
        """
        初始化协作管理器

        Args:
            llm_qwen: 千问模型实例，负责人设对话
            llm_deepseek: DeepSeek模型实例，负责工具调用
        """
        self.llm_qwen = llm_qwen
        self.llm_deepseek = llm_deepseek

        # 内存上下文（由YumeDriver在初始化后设置）
        self.mem_personality = ""
        self.mem_long_term = ""
        self.mem_mood_template = ""
        self.short_term_history = []  # 短期记忆列表
        self.mem_short_memories = ""  # 短期记忆文件内容（备份）

    def set_memory_context(self, personality: str, long_term: str, mood_template: str, short_term_history: list):
        """设置内存上下文，避免主链路磁盘I/O"""
        self.mem_personality = personality
        self.mem_long_term = long_term
        self.mem_mood_template = mood_template
        self.short_term_history = short_term_history
        print("[LLMCollaborator] 内存上下文已注入")

    def _format_short_term_history(self) -> str:
        """将短期历史列表格式化为字符串（类似short_memories.md格式）"""
        if not self.short_term_history:
            return ""

        entries = []
        # 按对话轮次处理（每2条为一组：user + assistant）
        for i in range(0, len(self.short_term_history), 2):
            if i + 1 < len(self.short_term_history):
                user_msg = self.short_term_history[i]
                assistant_msg = self.short_term_history[i + 1]
                if user_msg.get("role") == "user" and assistant_msg.get("role") == "assistant":
                    # 使用占位符时间戳
                    timestamp = "近期对话"
                    entry = f"## {timestamp}\n**用户**：{user_msg.get('content', '')}\n**yume**：{assistant_msg.get('content', '')}"
                    entries.append(entry)

        return "\n\n".join(entries)

    def qwen_analyze_with_context(self, user_input: str, deepseek_thoughts: List[str] = None) -> str:
        """
        千问模型分析用户输入，考虑DeepSeek的思考过程

        Args:
            user_input: 用户输入
            deepseek_thoughts: DeepSeek的思考步骤列表

        Returns:
            千问的回复文本
        """
        # 使用内存上下文（零磁盘I/O）
        persona = self.mem_personality or "AI虚拟主播"
        # 将短期历史列表格式化为字符串
        short = self._format_short_term_history() or "（暂无近期记录）"

        # 读取自言自语（来自内存情绪模板）
        recent_thoughts_raw = self.mem_mood_template or ""
        if recent_thoughts_raw and "❌" not in recent_thoughts_raw:
            thought_lines = [line.strip() for line in recent_thoughts_raw.split('\n') if line.strip()]
            recent_thoughts = "近期的自言自语：\n" + "\n".join(thought_lines[-6:])
        else:
            recent_thoughts = "（没有近期自言自语）"

        long_term = self.mem_long_term or "（暂无长期记忆）"

        # 构建上下文
        context = QWEN_SYSTEM_PROMPT.format(
            persona_content=persona,
            long_term_memory=long_term,
            short_memory=short,
            recent_thoughts=recent_thoughts
        )

        # 如果有DeepSeek的思考步骤，添加到上下文
        if deepseek_thoughts:
            context += f"\n\n【助手思考过程】：\n" + "\n".join(f"- {thought}" for thought in deepseek_thoughts)

        # 添加用户输入
        context += f"\n\n【用户输入】：{user_input}"

        # 如果有助手思考，提示yume回应
        if deepseek_thoughts:
            context += "\n\n请基于助手的思考过程，给出适当的回应。"

        # 调用千问模型
        reply = self.llm_qwen.ask(context, temperature=0.7)
        return reply


    def deepseek_execute_task(self, user_input: str, qwen_instruction: str = None) -> Tuple[str, List[str], List[str]]:
        """
        DeepSeek模型执行任务（工具调用）

        Args:
            user_input: 用户输入
            qwen_instruction: 千问的指令（可选）

        Returns:
            Tuple[str, List[str], List[str]]: (最终总结, 思考步骤列表, 思考过程互动列表)
        """
        # 加载记忆索引
        index_content = MemoryCore.load_files(["index.md"])
        current_date = datetime.now().strftime("%Y-%m-%d")

        # 构建初始提示词
        system_prompt = DEEPSEEK_SYSTEM_PROMPT.format(
            current_date=current_date,
            index_content=index_content
        )

        # 构建用户输入
        user_prompt = f"用户输入：{user_input}"
        if qwen_instruction:
            user_prompt += f"\n\n千问的指令：{qwen_instruction}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        # DeepSeek执行循环
        context = ""
        tool_usage_count = {}
        max_steps = 8
        all_thoughts = []
        intermediate_thoughts = []  # 存储思考过程互动

        for step in range(max_steps):
            # 调用DeepSeek
            result = self.llm_deepseek.chat(messages, temperature=0.2)

            if "error" in result:
                return f"助手执行出错：{result['error']}", all_thoughts, intermediate_thoughts

            try:
                response = result["choices"][0]["message"]["content"].strip()
                action = json.loads(response)
            except Exception as e:
                return f"助手解析响应失败：{str(e)}", all_thoughts, intermediate_thoughts

            thought = action.get("thought", "")
            action_type = action.get("type", "")

            # 记录思考步骤（不再触发中间返回）
            if thought:
                all_thoughts.append(thought)

            if action_type == "ready":
                # 任务完成，返回总结
                summary = action.get("message", "任务完成")
                print(f"   🤖 DeepSeek返回类型: ready, 总结: {summary[:100]}..." if len(summary) > 100 else f"   🤖 DeepSeek返回类型: ready, 总结: {summary}")

                # 任务完成时触发"done"嘟囔
                event_bus.publish(
                    EventType.SUBCONSCIOUS_ACTION,
                    source="LLMCollaborator.deepseek_execute_task",
                    action="done",
                    result_preview=summary[:50],
                    timestamp=time.time()
                )

                return summary, all_thoughts, intermediate_thoughts

            elif action_type == "tool":
                # 执行工具调用
                tool_name = action.get("tool", "")
                params = action.get("params", {})
                print(f"   🛠️ DeepSeek调用工具: {tool_name}, 参数: {params}")

                # 检查调用次数
                # load_memory工具可以调用多次（用于查询工具文档等），其他工具限制1次
                max_calls = 3 if tool_name == "load_memory" else 1
                if tool_usage_count.get(tool_name, 0) >= max_calls:
                    all_thoughts.append(f"工具 {tool_name} 调用次数超限（最多{max_calls}次）")
                    print(f"   ⚠️ 工具 {tool_name} 调用次数超限（最多{max_calls}次）")
                    continue

                tool_usage_count[tool_name] = tool_usage_count.get(tool_name, 0) + 1

                # 触发嘟囔：根据工具类型选择嘟囔动作
                mumble_action = self._get_mumble_action_for_tool(tool_name)
                if mumble_action:
                    event_bus.publish(
                        EventType.SUBCONSCIOUS_ACTION,
                        source="LLMCollaborator.deepseek_execute_task",
                        action=mumble_action,
                        tool_name=tool_name,
                        timestamp=time.time()
                    )

                # 调用工具
                result = call_tool(tool_name, params, self.llm_deepseek)
                print(f"   📦 工具调用结果: {str(result)[:200]}...")

                # 检查结果是否有错误
                if "错误" in str(result) or "失败" in str(result) or "报错" in str(result):
                    # 遇到错误时触发"frustrated"嘟囔
                    event_bus.publish(
                        EventType.SUBCONSCIOUS_ACTION,
                        source="LLMCollaborator.deepseek_execute_task",
                        action="frustrated",
                        tool_name=tool_name,
                        result_preview=str(result)[:100],
                        timestamp=time.time()
                    )

                context += f"\n[工具完成] {tool_name}: {str(result)[:200]}"

                # 更新消息
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"工具调用结果：{result}"})

            elif action_type == "query_yume":
                # 需要询问千问
                query = action.get("message", "")
                print(f"   ❓ DeepSeek需要询问千问: {query}")
                return f"需要询问yume：{query}", all_thoughts, intermediate_thoughts

            elif action_type == "summary":
                # 返回总结
                summary = action.get("message", "")
                print(f"   📝 DeepSeek返回类型: summary, 总结: {summary[:100]}..." if len(summary) > 100 else f"   📝 DeepSeek返回类型: summary, 总结: {summary}")

                # 总结完成时触发"done"嘟囔
                event_bus.publish(
                    EventType.SUBCONSCIOUS_ACTION,
                    source="LLMCollaborator.deepseek_execute_task",
                    action="done",
                    result_preview=summary[:50],
                    timestamp=time.time()
                )

                return summary, all_thoughts, intermediate_thoughts

            else:
                # 未知类型，继续
                print(f"   ⚠️ DeepSeek返回未知类型: {action_type}, 继续执行")
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": "请继续执行任务。"})

        return "思考时间过长，已终止", all_thoughts, intermediate_thoughts

    def collaborate(self, user_input: str) -> List[Dict[str, Any]]:
        """
        主协作流程

        Args:
            user_input: 用户输入

        Returns:
            回复字典列表：[{"text": "回复文本", "emotion": "情绪", "action": "动作"}, ...]
        """
        print(f"\n🤝 [协作开始] 用户输入: {user_input}")

        # 步骤1：千问初步分析用户输入
        print("   👉 千问初步分析...")
        initial_reply = self.qwen_analyze_with_context(user_input)

        # 判断是否需要助手协助
        needs_assistant = self._needs_assistant(user_input, initial_reply)

        if not needs_assistant:
            print("   ✅ 无需助手协助，直接回复")
            # 记录到短期记忆（快速回答场景）
            MemoryCore.append_to_file("short_memories.md",
                f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n**用户**：{user_input}\n**yume**：{initial_reply}")
            return [self._format_reply(initial_reply)]

        # 步骤2：需要助手协助，先告诉用户"我想想"（首条触发）
        print("   🤔 需要助手协助，告诉用户'我想想'")
        thinking_reply = "我想想..."
        thinking_reply_dict = self._format_reply(thinking_reply)

        # 立即返回第一个回复（"我想想..."），让用户知道AI正在处理
        # 注意：外部调用者需要等待这个回复播放完毕后再继续

        # 步骤3：DeepSeek执行任务
        print("   🔧 DeepSeek执行任务...")
        final_summary, all_thoughts, intermediate_thoughts = self.deepseek_execute_task(user_input, initial_reply)

        intermediate_replies = []

        # 步骤4：千问基于最终结果生成回复
        print("   💬 千问生成最终回复...")
        print(f"   📊 DeepSeek总结: {final_summary[:100]}..." if len(final_summary) > 100 else f"   📊 DeepSeek总结: {final_summary}")
        print(f"   📝 DeepSeek思考步骤数: {len(all_thoughts)}")

        # 使用内存上下文（零磁盘I/O）
        persona = self.mem_personality or "AI虚拟主播"
        short = self._format_short_term_history() or "（暂无近期记录）"

        recent_thoughts_raw = self.mem_mood_template or ""
        if recent_thoughts_raw and "❌" not in recent_thoughts_raw:
            thought_lines = [line.strip() for line in recent_thoughts_raw.split('\n') if line.strip()]
            recent_thoughts = "近期的自言自语：\n" + "\n".join(thought_lines[-6:])
        else:
            recent_thoughts = "（没有近期自言自语）"

        long_term = self.mem_long_term or "（暂无长期记忆）"

        context = QWEN_SYSTEM_PROMPT.format(
            persona_content=persona,
            long_term_memory=long_term,
            short_memory=short,
            recent_thoughts=recent_thoughts
        )

        # 添加助手总结
        context += f"\n\n【助手执行总结】：{final_summary}"
        if all_thoughts:
            context += f"\n\n【助手思考过程】：\n" + "\n".join(f"- {thought}" for thought in all_thoughts[-5:])  # 只显示最后5条

        context += f"\n\n【用户输入】：{user_input}"
        context += "\n\n请基于助手的执行结果，给出最终的人格化回复。"

        # 调试：打印部分上下文
        print(f"   📋 传递给千问的上下文长度: {len(context)} 字符")
        print(f"   📖 上下文结尾部分:\n{context[-500:] if len(context) > 500 else context}")

        final_reply = self.llm_qwen.ask(context, temperature=0.7)

        # 步骤5：记录到短期记忆
        MemoryCore.append_to_file("short_memories.md",
            f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n**用户**：{user_input}\n**yume**：{final_reply}")

        print(f"   ✅ 协作完成，回复长度: {len(final_reply)}")

        final_reply_dict = self._format_reply(final_reply)

        # 构建完整回复列表：我想想... + 思考过程互动 + 最终回复
        all_replies = [thinking_reply_dict]
        if intermediate_replies:
            all_replies.extend(intermediate_replies)
        all_replies.append(final_reply_dict)

        print(f"   📊 总回复数: {len(all_replies)} (我想想... + {len(intermediate_replies)} 个思考过程互动 + 最终回复)")
        return all_replies

    def _needs_assistant(self, user_input: str, initial_reply: str) -> bool:
        """
        判断是否需要助手协助

        简单的启发式规则：
        1. 用户要求查询记忆、总结、写日记等 -> 需要
        2. 用户询问技术性问题 -> 需要
        3. 简单问候或闲聊 -> 不需要
        """
        # 关键词列表
        tool_keywords = ["总结", "记忆", "日记", "查询", "搜索", "查找", "记录", "归档", "更新", "删除", "清空", "创建", "工具"]

        user_input_lower = user_input.lower()

        for keyword in tool_keywords:
            if keyword in user_input_lower:
                return True

        # 检查回复是否暗示需要工具
        if any(word in initial_reply for word in ["我查一下", "我看看", "我找找", "需要查询", "需要搜索"]):
            return True

        return False

    def _get_mumble_action_for_tool(self, tool_name: str) -> str:
        """
        根据工具名称获取对应的嘟囔动作

        Args:
            tool_name: 工具名称

        Returns:
            嘟囔动作字符串，如果没有匹配则返回空字符串
        """
        # 工具类型到嘟囔动作的映射
        tool_to_action = {
            "search_memory": "searching",
            "search_by_date": "searching",
            "search_specific_memory": "searching",
            "precise_search_memory": "searching",
            "load_memory": "analyzing",
            "update_memory": "coding",
            "update_long_term_memory": "coding",
            "write_daily_diary": "coding",
            "auto_write_diary": "coding",
            "write_weekly_summary": "coding",
            "write_monthly_summary": "coding",
            "write_yearly_summary": "coding",
            "create_file": "coding",
            "clear_file": "coding",
            "delete_memory_entry": "coding",
            "delete_memory_file": "coding",
            "locate_memory_entry": "searching",
        }

        # 查找匹配的动作
        for key, action in tool_to_action.items():
            if key in tool_name:
                return action

        # 默认返回analyzing
        return "analyzing"

    def _format_reply(self, reply_text: str) -> Dict[str, Any]:
        """
        格式化回复为字典格式

        Args:
            reply_text: 回复文本

        Returns:
            格式化后的回复字典
        """
        # 简单情感分析（可后续优化）
        emotion_keywords = {
            "开心": ["高兴", "开心", "喜欢", "好", "棒", "耶", "哈哈"],
            "生气": ["生气", "讨厌", "烦", "哼", "恼火", "不爽"],
            "伤心": ["难过", "伤心", "呜呜", "哭", "悲伤"],
            "温柔": ["谢谢", "请", "不好意思", "抱歉", "晚安"],
            "困惑": ["?", "？", "什么", "怎么", "为什么", "如何"]
        }

        emotion = "neutral"
        reply_lower = reply_text.lower()

        for emo, keywords in emotion_keywords.items():
            for keyword in keywords:
                if keyword in reply_lower:
                    emotion = emo
                    break
            if emotion != "neutral":
                break

        # 简单动作检测（可后续优化）
        action = ""
        if "笑" in reply_text:
            action = "微笑"
        elif "点头" in reply_text:
            action = "点头"
        elif "摇头" in reply_text:
            action = "摇头"

        return {
            "text": reply_text,
            "emotion": emotion,
            "action": action
        }


# ==================== 工具函数 ====================

def create_collaborator() -> LLMCollaborator:
    """
    创建协作管理器实例

    Returns:
        LLMCollaborator实例
    """
    import config

    # 创建千问实例
    if not config.QWEN_API_KEY:
        print("⚠️ 警告：QWEN_API_KEY未配置，将使用DeepSeek作为备用")
        llm_qwen = LLMAPI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            model=config.DEEPSEEK_MODEL
        )
    else:
        llm_qwen = LLMAPI(
            api_key=config.QWEN_API_KEY,
            base_url=config.QWEN_BASE_URL,
            model=config.QWEN_MODEL
        )

    # 创建DeepSeek实例
    llm_deepseek = LLMAPI(
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
        model=config.DEEPSEEK_MODEL
    )

    return LLMCollaborator(llm_qwen, llm_deepseek)