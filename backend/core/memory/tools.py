"""
记忆工具函数 (模块级函数，原 MemoryCore @staticmethod)
"""
import json
import os
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def load_files(filenames: list) -> str:
    if not filenames:
        return ""
    memory_root = Path(__file__).parent.parent.parent / "agent_memory"
    result = []
    for name in filenames:
        name = name.strip()
        path = memory_root / name
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                # 日记文件：优先返回 ## 日记 摘要段
                if "diary/daily/" in name and name.endswith(".md"):
                    content = _extract_diary_section(content)
                result.append(content)
            except Exception as e:
                print(f"[WARN] 加载 {name} 失败: {e}")
                result.append("")
        else:
            result.append("")
    return result[0] if result else ""


def _extract_diary_section(content: str) -> str:
    """从日记 .md 文件中提取优先级最高的内容段。
    优先级 1: ## 日记（LLM 摘要）
    优先级 2: ## 浓缩对话（原始对话）
    都没有: 返回前 500 字符
    """
    # 优先提取 ## 日记
    m = re.search(r'## 日记\n(.*?)(?=\n## |\n---|\Z)', content, re.DOTALL)
    if m:
        summary = m.group(1).strip()
        if summary:
            return summary

    # 其次提取 ## 浓缩对话
    m = re.search(r'## 浓缩对话\n(.*?)(?=\Z)', content, re.DOTALL)
    if m:
        condensed = m.group(1).strip()
        if condensed:
            return condensed

    # 都没有，返回文件前 500 字符
    return content[:500].strip()


def append_to_file(filename: str, content: str) -> None:
    memory_root = Path(__file__).parent.parent.parent / "agent_memory"
    fpath = memory_root / filename
    try:
        fpath.parent.mkdir(parents=True, exist_ok=True)
        with open(fpath, 'a', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print(f"[WARN] 追加写入 {filename} 失败: {e}")


def get_random_long_term_memory(n: int = 3) -> str:
    try:
        memory_root = Path(__file__).parent.parent.parent / "agent_memory"
        cards_dir = memory_root / "cards"
        if not cards_dir.exists():
            return ""
        cards_jsonl = cards_dir / "cards.jsonl"
        if not cards_jsonl.exists():
            return ""
        lines = []
        with open(cards_jsonl, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    lines.append(line)
        if lines:
            chosen = random.sample(lines, min(n, len(lines)))
            contents = []
            for line in chosen:
                try:
                    d = json.loads(line)
                    contents.append(d.get("content", "")[:200])
                except Exception:
                    pass
            return "\n".join(contents) if contents else ""
    except Exception:
        pass
    return ""


def set_short_term_memory_cache(history: list) -> None:
    if not history:
        return
    memory_root = Path(__file__).parent.parent.parent / "agent_memory"
    fpath = memory_root / "core/short_term.json"
    try:
        existing = {}
        if fpath.exists():
            try:
                existing = json.loads(fpath.read_text(encoding="utf-8"))
            except Exception:
                pass
        dialogues = []
        for item in history:
            if isinstance(item, dict) and "role" in item:
                dialogues.append({
                    "role": item["role"],
                    "content": item.get("content", ""),
                    "timestamp": item.get("timestamp", datetime.now().isoformat())
                })
        data = {
            "dialogues": dialogues,
            "current_emotion": existing.get("current_emotion", {}),
            "updated_at": datetime.now().isoformat()
        }
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[WARN] 短期记忆缓存同步失败: {e}")


def write_file(filename: str, content: str) -> None:
    memory_root = Path(__file__).parent.parent.parent / "agent_memory"
    fpath = memory_root / filename
    try:
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
    except Exception as e:
        print(f"[WARN] 写入文件 {filename} 失败: {e}")


def create_file(filename: str = "", content: str = "", overwrite: bool = False) -> str:
    if not filename:
        return "错误：缺少文件名"
    memory_root = Path(__file__).parent.parent.parent / "agent_memory"
    fpath = memory_root / filename
    try:
        fpath.parent.mkdir(parents=True, exist_ok=True)
        if fpath.exists() and not overwrite:
            return f"文件 {filename} 已存在"
        fpath.write_text(content, encoding="utf-8")
        return f"文件 {filename} 创建成功"
    except Exception as e:
        return f"文件创建失败: {e}"


def load_tool_docs() -> str:
    try:
        memory_root = Path(__file__).parent.parent.parent / "agent_memory"
        path = memory_root / "tools" / "tool_docs.md"
        if path.exists():
            return path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[WARN] 加载工具文档失败: {e}")
    return "工具文档加载失败"


def tool_read_file(filenames) -> str:
    return load_files(filenames if isinstance(filenames, list) else [filenames])


def tool_write_file(filename: str, content: str) -> str:
    return create_file(filename=filename, content=content, overwrite=True)


def tool_search_memory(keyword: str, target_date=None, llm=None) -> str:
    memory_root = Path(__file__).parent.parent.parent / "agent_memory"
    if not memory_root.exists():
        return "记忆目录不存在"
    try:
        from core.memory.card_store import CardStore
        store = CardStore(memory_root=memory_root)
        store.load_all()
        from utils.text_utils import extract_keywords
        tags = extract_keywords(keyword, max_kw=3)
        cards = store.retrieve(query_tags=tags, limit=5)
        if cards:
            lines = [f"搜索到 {len(cards)} 条关于 '{keyword}' 的记忆："]
            for c in cards:
                lines.append(f"- [{c.timestamp[:10]}] {c.topic}: {c.content[:100]}")
            return "\n".join(lines)
    except Exception:
        pass
    results = []
    keyword_lower = keyword.lower()
    for fpath in memory_root.rglob("*"):
        if fpath.name == "short_term.json" or fpath.suffix not in (".md", ".json", ".txt"):
            continue
        try:
            content = fpath.read_text(encoding="utf-8")
        except Exception:
            continue
        idx = content.lower().find(keyword_lower)
        if idx >= 0:
            start = max(0, idx - 60)
            end = min(len(content), idx + len(keyword) + 100)
            snippet = content[start:end].replace("\n", " ").strip()
            rel_path = fpath.relative_to(memory_root)
            results.append(f"[{rel_path}] ...{snippet}...")
        if len(results) >= 5:
            break
    if not results:
        return f"未找到关于 '{keyword}' 的记忆"
    return f"搜索到 {len(results)} 条关于 '{keyword}' 的记忆：\n" + "\n".join(f"- {r}" for r in results)


def tool_summarize_and_archive(max_lines=50, llm=None) -> str:
    return "记忆压缩已由 CardStore 三层算法自动管理"


def tool_write_diary(target_date=None, llm=None) -> str:
    """生成指定日期的日记：收集对话 → LLM 过滤浓缩 → LLM 摘要 → 写入结构化日记"""
    import re
    from core.memory.diary_processor import DiaryProcessor

    memory_root = Path(__file__).parent.parent.parent / "agent_memory"
    date_str = target_date or datetime.now().strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")

    daily_file = memory_root / "diary" / "daily" / f"{date_str}.md"

    # 如果目标日期的 diary 文件还不存在，尝试从草稿提取
    if not daily_file.exists():
        draft_path = memory_root / "diary" / "drafts" / "daily_draft.txt"
        if draft_path.exists():
            try:
                draft_content = draft_path.read_text(encoding="utf-8")
                # 尝试提取目标日期的内容
                sections: dict = {}
                current_date = None
                for line in draft_content.split("\n"):
                    m = re.match(r'^--- (\d{4}-\d{2}-\d{2}) ---$', line)
                    if m:
                        current_date = m.group(1)
                        if current_date not in sections:
                            sections[current_date] = []
                        continue
                    if current_date:
                        sections[current_date].append(line)

                # 如果是今天但没有日期标签，用全部内容
                if not sections and date_str == today:
                    sections[date_str] = draft_content.split("\n")

                if date_str in sections:
                    body = "\n".join(sections[date_str]).strip()
                    if body:
                        daily_file.parent.mkdir(parents=True, exist_ok=True)
                        daily_file.write_text(f"# {date_str} 对话日记\n\n{body}", encoding="utf-8")
            except Exception as e:
                print(f"[tool_write_diary] 从草稿创建日记文件失败: {e}")

    if not daily_file.exists():
        return f"日记文件 {date_str}.md 不存在，草稿中也没有该日期的对话记录。可以跟我说'写日记'让我生成今天的日记。"

    # 检查是否已经生成了日记摘要（有 ## 日记 才算处理过）
    existing = daily_file.read_text(encoding="utf-8")
    if "## 日记" in existing:
        return f"{date_str} 日记已经生成过了，不需要重复处理。"

    processor = DiaryProcessor(memory_root)
    success = processor.process_daily_diary_sync(date_str)
    if success:
        return f"{date_str} 日记已生成完毕。"
    else:
        return f"{date_str} 日记生成失败，请检查后端日志。"
