"""
记忆工具函数 (模块级函数，原 MemoryCore @staticmethod)
"""
import json
import os
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


_MEMORY_ROOT = (Path(__file__).parent.parent.parent / "agent_memory").resolve()
_WORKSPACE_ROOT = (Path(__file__).parent.parent.parent).resolve()


def load_files(filenames: list) -> str:
    if not filenames:
        return ""
    result = []
    for name in filenames:
        name = name.strip()
        # list_directory 返回的路径带 agent_memory/ 前缀，_MEMORY_ROOT 已包含
        if name.startswith("agent_memory/"):
            name = name[len("agent_memory/"):]
        try:
            path = _resolve_safe_path(name)
        except ValueError as e:
            print(f"[WARN] 加载 {name} 被拒绝: {e}")
            result.append("")
            continue
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
    try:
        fpath = _resolve_safe_path(filename)
    except ValueError as e:
        print(f"[WARN] 追加写入 {filename} 被拒绝: {e}")
        return
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
    try:
        fpath = _resolve_safe_path(filename)
    except ValueError as e:
        print(f"[WARN] 写入文件 {filename} 被拒绝: {e}")
        return
    try:
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
    except Exception as e:
        print(f"[WARN] 写入文件 {filename} 失败: {e}")


def create_file(filename: str = "", content: str = "", overwrite: bool = False) -> str:
    if not filename:
        return "错误：缺少文件名"
    try:
        fpath = _resolve_safe_path(filename)
    except ValueError as e:
        return f"文件创建被拒绝: {e}"
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


def tool_write_diary(target_date=None, llm=None) -> str:
    """生成指定日期的日记：收集对话 → LLM 过滤浓缩 → LLM 摘要 → 写入结构化日记"""
    import re
    from core.memory.diary_processor import DiaryProcessor

    memory_root = Path(__file__).parent.parent.parent / "agent_memory"
    date_str = target_date or datetime.now().strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")

    daily_file = memory_root / "diary" / "daily" / f"{date_str}.md"

    if not daily_file.exists():
        draft_path = memory_root / "diary" / "drafts" / "daily_draft.txt"
        if draft_path.exists():
            try:
                draft_content = draft_path.read_text(encoding="utf-8")
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
        return f"日记文件 {date_str}.md 不存在，草稿中也没有该日期的对话记录。"

    existing = daily_file.read_text(encoding="utf-8")
    if "## 日记" in existing:
        return f"{date_str} 日记已经生成过了，不需要重复处理。"

    processor = DiaryProcessor(memory_root)
    success = processor.process_daily_diary_sync(date_str)
    if success:
        return f"{date_str} 日记已生成完毕。"
    else:
        return f"{date_str} 日记生成失败，请检查后端日志。"


# ═══════════════════════════════════════════════════════════════
# 操作工具 (P0: list_directory / grep_search)
# ═══════════════════════════════════════════════════════════════

_TEXT_EXTENSIONS = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".cfg",
                    ".toml", ".ini", ".js", ".ts", ".tsx", ".jsx", ".html",
                    ".css", ".xml", ".sh", ".bat", ".ps1", ".log", ".csv", ".env"}


def _resolve_safe_path(filename: str, root: Optional[Path] = None) -> Path:
    """将用户提供的文件名解析到指定 root 内，拒绝路径遍历"""
    root = (root or _MEMORY_ROOT).resolve()

    if os.path.isabs(filename):
        raise ValueError(f"路径遍历拒绝(绝对路径): {filename}")

    parts = filename.replace('\\', '/').split('/')
    for part in parts:
        if part == '..' or '..%' in part or '%2e%2e' in part.lower():
            raise ValueError(f"路径遍历拒绝: {filename}")

    full = (root / filename).resolve()
    try:
        full.relative_to(root)
    except ValueError:
        raise ValueError(f"路径逃逸 root: {filename}")

    return full


def _is_text_file(filepath: Path) -> bool:
    return filepath.suffix.lower() in _TEXT_EXTENSIONS


def _format_tree(path: Path, prefix: str = "", is_last: bool = True) -> list[str]:
    lines = []
    if not path.is_dir():
        return lines
    entries = sorted(path.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    for i, entry in enumerate(entries):
        if entry.name.startswith(".") and entry.name not in (".env",):
            continue
        last = (i == len(entries) - 1)
        connector = "└── " if last else "├── "
        suffix = "/" if entry.is_dir() else ""
        lines.append(f"{prefix}{connector}{entry.name}{suffix}")
        if entry.is_dir():
            ext_prefix = "    " if last else "│   "
            lines.extend(_format_tree(entry, prefix + ext_prefix, last))
    return lines


def tool_list_directory(path: str = ".", recursive: bool = False, max_depth: int = 2) -> str:
    try:
        target = _resolve_safe_path(path, root=_WORKSPACE_ROOT)
    except ValueError as e:
        return f"目录访问被拒绝: {e}"

    if not target.exists():
        return f"目录不存在: {path}"
    if not target.is_dir():
        return f"不是目录: {path}"

    if not recursive or max_depth <= 0:
        entries = sorted(target.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
        lines = [f"目录: {path} ({len(entries)} 项)"]
        for entry in entries:
            if entry.name.startswith(".") and entry.name not in (".env",):
                continue
            suffix = "/" if entry.is_dir() else ""
            lines.append(f"  {entry.name}{suffix}")
        return "\n".join(lines)

    lines = [f"目录: {path} (递归, max_depth={max_depth})"]
    entries = sorted(target.iterdir(), key=lambda e: (e.is_file(), e.name.lower()))
    for i, entry in enumerate(entries):
        if entry.name.startswith(".") and entry.name not in (".env",):
            continue
        last = (i == len(entries) - 1)
        connector = "└── " if last else "├── "
        suffix = "/" if entry.is_dir() else ""
        lines.append(f"{connector}{entry.name}{suffix}")
        if entry.is_dir() and max_depth > 1:
            ext_prefix = "    " if last else "│   "
            tree = _format_tree(entry, ext_prefix, last)
            max_lines = 100
            lines.extend(tree[:max_lines])
            if len(tree) > max_lines:
                lines.append(f"    ... (截断, 共 {len(tree)} 行)")
    return "\n".join(lines)


def tool_grep_search(pattern: str, path: str = ".",
                     recursive: bool = True, file_pattern: str = "*",
                     max_results: int = 50) -> str:
    try:
        target = _resolve_safe_path(path, root=_WORKSPACE_ROOT)
    except ValueError as e:
        return f"搜索被拒绝: {e}"

    if not target.exists():
        return f"路径不存在: {path}"

    import fnmatch
    results = []
    files_scanned = 0

    def _search_file(fpath: Path):
        nonlocal files_scanned
        if len(results) >= max_results:
            return
        if not _is_text_file(fpath):
            return
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return
        files_scanned += 1
        for lineno, line in enumerate(content.split("\n"), 1):
            if len(results) >= max_results:
                break
            if pattern in line:
                rel = fpath.relative_to(_WORKSPACE_ROOT)
                snippet = line.strip()[:200]
                results.append(f"{rel}:{lineno}: {snippet}")

    def _walk_dir(d: Path, depth: int = 0):
        if len(results) >= max_results or depth > 5:
            return
        try:
            for entry in sorted(d.iterdir(), key=lambda e: (e.is_file(), e.name.lower())):
                if len(results) >= max_results:
                    return
                if entry.name.startswith(".") or entry.name in ("__pycache__", "node_modules"):
                    continue
                if entry.is_dir() and recursive:
                    _walk_dir(entry, depth + 1)
                elif entry.is_file():
                    if file_pattern != "*" and not fnmatch.fnmatch(entry.name, file_pattern):
                        continue
                    _search_file(entry)
        except PermissionError:
            pass

    if target.is_file():
        _search_file(target)
    elif target.is_dir():
        _walk_dir(target)

    if not results:
        return f"未找到匹配 '{pattern}' 的结果 (扫描 {files_scanned} 个文件)"

    header = f"搜索 '{pattern}' — {len(results)} 条结果 (扫描 {files_scanned} 个文件)"
    if len(results) >= max_results:
        header += f" [已达上限 {max_results}]"
    return header + "\n" + "\n".join(results)


# ═══════════════════════════════════════════════════════════════
# 回调注册
# ═══════════════════════════════════════════════════════════════

_archive_callback = None


def register_archive_callback(cb):
    global _archive_callback
    _archive_callback = cb


def tool_summarize_and_archive(max_lines=50, llm=None) -> str:
    if _archive_callback:
        return _archive_callback()
    return "记忆压缩已由 CardStore 三层算法自动管理"


# ═══════════════════════════════════════════════════════════════
# 联网搜索
# ═══════════════════════════════════════════════════════════════


def tool_web_search(keywords: str, max_results: int = 5) -> str:
    """DuckDuckGo 联网搜索，返回标题+链接+摘要"""
    if not keywords or not keywords.strip():
        return "搜索关键词不能为空"

    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        results = []
        with DDGS(timeout=10) as ddgs:
            for r in ddgs.text(keywords.strip(), max_results=max_results):
                results.append(
                    f"- [{r.get('title', '无标题')}]({r.get('href', '')})\n"
                    f"  {r.get('body', '')[:200]}"
                )

        if not results:
            return f"未找到与 '{keywords}' 相关的网络结果"

        header = f"搜索 '{keywords}' — {len(results)} 条网络结果"
        return header + "\n" + "\n".join(results)

    except ImportError:
        return "联网搜索模块未安装 (pip install ddgs)"
    except Exception as e:
        return f"联网搜索失败: {e}"


# ═══════════════════════════════════════════════════════════════
# VLM 图片识别工具
# ═══════════════════════════════════════════════════════════════

_IMAGE_RECOGNITION_SYSTEM = (
    "你是一个图片识别助手。用中文口语化、自然地描述这张图片的内容。"
    "如果是截图：描述屏幕上显示的应用、网页、代码、文字等。"
    "如果是照片：描述场景、人物、物体、动作、氛围等。"
    "如果是表情包/meme：读懂其中的梗和情绪。"
    "如果是动漫/二次元图片：描述角色特征和画面内容。"
    "尽量简洁但完整，最终控制在一段话内。"
)


def tool_recognize_image(image_path: str, question: str = "") -> str:
    """调用 VLM 识别图片内容，返回中文描述"""
    import base64

    if not image_path or not image_path.strip():
        return "错误：缺少图片路径参数"

    # 解析路径
    memory_root = Path(__file__).parent.parent.parent / "agent_memory"
    img_path = Path(image_path)
    if not img_path.is_absolute():
        # 先尝试 agent_memory 下的相对路径
        candidate = memory_root / image_path
        if candidate.exists():
            img_path = candidate
        else:
            # 再尝试 backend 下的相对路径
            candidate2 = _WORKSPACE_ROOT / image_path
            if candidate2.exists():
                img_path = candidate2
            else:
                return f"图片文件不存在: {image_path}"

    if not img_path.exists():
        return f"图片文件不存在: {image_path}"

    suffix = img_path.suffix.lower()
    mime_map = {'.jpg': 'jpeg', '.jpeg': 'jpeg', '.png': 'png', '.gif': 'gif',
                '.webp': 'webp', '.bmp': 'bmp'}
    if suffix not in mime_map:
        return f"不支持的图片格式: {suffix}"

    try:
        with open(img_path, 'rb') as f:
            b64_data = base64.b64encode(f.read()).decode()
    except Exception as e:
        return f"读取图片失败: {e}"

    from core.llm.llm_api import LLMAPI
    import config as _config

    api_key = os.environ.get("DASHSCOPE_API_KEY", "") or getattr(_config, "DASHSCOPE_API_KEY", "")
    base_url = getattr(_config, "VISION_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    model = getattr(_config, "VISION_MODEL", "qwen-vl-plus")
    api = LLMAPI(api_key=api_key, base_url=base_url, model=model, timeout=30)

    prompt = question.strip() if question else "请描述这张图片的内容"

    messages = [
        {"role": "system", "content": _IMAGE_RECOGNITION_SYSTEM},
        {"role": "user", "content": [
            {"type": "image_url",
             "image_url": {"url": f"data:image/{mime_map[suffix]};base64,{b64_data}"}},
            {"type": "text", "text": prompt},
        ]},
    ]

    try:
        result = api.chat(messages, temperature=0.3)
    except Exception as e:
        return f"VLM 调用失败: {e}"

    if "error" in result:
        return f"VLM API 错误: {result['error']}"

    return result["choices"][0]["message"]["content"].strip()
