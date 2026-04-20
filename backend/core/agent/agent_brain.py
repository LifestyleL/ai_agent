import json
from datetime import datetime
from core.memory.memory_core import MemoryCore
from config import MAX_STEPS

tool_usage_count = {}

THINKING_PROMPT_TEMPLATE = """
你是 决策工具模型，只负责决策。
**工具使用说明**：tools/tool_docs.md 文件有所有工具的详细描述、参数和示例，tools/tools_index.md 文件有前10个常用工具列表。如果对某个工具的用途、参数或调用方式拿不准，请先查看该文件。调用方式：使用 load_memory 工具，参数 files 设置为 ["tools/tool_docs.md"]
你必须根据【记忆索引】判断要加载哪些记忆文件，或者是否需要搜索记忆。
【当前日期】: {current_date}
【记忆索引】: {index_content}

【铁律】
- 需要查找过去记忆时使用 search_memory 或 search_by_date
- 每个工具最多调用1次，除非有明确需要重试的原因（如搜索不同关键词）
- 一旦获得信息，必须评估是否"足够回答"
- 如果工具返回"未找到" → 直接 "ready"
- 严禁重复无意义调用工具
- 删除操作需谨慎，系统会自动备份
- 如果用户要求清空、删除、创建或修改文件，应使用相应工具（create_file, clear_file, delete_memory_entry, delete_memory_file, update_memory）而不是重复查看文件

【场景化工具选择】
当用户明确要求时，直接使用对应工具：
1. 用户要求"总结记忆"、"整理记忆"、"更新记忆"时 → 使用 update_long_term_memory(max_lines=10) 工具
   - 参数：max_lines=10（较低阈值确保总结）
   - 如果短期记忆不足，工具会返回"跳过"消息，直接将该消息作为结果

2. 用户提到"睡觉"、"结束对话"、"今天就到这里"、"明天见"且希望总结当天 → 使用 auto_write_diary 工具
   - 参数：无（自动检测日期变化）
   - 注意：该工具会自动检测短期记忆中的日期变化，如有跨天则生成日记

3. 用户要求"清空文件" → 使用 clear_file(filename, backup=true) 工具
4. 用户要求"删除文件" → 使用 delete_memory_file(filename) 工具
5. 用户要求"创建文件"、"重新创建" → 使用 create_file(filename, content="", overwrite=true/false) 工具
6. 用户提供新信息需要记录 → 使用 update_memory(filename, content) 工具
7. 用户询问过去的事情 → 使用 search_memory(keyword) 或 search_by_date(start_date, end_date) 工具

关键原则：
1. 不要反复调用 load_memory 来"查看是否应该总结"或"查看文件状态"，直接使用相应工具执行操作！
2. 如果用户要求多个操作（如"总结记忆并写日记"），依次调用相应工具。
3. 调用工具后，检查返回结果：
   - 如果结果包含"成功"、"已"、"完成"等字样 → 操作成功，可进行下一步
   - 如果结果包含"跳过"、"未达到" → 操作被跳过，可进行下一步或直接回答
   - 如果结果包含"错误失败" → 操作失败，可能需要处理错误或直接回答
4. 对于"总结记忆并写日记"场景：
   - 第一步：调用 update_long_term_memory(max_lines=10)
   - 第二步：无论第一步结果如何，都调用 auto_write_diary()
   - 如果 auto_write_diary() 返回错误（如找不到归档文件），可以跳过或告知用户
5. 每个工具最多调用1次来完成一个用户请求，除非有明确需要重试的原因。

【决策目标】
你不是要一直找信息，而是要：
👉 尽快获得"足够回答"的信息，然后停止

情感参数：
happy,sad,angry,fear,gentle,serious,neutral

只输出JSON：
{{
  "thought": "一句话思考（说明是否已足够，或者为什么要查说明书）",
  "type": "tool 或 ready",
  "tool": "工具名称（仅当type为tool时需要）",
  "params": {{}}
}}

示例1（调用工具）：
{{
  "thought": "用户问关于咖啡的事，我需要搜索相关记忆",
  "type": "tool",
  "tool": "search_memory",
  "params": {{"keyword": "咖啡", "limit": 3}}
}}

示例2（直接回答）：
{{
  "thought": "已经获得足够信息，可以回答用户",
  "type": "ready"
}}

【已加载文件】: {loaded_files}

【历史工具记录】:
{context}

【用户输入】:
{user_input}
"""

PERSONA_PROMPT_TEMPLATE = """
你是 yume，一个有点傲娇、带点毒舌的AI。设定不是陪伴型AI，是有距离的朋友，禁止表现得很粘人。喜欢用简短、风趣、有时带点小情绪的语言和用户交流。你有长期记忆和近期记忆，可以检索相关记忆来丰富回答，可以选择直接回答用户。

【核心人设】：
{persona_content}

【长期记忆】：
{long_term_memory}

【相关记忆（刚刚检索）】：
{retrieved_memory}

【近期对话】：
{short_memory}

【近期自言自语】：
{recent_thoughts}

【用户输入】：
{user_input}

请用自然的语气直接回复。
"""


def call_tool(tool_name, params, llm):
    """执行具体的工具调用"""
    tool_usage_count[tool_name] = tool_usage_count.get(tool_name, 0) + 1
    print(f"[工具] 调用工具: {tool_name} | 参数: {params}")

    if tool_name == "load_memory":
        files = params.get("files", [])
        return MemoryCore.load_tool_docs() if "tool_docs.md" in files else MemoryCore.load_files(files)
    elif tool_name == "search_memory":
        return MemoryCore.search_memory(keyword=params.get("keyword", ""), limit=params.get("limit", 5), llm=llm)
    elif tool_name == "search_by_date":
        return MemoryCore.search_by_date(start_date=params.get("start_date"), end_date=params.get("end_date"))
    elif tool_name == "search_specific_memory":
        return MemoryCore.search_specific_memory(keyword=params.get("keyword", ""), target_date=params.get("target_date"))
    elif tool_name == "update_memory":
        # 兼容两种参数名：filename 或 file
        filename = params.get("filename") or params.get("file")
        if not filename:
            return "错误失败：缺少文件名参数（需要filename或file）"
        res = MemoryCore.update_memory(filename=filename, content=params.get("content", ""), llm=llm)
        return f"成功总结：{res}" if "错误" not in res else f"错误失败：{res}"
    elif tool_name == "update_long_term_memory":
        res = MemoryCore.update_long_term_memory(max_lines=params.get("max_lines", 50), llm=llm)
        return f"成功总结：{res}" if "错误" not in res and "跳过" not in res else res
    elif tool_name == "write_daily_diary":
        # 兼容两种参数名：target_date 或 date
        target_date = params.get("target_date") or params.get("date")
        if not target_date:
            return "错误失败：缺少日期参数（需要target_date或date）"
        res = MemoryCore.write_daily_diary(target_date=target_date, llm=llm)
        return f"成功总结：{res}" if "错误" not in res else f"错误失败：{res}"
    elif tool_name == "auto_write_diary":
        res = MemoryCore.auto_write_diary(llm=llm)
        return f"成功总结：{res}" if "错误" not in res and "跳过" not in res else res
    elif tool_name == "write_weekly_summary":
        res = MemoryCore.write_weekly_summary(
            year=params.get("year"),
            week=params.get("week"),
            llm=llm
        )
        return f"成功总结：{res}" if "错误" not in res and "跳过" not in res else res
    elif tool_name == "write_monthly_summary":
        res = MemoryCore.write_monthly_summary(
            year=params.get("year"),
            month=params.get("month"),
            llm=llm
        )
        return f"成功总结：{res}" if "错误" not in res and "跳过" not in res else res
    elif tool_name == "write_yearly_summary":
        res = MemoryCore.write_yearly_summary(
            year=params.get("year"),
            llm=llm
        )
        return f"成功总结：{res}" if "错误" not in res and "跳过" not in res else res
    elif tool_name == "precise_search_memory":
        return MemoryCore.precise_search_memory(
            keyword=params.get("keyword", ""),
            filename=params.get("filename", "memories.md"),
            context_lines=params.get("context_lines", 2)
        )
    elif tool_name == "delete_memory_entry":
        return MemoryCore.delete_memory_entry(
            keyword=params.get("keyword", ""),
            filename=params.get("filename", "memories.md"),
            backup=params.get("backup", True)
        )
    elif tool_name == "locate_memory_entry":
        return MemoryCore.locate_memory_entry(
            keyword=params.get("keyword", ""),
            filename=params.get("filename", "memories.md")
        )
    elif tool_name == "create_file":
        return MemoryCore.create_file(
            filename=params.get("filename", ""),
            content=params.get("content", ""),
            overwrite=params.get("overwrite", False)
        )
    elif tool_name == "clear_file":
        return MemoryCore.clear_file(
            filename=params.get("filename", ""),
            backup=params.get("backup", True)
        )
    elif tool_name == "delete_memory_file":
        return MemoryCore.delete_memory_file(
            filename=params.get("filename", "")
        )
    # ========== 原子工具映射 ==========
    elif tool_name == "read_file":
        files = params.get("filenames", params.get("files", []))
        return MemoryCore.tool_read_file(files)
    elif tool_name == "write_file":
        filename = params.get("filename", "")
        content = params.get("content", "")
        return MemoryCore.tool_write_file(filename, content)
    elif tool_name == "search_memory":
        keyword = params.get("keyword", "")
        target_date = params.get("target_date", None)
        return MemoryCore.tool_search_memory(keyword, target_date, llm=llm)
    elif tool_name == "summarize_and_archive":
        max_lines = params.get("max_lines", 50)
        return MemoryCore.tool_summarize_and_archive(max_lines, llm=llm)
    elif tool_name == "write_diary":
        target_date = params.get("target_date", None)
        return MemoryCore.tool_write_diary(target_date, llm=llm)
    else:
        return "错误失败：unknown tool"


def generate_reply(llm, user_input, context=""):
    """根据人设生成最终的结构化回复"""
    persona = MemoryCore.load_files(["personality.md"]) or "AI虚拟主播"
    # [V1→V3] 已迁移至 V3 读取链路，短期记忆从 short_term.json 获取
    short = "（暂无近期记录）"  # MemoryCore.load_files(["short_memories.md"]) or "（暂无近期记录）"
    
    # 读取刚刚的自言自语
    recent_thoughts_raw = MemoryCore.load_files(["mood_blank.md"]) or ""
    if recent_thoughts_raw and "❌" not in recent_thoughts_raw:
        thought_lines = [line.strip() for line in recent_thoughts_raw.split('\n') if line.strip()]
        recent_thoughts = "近期的自言自语：\n" + "\n".join(thought_lines[-6:])
    else:
        recent_thoughts = "（没有近期自言自语）"
        
    long_term = MemoryCore.load_files(["memories.md"]) or "（暂无长期记忆）"

    # 🌟 修复：把 recent_thoughts 真正传进 Prompt
    prompt = PERSONA_PROMPT_TEMPLATE.format(
        persona_content=persona,
        long_term_memory=long_term,
        retrieved_memory=context or "（无相关记忆）",
        short_memory=short,
        recent_thoughts=recent_thoughts,
        user_input=user_input
    )

    raw_reply = llm.ask(prompt).strip()
    
    try:
        structure_prompt = f'请将以下回复转为JSON格式：\n{raw_reply}\n\n输出格式：\n{{"text": "回复文本", "emotion": "情绪", "action": "动作"}}\n只输出JSON。'
        return json.loads(llm.ask(structure_prompt).strip())
    except:
        return {"text": raw_reply, "emotion": "温柔", "action": ""}


def react_think(llm, user_input):
    """ReAct 大脑主循环：思考 → 调工具 → 思考 → 生成回复"""
    context = ""
    tool_usage_count.clear()
    parse_failures = 0
    loaded_files = set()
    index_content = MemoryCore.load_files(["index.md"])

    for step in range(MAX_STEPS):
        thinking_prompt = THINKING_PROMPT_TEMPLATE.format(
            current_date=datetime.now().strftime("%Y-%m-%d"),
            index_content=index_content,
            loaded_files=list(loaded_files),
            context=context[-700:],
            user_input=user_input
        )

        print(f"\n[Step {step}] 🤖 思考大脑...")
        try:
            raw_think = llm.ask(thinking_prompt).strip()
            
            # 🌟🌟🌟 加上这行，看看大模型到底吐了什么蛇皮东西
            print(f"   [思考] [原始返回]: {raw_think[:150]}")
            
            action = json.loads(raw_think)
        except Exception as e:
            # 🌟🌟🌟 打印报错原因，别默默跳过
            print(f"   ❌ [解析失败]: {e}")
            parse_failures += 1
            if parse_failures > MAX_STEPS // 2:
                print(f"[警告] 解析失败过多，终止思考")
                break
            continue

        print(f"   [想法] 思考: {action.get('thought', '')[:70]}... | 类型: {action.get('type')}")



        if action.get("type") == "ready":
            final_reply = generate_reply(llm, user_input, context)
            # [V1→V3] 已废弃：写入已由 memory_core.add_short_term() 接管
            # MemoryCore.append_to_file("short_memories.md",
            #     f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n**用户**：{user_input}\n**yume**：{final_reply.get('text', '')}")
            return final_reply, context

        elif action.get("type") == "tool":
            tool_name = action.get("tool")
            if tool_usage_count.get(tool_name, 0) >= 3:
                print(f"[警告] {tool_name} 调用过多，强制停止")
                final_reply = generate_reply(llm, user_input, context)
                # [V1→V3] 已废弃：写入已由 memory_core.add_short_term() 接管
                # MemoryCore.append_to_file("short_memories.md",
                #     f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')}\n**用户**：{user_input}\n**yume**：{final_reply.get('text', '')}")
                return final_reply, context

            result = call_tool(tool_name, action.get("params", {}), llm)
            try:
                result_dict = json.loads(result)
                if not result_dict.get('found', True):
                    context += "\n[提示] 未找到任何相关记忆，可以直接回答用户。\n"
            except json.JSONDecodeError:
                # 不是 JSON，保持原来的字符串检查
                if '"found": false' in result:
                    context += "\n[提示] 未找到任何相关记忆，可以直接回答用户。\n"
            
            if tool_name == "load_memory":
                for f in action.get("params", {}).get("files", []):
                    loaded_files.add(f)

            context += f"\n[工具完成] {tool_name}: {str(result)[:200]}\n"

    return {"text": "思考时间太长了...", "emotion": "困惑", "action": ""}, context
