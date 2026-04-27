"""
上下文自动组装器
替代旧的"LLM 决策→工具调用→结果注入"模式。
每次生成回复前，自动从磁盘组装上下文，塞给 LLM 一次性生成。
"""

import re
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List


def _get_memory_root() -> Path:
    return Path(__file__).parent.parent.parent / "agent_memory"


def load_personality() -> str:
    path = _get_memory_root() / "personality.md"
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            pass
    return ""


def load_short_term_history(max_turns: int = 10) -> str:
    """从 short_term.json 加载最近 N 轮对话，格式化为字符串"""
    path = _get_memory_root() / "short_term.json"
    if not path.exists():
        return ""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        dialogues = data.get("dialogues", [])
        if not dialogues:
            return ""

        recent = dialogues[-(max_turns * 2):]
        lines = []
        for d in recent:
            role = "用户" if d.get("role") == "user" else "yume"
            content = d.get("content", "")
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)
    except Exception:
        return ""


def _extract_keywords(text: str, max_words: int = 5) -> List[str]:
    """从用户输入中提取关键词，用于搜索长期记忆"""
    stop_words = {
        "的", "了", "是", "在", "我", "你", "他", "她", "它", "们",
        "和", "与", "或", "也", "就", "都", "而", "及", "把", "被",
        "让", "从", "到", "对", "向", "往", "用", "以", "为", "因为",
        "所以", "但是", "虽然", "如果", "可以", "没有", "这个", "那个",
        "什么", "怎么", "怎样", "哪", "吗", "呢", "吧", "啊", "哦",
        "嗯", "哈", "呀", "嘛", "不", "很", "会", "要", "有", "能",
        "一个", "一下", "一点", "些", "知道", "觉得", "说", "想",
        "去", "来", "做", "看", "让", "给", "还", "已经", "刚才",
        "现在", "今天", "昨天", "明天",
    }
    words = re.findall(r"[一-鿿\w]+", text)
    keywords = []
    for w in words:
        if w not in stop_words and len(w) >= 2:
            keywords.append(w)
    # 去重，保留前 max_words 个
    seen = set()
    result = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            result.append(kw)
    return result[:max_words]


def search_long_term(keywords: List[str], max_results: int = 3) -> str:
    """在 agent_memory/ 目录下搜索包含关键词的文件，返回匹配片段"""
    root = _get_memory_root()
    if not root.exists():
        return ""

    found_snippets: List[str] = []
    search_files: List[Path] = []

    # 收集可搜索的文件
    for pattern in ["*.md", "*.json"]:
        search_files.extend(root.rglob(pattern))

    for fpath in search_files:
        if fpath.name == "short_term.json":
            continue
        try:
            content = fpath.read_text(encoding="utf-8")
        except Exception:
            continue

        for kw in keywords:
            idx = content.lower().find(kw.lower())
            if idx >= 0:
                start = max(0, idx - 40)
                end = min(len(content), idx + len(kw) + 80)
                snippet = content[start:end].replace("\n", " ")
                label = fpath.relative_to(root)
                found_snippets.append(f"[{label}] ...{snippet}...")
                break

        if len(found_snippets) >= max_results:
            break

    if found_snippets:
        return "相关记忆：\n" + "\n".join(found_snippets[:max_results])
    return ""


def build_context(
    user_input: str,
    emotion: Optional[Dict] = None,
    max_history_turns: int = 10,
) -> str:
    """
    主入口：自动组装完整上下文，返回格式字符串供 LLM 直接使用。

    Returns:
        组装好的上下文字符串，可直接注入 PERSONA_PROMPT
    """
    persona = load_personality()
    short_history = load_short_term_history(max_history_turns)
    keywords = _extract_keywords(user_input)
    long_term_snippets = search_long_term(keywords) if keywords else ""

    parts: List[str] = []

    if persona:
        parts.append(f"【人设】\n{persona}")

    if long_term_snippets:
        parts.append(f"【相关长期记忆】\n{long_term_snippets}")
    else:
        parts.append("【相关长期记忆】\n（无相关记忆）")

    if short_history:
        parts.append(f"【近期对话】\n{short_history}")
    else:
        parts.append("【近期对话】\n（暂无近期记录）")

    if emotion:
        emo_type = emotion.get("type", "neutral")
        emo_strength = emotion.get("strength", 0.5)
        parts.append(f"【当前情绪】\n{emo_type} (强度: {emo_strength:.1f})")

    parts.append(f"【当前日期】\n{datetime.now().strftime('%Y年%m月%d日')}")

    parts.append(f"【用户输入】\n{user_input}")

    return "\n\n".join(parts)
