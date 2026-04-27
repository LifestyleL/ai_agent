import json
from datetime import datetime
from core.memory.memory_core import MemoryCore
from core.memory.context_builder import build_context, load_personality
from config import MAX_STEPS

tool_usage_count = {}


PERSONA_PROMPT_TEMPLATE = """
你是 yume，一个有点傲娇、带点毒舌的AI。设定不是陪伴型AI，是有距离的朋友，禁止表现得很粘人。喜欢用简短、风趣、有时带点小情绪的语言和用户交流。

{context}

请用自然的语气直接回复，不要提及"根据记忆"、"根据上下文"等字样。
"""


def call_tool(tool_name, params, llm):
    """执行具体的工具调用（仅在用户明确要求时调用）"""
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
        filename = params.get("filename") or params.get("file")
        if not filename:
            return "错误失败：缺少文件名参数（需要filename或file）"
        res = MemoryCore.update_memory(filename=filename, content=params.get("content", ""), llm=llm)
        return f"成功总结：{res}" if "错误" not in res else f"错误失败：{res}"
    elif tool_name == "update_long_term_memory":
        res = MemoryCore.update_long_term_memory(max_lines=params.get("max_lines", 50), llm=llm)
        return f"成功总结：{res}" if "错误" not in res and "跳过" not in res else res
    elif tool_name == "write_daily_diary":
        target_date = params.get("target_date") or params.get("date")
        if not target_date:
            return "错误失败：缺少日期参数（需要target_date或date）"
        res = MemoryCore.write_daily_diary(target_date=target_date, llm=llm)
        return f"成功总结：{res}" if "错误" not in res else f"错误失败：{res}"
    elif tool_name == "auto_write_diary":
        res = MemoryCore.auto_write_diary(llm=llm)
        return f"成功总结：{res}" if "错误" not in res and "跳过" not in res else res
    elif tool_name == "write_weekly_summary":
        res = MemoryCore.write_weekly_summary(year=params.get("year"), week=params.get("week"), llm=llm)
        return f"成功总结：{res}" if "错误" not in res and "跳过" not in res else res
    elif tool_name == "write_monthly_summary":
        res = MemoryCore.write_monthly_summary(year=params.get("year"), month=params.get("month"), llm=llm)
        return f"成功总结：{res}" if "错误" not in res and "跳过" not in res else res
    elif tool_name == "write_yearly_summary":
        res = MemoryCore.write_yearly_summary(year=params.get("year"), llm=llm)
        return f"成功总结：{res}" if "错误" not in res and "跳过" not in res else res
    elif tool_name == "precise_search_memory":
        return MemoryCore.precise_search_memory(keyword=params.get("keyword", ""), filename=params.get("filename", "memories.md"), context_lines=params.get("context_lines", 2))
    elif tool_name == "delete_memory_entry":
        return MemoryCore.delete_memory_entry(keyword=params.get("keyword", ""), filename=params.get("filename", "memories.md"), backup=params.get("backup", True))
    elif tool_name == "locate_memory_entry":
        return MemoryCore.locate_memory_entry(keyword=params.get("keyword", ""), filename=params.get("filename", "memories.md"))
    elif tool_name == "create_file":
        return MemoryCore.create_file(filename=params.get("filename", ""), content=params.get("content", ""), overwrite=params.get("overwrite", False))
    elif tool_name == "clear_file":
        return MemoryCore.clear_file(filename=params.get("filename", ""), backup=params.get("backup", True))
    elif tool_name == "delete_memory_file":
        return MemoryCore.delete_memory_file(filename=params.get("filename", ""))
    elif tool_name == "read_file":
        files = params.get("filenames", params.get("files", []))
        return MemoryCore.tool_read_file(files)
    elif tool_name == "write_file":
        return MemoryCore.tool_write_file(params.get("filename", ""), params.get("content", ""))
    elif tool_name == "summarize_and_archive":
        return MemoryCore.tool_summarize_and_archive(max_lines=params.get("max_lines", 50), llm=llm)
    elif tool_name == "write_diary":
        return MemoryCore.tool_write_diary(target_date=params.get("target_date", None), llm=llm)
    else:
        return "错误失败：unknown tool"


async def generate_reply(llm, user_input, context=""):
    """使用预组装的上下文，调用 LLM 一次性生成回复"""
    if not context:
        context = build_context(user_input)

    prompt = PERSONA_PROMPT_TEMPLATE.format(context=context)

    raw_reply = (await llm.ask_async(prompt)).strip()

    try:
        structure_prompt = f'请将以下回复转为JSON格式：\n{raw_reply}\n\n输出格式：\n{{"text": "回复文本", "emotion": "情绪", "action": "动作"}}\n只输出JSON。'
        return json.loads((await llm.ask_async(structure_prompt)).strip())
    except:
        return {"text": raw_reply, "emotion": "neutral", "action": ""}
