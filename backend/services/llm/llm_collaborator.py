"""
LLM协作管理器：实现DeepSeek（工具调用）和千问（人设对话）的双模型协作
"""

import json
import time
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional, Generator
from core.llm.llm_api import LLMAPI
from core.memory.memory_core import MemoryCore
from core.agent.agent_brain import call_tool, generate_reply
from core.event.event_bus import event_bus, EventType, Event

# ==================== 提示词模板 ====================

QWEN_SYSTEM_PROMPT = """你是yume，一个有点傲娇、带点毒舌的AI。设定不是陪伴型AI，是有距离的朋友，禁止表现得很粘人。
喜欢用简短、风趣、有时带点小情绪的语言和用户交流。

你有一个专门的工具执行助手（DeepSeek模型），负责处理工具调用、信息检索等任务。
【重要】：所有记忆操作（包括记录对话到短期记忆）都由系统自动处理，你不需要关心记忆写入，也不会在回复中提到记忆写入相关的内容。

【日记系统】：
你拥有日记系统，会自动将每天的对话和事件总结写入日记。
日记存储在 agent_memory/diary/daily/ 目录下，按日期命名。
当用户要求你查看日记、回忆过去的事情、或者查找历史记录时，
你应该坦然承认你有日记，并且可以尝试回忆或查找相关内容。
不要否认你有日记系统。

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

【当前日期】：
{current_date}

请用自然的语气直接回复。
"""


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

    def _build_qwen_context(self, user_input: str, deepseek_thoughts: List[str] = None, tool_summary: str = None) -> str:
        """
        构建 Qwen 上下文字符串（供流式和非流式共用）
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

        # 获取当前日期
        current_date = datetime.now().strftime("%Y年%m月%d日")

        # 构建上下文
        context = QWEN_SYSTEM_PROMPT.format(
            persona_content=persona,
            long_term_memory=long_term,
            short_memory=short,
            recent_thoughts=recent_thoughts,
            current_date=current_date
        )

        # 如果有DeepSeek的思考步骤，添加到上下文
        if deepseek_thoughts:
            context += f"\n\n【助手思考过程】：\n" + "\n".join(f"- {thought}" for thought in deepseek_thoughts)

        # 如果有工具总结，添加到上下文
        if tool_summary:
            context += f"\n\n【助手查询到的信息】：{tool_summary}"

        # 添加用户输入
        context += f"\n\n【用户输入】：{user_input}"

        # 如果有助手思考或工具总结，提示yume回应
        if deepseek_thoughts or tool_summary:
            context += "\n\n请基于以上信息，用自然的语气直接回复用户，不要提及你使用了工具或助手。"

        return context

    def qwen_analyze_with_context(self, user_input: str, deepseek_thoughts: List[str] = None, tool_summary: str = None) -> str:
        """
        千问模型分析用户输入，考虑DeepSeek的思考过程

        Args:
            user_input: 用户输入
            deepseek_thoughts: DeepSeek的思考步骤列表

        Returns:
            千问的回复文本
        """
        context = self._build_qwen_context(user_input, deepseek_thoughts, tool_summary)
        # 调用千问模型
        reply = self.llm_qwen.ask(context, temperature=0.7)
        return reply


    def _deepseek_execute_loop(self, user_input: str, tools_json: str, initial_decision: dict) -> Tuple[str, List[str]]:
        """
        DeepSeek 多轮工具调用循环（内部方法）
        """
        messages = [
            {"role": "system", "content": DEEPSEEK_SYSTEM_PROMPT.format(tools_json=tools_json, history="", user_question=user_input)},
            {"role": "assistant", "content": json.dumps(initial_decision)} # 把第一次决策塞进去
        ]

        tool_usage_count = {}
        max_steps = 5
        all_thoughts = []

        for step in range(max_steps):
            result = self.llm_deepseek.chat(messages, temperature=0.2)
            if "error" in result:
                return f"工具执行出错: {result['error']}", all_thoughts

            try:
                response = result["choices"][0]["message"]["content"].strip()
                action = json.loads(response)
            except Exception as e:
                return "工具执行解析失败", all_thoughts

            thought = action.get("thought", "")
            if thought: all_thoughts.append(thought)

            # 判断是否可以结束
            if not action.get("need_tool", False) and action.get("can_answer", False):
                event_bus.publish(EventType.SUBCONSCIOUS_ACTION, source="LLMCollaborator", action="done", timestamp=time.time())
                return "信息已收集完毕", all_thoughts

            # 执行工具
            if action.get("need_tool", False):
                tool_name = action.get("tool_name", "")
                params = action.get("params", {})

                # 频率限制
                if tool_usage_count.get(tool_name, 0) >= 2:
                    continue
                tool_usage_count[tool_name] = tool_usage_count.get(tool_name, 0) + 1

                # 触发嘟囔（保留原有优秀设计）
                mumble_action = self._get_mumble_action_for_tool(tool_name)
                if mumble_action:
                    event_bus.publish(EventType.SUBCONSCIOUS_ACTION, source="LLMCollaborator", action=mumble_action, tool_name=tool_name, timestamp=time.time())

                # 调用工具
                tool_result = call_tool(tool_name, params, self.llm_deepseek)

                if "错误" in str(tool_result) or "失败" in str(tool_result):
                    event_bus.publish(EventType.SUBCONSCIOUS_ACTION, source="LLMCollaborator", action="frustrated", timestamp=time.time())

                # 结果回传
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content": f"工具调用结果：{tool_result}"})
            else:
                # 既不需要工具也不能回答，打破死循环
                break

        return "达到最大执行次数", all_thoughts

    def collaborate(self, user_input: str) -> List[Dict[str, Any]]:
        """主协作流程（同步兼容层，实际底层已走流式）"""
        print(f"\n[协作开始-兼容层] 用户输入: {user_input}")
        full_text = ""

        final_emotion = "neutral"
        final_action = ""
        replies_to_return = []

        # 调用流式接口并收集结果
        for stream_chunk in self.collaborate_stream(user_input):
            if stream_chunk["type"] == "thinking":
                replies_to_return.append(self._format_reply(stream_chunk["text"]))
            elif stream_chunk["type"] == "chunk":
                full_text += stream_chunk["text"]
            elif stream_chunk["type"] == "done":
                final_emotion = stream_chunk.get("emotion", "neutral")
                final_action = stream_chunk.get("action", "")

        # 记录记忆
        # if full_text:
            # [V1→V3] 已废弃：写入已由 memory_core.add_short_term() 接管
            # MemoryCore.append_to_file("short_memories.md", f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n**用户**：{user_input}\n**yume**：{full_text}")

        # 构建最终的同步返回格式
        if not replies_to_return:
            replies_to_return.append(self._format_reply(full_text))
        else:
            # 如果有 thinking，把最终文本作为第二个回复追加进去
            final_dict = {"text": full_text, "emotion": final_emotion, "action": final_action}
            replies_to_return.append(final_dict)

        return replies_to_return

    def collaborate_stream(self, user_input: str) -> Generator[Dict[str, Any], None, None]:
        """
        流式协作接口（生成器）
        Yields 格式：
        - {"type": "thinking", "text": "稍等..."} # 预制提示语
        - {"type": "chunk", "text": "嗯"} # Qwen 流式输出的片段
        - {"type": "done", "text": "", "emotion": "neutral", "action": ""} # 结束信号
        """
        print(f"\n[协作开始] 用户输入: {user_input}")

        # 1. 预加载工具列表（替代 DeepSeek 自己查表，省 1-2s）
        try:
            tools_json = MemoryCore.load_files(["tools/tools_index.md"])
            # 调试：打印工具列表内容摘要
            if tools_json and tools_json.strip():
                preview = tools_json[:200] + ("..." if len(tools_json) > 200 else "")
                print(f"   [调试] 工具列表加载成功，长度: {len(tools_json)} 字符")
                print(f"   [调试] 前200字符: {preview}")
            else:
                print(f"   [警告] 工具列表为空或空白")
                tools_json = "无可用工具列表"
        except Exception as e:
            print(f"   [错误] 加载工具列表失败: {e}")
            tools_json = "无可用工具列表"

        # 2. 先检查短期记忆中是否有相关内容（软提示）
        bigram_hint = ""  # 存储匹配提示信息，为空表示无显著匹配

        # [V1→V3] 动作意图排除：以下模式不应被 bigram 拦截
        action_patterns = [
            "查一查", "查看", "查查", "找一找", "找找",
            "读一下", "读一读", "看一下", "看一下日记",
            "给我看看", "让我看看", "具体查", "具体看看",
            "搜索", "帮我查", "帮我找", "帮我搜",
            "确认一下", "核实", "验证", "检查",
        ]

        # 在 bigram 匹配之前，先检查动作意图
        should_skip_memory_check = False
        for pattern in action_patterns:
            if pattern in user_input:
                should_skip_memory_check = True
                print(f"[V1→V3] 检测到动作意图 '{pattern}'，放行工具调用")
                break

        # 如果没有动作意图，且存在短期记忆，进行 bigram 匹配（软提示）
        if not should_skip_memory_check and self.short_term_history:
            # [V1→V3] 双字片段匹配：检查用户输入中的双字片段是否出现在短期记忆中
            user_input_lower = user_input.lower()
            # 生成所有双字片段（bigram）
            bigrams = []
            for i in range(len(user_input_lower) - 1):
                bigram = user_input_lower[i:i+2]
                bigrams.append(bigram)

            # 检查最近 20 条短期记忆
            recent_memories = self.short_term_history[-20:] if len(self.short_term_history) > 20 else self.short_term_history
            matched_fragments = []
            best_match_count = 0
            best_match_memory = ""

            for mem in reversed(recent_memories):
                mem_content = mem.get("content", "").lower()
                # 计算匹配的双字片段数量
                match_count = 0
                current_matched = []
                for bigram in bigrams:
                    if bigram in mem_content:
                        match_count += 1
                        current_matched.append(bigram)

                # 记录最佳匹配
                if match_count > best_match_count:
                    best_match_count = match_count
                    best_match_memory = mem_content[:100]  # 截取前100字符
                    matched_fragments = current_matched

            # 匹配阈值：至少有2个独立片段匹配，或者输入很短时至少有1个片段匹配
            threshold = 2 if len(bigrams) >= 2 else 1
            if best_match_count >= threshold:
                # 计算匹配百分比
                match_pct = (best_match_count / len(bigrams)) * 100 if bigrams else 0
                bigram_hint = f"\n[记忆提示] 本地短期记忆中存在相关内容（双字匹配度 {match_pct:.1f}%，匹配片段: {matched_fragments}）。请判断是否仍需要调用工具搜索，还是直接基于已有记忆回答。"
                print(f"[Bigram] 本地匹配度 {match_pct:.1f}%，已注入软提示 (匹配片段: {matched_fragments})")
            else:
                print(f"[Bigram] 无显著本地匹配，走正常工具判断 (匹配片段: {best_match_count}/{len(bigrams)})")
        else:
            # 跳过 bigram 检查（动作意图或无线索）
            print(f"[Bigram] 跳过本地记忆检查 (原因: {'动作意图' if should_skip_memory_check else '无短期记忆'})")

        # 3. 第一次调用 DeepSeek 进行轻量级决策（判断要不要工具）
        print("   => DeepSeek 初步决策...")
        history_str = ""
        # 将 bigram 提示注入用户问题中
        user_question_with_hint = user_input + bigram_hint
        ds_prompt = DEEPSEEK_SYSTEM_PROMPT.format(
            tools_json=tools_json,
            history=history_str,
            user_question=user_question_with_hint
        )

        # 延迟诊断：打印 prompt 信息
        print(f"   [延迟诊断] DeepSeek prompt 总长度: {len(ds_prompt)} 字符")
        # 估算工具列表数量（统计 tool_name 出现次数）
        tool_count = tools_json.count('"tool_name"') if tools_json else 0
        print(f"   [延迟诊断] 工具列表字符数: {len(tools_json)}，估算工具数量: {tool_count}")
        if bigram_hint:
            hint_preview = bigram_hint[:100] + ("..." if len(bigram_hint) > 100 else "")
            print(f"   [延迟诊断] Bigram hint 存在，前100字符: {hint_preview}")
        else:
            print(f"   [延迟诊断] Bigram hint: 无")

        # 所有输入都走 DeepSeek 判断，不再硬拦截
        ds_result = self.llm_deepseek.chat([{"role": "user", "content": ds_prompt}], temperature=0.1)
        # 容错解析
        try:
            decision = json.loads(ds_result["choices"][0]["message"]["content"].strip())
        except:
            decision = {"need_tool": False, "can_answer": True}


        # 3. 如果不需要工具，直接交给 Qwen 流式输出
        if not decision.get("need_tool", False) and decision.get("can_answer", True):
            print("   [√] 无需工具，直接调用 Qwen 流式生成")
            qwen_context = self._build_qwen_context(user_input)
            full_text = ""
            # 延迟诊断：第一条流式输出开始时间戳
            stream_start_time = time.time() * 1000  # 毫秒
            print(f"   [延迟诊断] 第一条流式输出开始时间戳: {stream_start_time:.2f} ms")
            print("[流式输出开始] ", end="", flush=True)  # 流式输出提示
            # 流式输出（带时间戳监控）
            chunk_count = 0
            stream_start_seconds = time.time()
            for chunk_text in self.llm_qwen.ask_stream(qwen_context, temperature=0.7):
                chunk_count += 1
                print(chunk_text, end="", flush=True)  # 控制台实时打印
                full_text += chunk_text
                yield {"type": "chunk", "text": chunk_text}
                # 每5个chunk打印一次时间戳
                if chunk_count % 5 == 0:
                    elapsed = time.time() - stream_start_seconds
                    chunk_preview = chunk_text[:20] + ("..." if len(chunk_text) > 20 else "")
                    print(f"\n   [Stream] chunk#{chunk_count} +{elapsed:.2f}s: '{chunk_preview}'")
            print()  # 流式输出结束换行
            # 分析情感和动作
            formatted = self._format_reply(full_text)
            yield {"type": "done", "text": "", "emotion": formatted["emotion"], "action": formatted["action"]}
            return

        # 4. 如果需要工具，先 yield 预制提示语
        print("   [工具] 需要工具，进入执行循环...")
        yield {"type": "thinking", "text": "稍等，我查一下。"}

        # 调用多轮执行方法
        final_summary, all_thoughts = self._deepseek_execute_loop(user_input, tools_json, decision)

        # 5. Qwen 流式输出结果
        print("   [回复] Qwen 流式生成最终回复...")
        qwen_context = self._build_qwen_context(user_input, deepseek_thoughts=all_thoughts, tool_summary=final_summary)
        full_text = ""
        print("[流式输出开始] ", end="", flush=True)  # 流式输出提示
        for chunk_text in self.llm_qwen.ask_stream(qwen_context, temperature=0.7):
            print(chunk_text, end="", flush=True)  # 控制台实时打印
            full_text += chunk_text
            yield {"type": "chunk", "text": chunk_text}
        print()  # 流式输出结束换行
        # 分析情感和动作
        formatted = self._format_reply(full_text)
        yield {"type": "done", "text": "", "emotion": formatted["emotion"], "action": formatted["action"]}


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
        print("[警告] QWEN_API_KEY未配置，将使用DeepSeek作为备用")
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