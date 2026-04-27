"""
统一记忆系统 (V4.0)
- 短期记忆：RAM buffer + JSON 持久化
- 长期记忆：Markdown 文件存储（无 FAISS/向量）
- 日记：简单文件追加
- 搜索：grep 全文搜索
- 上下文自动组装
"""

import asyncio
import json
import os
import sys
import threading
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from core.emotion.emotion_engine import EmotionEngine
import config
from core.llm.llm_api import LLMAPI


class MemoryCore:
    """统一记忆系统"""

    def __init__(self, llm_api: Optional[LLMAPI] = None):
        # 短期记忆缓冲区（RAM驻留）
        self._short_term_buffer: List[Dict[str, str]] = []

        # 记忆根目录
        self._memory_root = Path(__file__).parent.parent.parent / "agent_memory"
        self._memory_root.mkdir(exist_ok=True)

        # 情绪引擎
        self._emotion_engine = EmotionEngine()

        # LLM API
        self._llm_api = llm_api
        if self._llm_api is None and config.DEEPSEEK_API_KEY:
            self._llm_api = LLMAPI(
                api_key=config.DEEPSEEK_API_KEY,
                base_url=config.DEEPSEEK_BASE_URL,
                model=config.DEEPSEEK_MODEL
            )

        # 短期记忆容量
        self.max_short_term_turns = getattr(config, 'SHORT_TERM_CAPACITY_BASE', 20)

        # 冷加载
        self.personality = self._load_text("personality.md")
        self.mood_template = self._load_text("mood_blank.md")
        self.short_term_history: List[Dict[str, str]] = []

        # 日记/深度回忆
        self._last_active_date = datetime.now().strftime("%Y-%m-%d")
        self._pending_recalls: list = []
        self.last_emotion_tag = None

        self._load_short_term_from_disk()
        print(f"[MemoryCore] V4.0 统一记忆系统就绪 (短期记忆: {len(self.short_term_history)} 条)")

    # ================================================================
    # 文件 I/O
    # ================================================================

    def _load_text(self, filename: str) -> str:
        path = self._memory_root / filename
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except Exception as e:
                print(f"[WARN] 加载 {filename} 失败: {e}")
        return ""

    def _memory_path(self, filename: str) -> Path:
        return self._memory_root / filename

    def load_personality(self) -> str:
        return self.personality

    def load_mood_templates(self) -> str:
        return self.mood_template

    def load_tools_index(self) -> str:
        return self._load_text("tools/tools_index.md")

    def get_random_long_term_memory_v3(self, count: int = 1) -> str:
        return self.get_random_long_term_memory(count)

    # ================================================================
    # 短期记忆
    # ================================================================

    def add_short_term(self, role: str, content: str) -> None:
        if self._short_term_buffer:
            last = self._short_term_buffer[-1]
            if last.get("role") == role and last.get("content") == content:
                return
        dialogue = {"role": role, "content": content, "timestamp": datetime.now().isoformat()}
        self._short_term_buffer.append(dialogue)
        if len(self._short_term_buffer) > self.max_short_term_turns:
            self._short_term_buffer.pop(0)
        asyncio.create_task(self._persist_short_term())

    def get_short_term_context(self, max_turns: Optional[int] = None) -> str:
        if not self._short_term_buffer:
            return ""
        buffer = self._short_term_buffer
        if max_turns is not None and max_turns > 0:
            buffer = buffer[-max_turns:]
        formatted = []
        for d in buffer:
            role = "用户" if d["role"] == "user" else "助手"
            formatted.append(f"{role}: {d['content']}")
        return "\n".join(formatted)

    async def _persist_short_term(self) -> None:
        try:
            data = {
                "dialogues": self._short_term_buffer,
                "current_emotion": self._emotion_engine.get_emotion_dict(),
                "updated_at": datetime.now().isoformat()
            }
            await asyncio.to_thread(self._write_json, self._memory_root / "short_term.json", data)
        except Exception as e:
            print(f"[ERROR] 短期记忆持久化失败: {e}")

    def _load_short_term_from_disk(self) -> None:
        path = self._memory_root / "short_term.json"
        if not path.exists():
            return
        try:
            data = self._read_json(path)
            if "dialogues" in data and isinstance(data["dialogues"], list):
                dialogues = data["dialogues"]
                if len(dialogues) > self.max_short_term_turns:
                    dialogues = dialogues[-self.max_short_term_turns:]
                self.short_term_history = [
                    {"role": d.get("role", "user"), "content": d.get("content", "")}
                    for d in dialogues
                ]
            if "current_emotion" in data:
                e = data["current_emotion"]
                if "type" in e and "strength" in e:
                    self._emotion_engine.reset(e["type"], e["strength"])
        except Exception as e:
            print(f"[WARN] 加载短期记忆失败: {e}")

    # ================================================================
    # 搜索（grep 全文搜索）
    # ================================================================

    def search_memory(self, keyword: str = "", limit: int = 5) -> str:
        """在 agent_memory/ 下全文搜索关键词"""
        if not keyword:
            return "请提供搜索关键词"
        if not self._memory_root.exists():
            return "记忆目录不存在"
        results = []
        keyword_lower = keyword.lower()
        for fpath in self._memory_root.rglob("*"):
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
                rel_path = fpath.relative_to(self._memory_root)
                results.append(f"[{rel_path}] ...{snippet}...")
            if len(results) >= limit:
                break
        if not results:
            return f"未找到关于 '{keyword}' 的记忆"
        return f"搜索到 {len(results)} 条关于 '{keyword}' 的记忆：\n" + "\n".join(f"- {r}" for r in results)

    def search_by_date(self, start_date: str = None, end_date: str = None) -> str:
        diary_dir = self._memory_root / "diary" / "daily"
        if not diary_dir.exists():
            return "日记目录不存在"
        results = []
        for fpath in sorted(diary_dir.glob("*.md")):
            fname = fpath.stem
            if start_date and fname < start_date:
                continue
            if end_date and fname > end_date:
                continue
            try:
                content = fpath.read_text(encoding="utf-8")[:300]
                results.append(f"--- {fname} ---\n{content}")
            except Exception:
                pass
        if not results:
            return f"日期范围 {start_date}~{end_date} 内无日记"
        return "\n\n".join(results)

    def search_diary(self, keyword: str, limit: int = 3) -> str:
        """在日记中搜索关键词（用于深层回忆替代 FAISS）"""
        diary_dir = self._memory_root / "diary" / "daily"
        if not diary_dir.exists():
            return ""
        results = []
        for fpath in sorted(diary_dir.glob("*.md"), reverse=True):
            try:
                content = fpath.read_text(encoding="utf-8")
            except Exception:
                continue
            idx = content.lower().find(keyword.lower())
            if idx >= 0:
                start = max(0, idx - 40)
                end = min(len(content), idx + len(keyword) + 80)
                snippet = content[start:end].replace("\n", " ").strip()
                results.append(f"[{fpath.stem}] ...{snippet}...")
            if len(results) >= limit:
                break
        return "\n".join(results) if results else ""

    # ================================================================
    # 日记
    # ================================================================

    def append_diary_draft(self, text: str) -> None:
        """追加对话草稿到日记素材文件"""
        draft_path = self._memory_root / "daily_draft.txt"
        try:
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%H:%M")
            with open(draft_path, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {text}\n")
        except Exception as e:
            print(f"[WARN] 日记草稿写入失败: {e}")

    def check_cross_day_diary(self) -> None:
        """跨天懒检查：如果日期变了，把昨天的草稿归档为日记"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._last_active_date == today:
            return
        self._last_active_date = today
        draft_path = self._memory_root / "daily_draft.txt"
        if not draft_path.exists() or draft_path.stat().st_size == 0:
            return
        try:
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            draft_content = draft_path.read_text(encoding="utf-8")
            diary_dir = self._memory_root / "diary" / "daily"
            diary_dir.mkdir(parents=True, exist_ok=True)
            diary_path = diary_dir / f"{yesterday}.md"
            with open(diary_path, 'w', encoding='utf-8') as f:
                f.write(f"# {yesterday} 对话日记\n\n{draft_content}")
            draft_path.write_text("", encoding="utf-8")
            print(f"[日记] {yesterday} 日记已归档 ({len(draft_content)} 字符)")
        except Exception as e:
            print(f"[WARN] 日记归档失败: {e}")

    # ================================================================
    # 活动类型检测
    # ================================================================

    @staticmethod
    def detect_activity_type(text: str) -> str:
        text_lower = text.lower()
        repetitive_keywords = ["重复", "再做一遍", "继续做", "继续刚才", "继续之前", "继续", "接着", "连续", "一直"]
        if any(kw in text_lower for kw in repetitive_keywords):
            return "repetitive_task"
        creative_keywords = ["创作", "写诗", "写文章", "写故事", "画", "设计", "创意", "想象", "构思"]
        if any(kw in text_lower for kw in creative_keywords):
            return "creative_task"
        forced_keywords = ["必须", "一定", "非得", "非要", "强制", "强迫", "逼", "命令"]
        if any(kw in text_lower for kw in forced_keywords):
            return "forced_task"
        return "user_chat"

    # ================================================================
    # 上下文组装
    # ================================================================

    def build_recall_injection(self) -> Tuple[str, int]:
        """构建深层回忆 Prompt 注入文本"""
        if not self._pending_recalls:
            return "", 0
        recall_count = len(self._pending_recalls)
        injection = "\n\n【潜意识浮现】\n"
        for i, fragment in enumerate(self._pending_recalls, 1):
            injection += f"{i}. {fragment}\n"
        injection += "（如果觉得这些感受与当前对话相关，可以自然地提出来）\n"
        self._pending_recalls = []
        if injection:
            print(f"[深度回忆] 捕获 {recall_count} 条潜意识碎片，留待下轮注入")
        return injection, recall_count

    def build_context(
        self,
        user_input: str,
        max_history_turns: int = 10,
    ) -> str:
        """组装完整上下文供 LLM 使用"""
        import re

        parts: List[str] = []

        if self.personality:
            parts.append(f"【人设】\n{self.personality}")

        # 短期历史
        history = self.short_term_history
        if history:
            recent = history[-(max_history_turns * 2):]
            lines = []
            for d in recent:
                role = "用户" if d.get("role") == "user" else "yume"
                content = d.get("content", "")
                if content:
                    lines.append(f"{role}: {content}")
            if lines:
                parts.append(f"【近期对话】\n" + "\n".join(lines))

        # 关键词搜索长期记忆
        stop_words = {
            "的", "了", "是", "在", "我", "你", "他", "她", "它", "们",
            "和", "与", "或", "也", "就", "都", "而", "及", "把", "被",
            "让", "从", "到", "对", "向", "往", "用", "以", "为",
        }
        words = re.findall(r"[一-鿿\w]+", user_input)
        keywords = []
        seen = set()
        for w in words:
            if w not in stop_words and len(w) >= 2 and w not in seen:
                seen.add(w)
                keywords.append(w)
                if len(keywords) >= 3:
                    break

        if keywords:
            long_term_snippets = self.search_diary(keywords[0], limit=3)
            if long_term_snippets:
                parts.append(f"【相关长期记忆】\n{long_term_snippets}")

        parts.append(f"【当前日期】\n{datetime.now().strftime('%Y年%m月%d日')}")
        parts.append(f"【用户输入】\n{user_input}")

        return "\n\n".join(parts)

    # ================================================================
    # 深层回忆（简化：grep 替代 FAISS）
    # ================================================================

    def do_deep_memory_recall(self, user_text: str) -> str:
        """深层回忆检索：在日记中搜索相关记忆"""
        try:
            # 提取关键词
            import re
            words = re.findall(r"[一-鿿\w]{2,}", user_text)
            if not words:
                return ""

            # 只用第一个有意义的词搜索
            result = self.search_diary(words[0], limit=2)
            if result:
                print(f"[DeepMemory] grep 检索到相关日记片段")
                return "【潜意识浮现的记忆】：\n" + result
        except Exception as e:
            print(f"[DeepMemory] 检索失败: {e}")
        return ""

    # ================================================================
    # 异步记忆写入
    # ================================================================

    def start_async_memory_write(self, user_text: str, ai_reply_text: str):
        def task():
            try:
                asyncio.run(self._async_memory_write(user_text, ai_reply_text))
            except Exception as e:
                print(f"[Memory] 异步记忆写入失败: {e}")
        threading.Thread(target=task, daemon=True).start()

    async def _async_memory_write(self, user_text: str, ai_reply_text: str):
        try:
            # 日记草稿
            self.append_diary_draft(f"用户：{user_text[:200]}")
            self.append_diary_draft(f"我：{ai_reply_text[:200]}")

            # 情绪标签
            real_emotion = self._emotion_engine.get_emotion_dict()
            tag_result = {
                "emotion_type": real_emotion.get("type", 0),
                "emotion_strength": real_emotion.get("strength", 1),
                "scene_type": real_emotion.get("scene", "A")
            }
            self.last_emotion_tag = tag_result

            # 短期记忆
            self.add_short_term("user", user_text)
            self.add_short_term("assistant", ai_reply_text)

            # 同步 short_term_history
            self.short_term_history.append({"role": "user", "content": user_text})
            self.short_term_history.append({"role": "assistant", "content": ai_reply_text})
            max_history = getattr(config, 'SHORT_TERM_HISTORY_TOKENS', 1500)
            while sum(len(m["content"]) for m in self.short_term_history) > max_history * 2 and len(self.short_term_history) > 4:
                self.short_term_history.pop(0)
            self.set_short_term_memory_cache(self.short_term_history)

            print(f"[Memory] 记忆写入完成 (情绪: {tag_result['emotion_type']})")

            # 情绪强烈时触发深层回忆（grep 搜索日记）
            if tag_result["emotion_strength"] >= 5:
                diary_snippets = self.search_diary(user_text[:50], limit=2)
                if diary_snippets:
                    self._pending_recalls = [diary_snippets]
                    print(f"[深度回忆] 捕获日记片段，留待下轮注入")

        except Exception as e:
            print(f"[Memory] 记忆写入失败: {e}")

    # ================================================================
    # 情绪
    # ================================================================

    def get_current_emotion(self) -> Dict[str, Any]:
        return self._emotion_engine.get_emotion_dict()

    def update_and_get_emotion(self, new_type: int, new_strength: float) -> Dict[str, Any]:
        self._emotion_engine.update_emotion(new_type, new_strength)
        return self._emotion_engine.get_emotion_dict()

    # ================================================================
    # JSON 原子写入
    # ================================================================

    def _write_json(self, file_path: Path, data: Any) -> None:
        import tempfile
        import shutil
        backup_path = None
        if file_path.exists():
            backup_path = file_path.with_suffix('.json.bak')
            try:
                shutil.copy2(file_path, backup_path)
            except Exception:
                pass
        temp_path = None
        try:
            temp_fd, temp_path = tempfile.mkstemp(dir=file_path.parent, suffix='.tmp')
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            shutil.move(temp_path, file_path)
            if backup_path and backup_path.exists():
                try:
                    os.remove(backup_path)
                except Exception:
                    pass
        except Exception as e:
            print(f"[ERROR] 原子写入失败 {file_path}: {e}")
            if backup_path and backup_path.exists() and not file_path.exists():
                try:
                    shutil.copy2(backup_path, file_path)
                except Exception:
                    pass
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            raise

    def _read_json(self, file_path: Path) -> Any:
        import shutil
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] 读取JSON失败 {file_path}: {e}")
            backup_path = file_path.with_suffix('.json.bak')
            if backup_path.exists():
                try:
                    shutil.copy2(backup_path, file_path)
                    with open(file_path, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception:
                    pass
            return {}

    # ================================================================
    # 兼容性静态方法（供工具系统和旧代码使用）
    # ================================================================

    @staticmethod
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
                    with open(path, 'r', encoding='utf-8') as f:
                        result.append(f.read())
                except Exception as e:
                    print(f"[WARN] 加载 {name} 失败: {e}")
                    result.append("")
            else:
                result.append("")
        return result[0] if result else ""

    @staticmethod
    def append_to_file(filename: str, content: str) -> None:
        memory_root = Path(__file__).parent.parent.parent / "agent_memory"
        fpath = memory_root / filename
        try:
            fpath.parent.mkdir(parents=True, exist_ok=True)
            with open(fpath, 'a', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            print(f"[WARN] 追加写入 {filename} 失败: {e}")

    @staticmethod
    def get_random_long_term_memory(n: int = 3) -> str:
        try:
            memory_root = Path(__file__).parent.parent.parent / "agent_memory"
            diary_dir = memory_root / "diary" / "daily"
            if diary_dir.exists():
                files = list(diary_dir.glob("*.md"))
                files.sort(key=lambda x: x.stat().st_mtime if x.is_file() else 0)
                if files:
                    recent_files = files[-3:] if len(files) >= 3 else files
                    target = random.choice(recent_files)
                    with open(target, 'r', encoding='utf-8') as f:
                        return f.read()[:200]
        except Exception:
            pass
        return ""

    @staticmethod
    def set_short_term_memory_cache(history: list) -> None:
        if not history:
            return
        memory_root = Path(__file__).parent.parent.parent / "agent_memory"
        fpath = memory_root / "short_term.json"
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

    @staticmethod
    def write_file(filename: str, content: str) -> None:
        memory_root = Path(__file__).parent.parent.parent / "agent_memory"
        fpath = memory_root / filename
        try:
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")
        except Exception as e:
            print(f"[WARN] 写入文件 {filename} 失败: {e}")

    @staticmethod
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

    @staticmethod
    def load_tool_docs() -> str:
        try:
            memory_root = Path(__file__).parent.parent.parent / "agent_memory"
            path = memory_root / "tools" / "tool_docs.md"
            if path.exists():
                return path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[WARN] 加载工具文档失败: {e}")
        return "工具文档加载失败"

    # 以下为已废弃方法（保持兼容性，直接返回跳过信息）
    @staticmethod
    def update_long_term_memory(max_lines=50, llm=None) -> str:
        return "跳过：长期记忆已由日记系统自动管理"

    @staticmethod
    def write_daily_diary(target_date=None, llm=None) -> str:
        return "跳过：日记已由日记流水线自动生成"

    @staticmethod
    def auto_write_diary(llm=None) -> str:
        return "跳过：日记已由日记流水线自动生成"

    @staticmethod
    def write_weekly_summary(year=None, week=None, llm=None) -> str:
        return "跳过：此功能已废弃"

    @staticmethod
    def write_monthly_summary(year=None, month=None, llm=None) -> str:
        return "跳过：此功能已废弃"

    @staticmethod
    def write_yearly_summary(year=None, llm=None) -> str:
        return "跳过：此功能已废弃"

    @staticmethod
    def precise_search_memory(keyword="", filename="memories.md", context_lines=2) -> str:
        memory_root = Path(__file__).parent.parent.parent / "agent_memory"
        fpath = memory_root / filename
        if not fpath.exists():
            return f"文件 {filename} 不存在"
        # Delegate to grep search
        keyword_lower = keyword.lower()
        try:
            content = fpath.read_text(encoding="utf-8")
            idx = content.lower().find(keyword_lower)
            if idx >= 0:
                start = max(0, idx - 60)
                end = min(len(content), idx + len(keyword) + 100)
                snippet = content[start:end].replace("\n", " ")
                return f"在 {filename} 中找到：...{snippet}..."
            return f"在 {filename} 中未找到 '{keyword}'"
        except Exception as e:
            return f"搜索失败: {e}"

    @staticmethod
    def delete_memory_entry(keyword="", filename="memories.md", backup=True) -> str:
        return "跳过：删除功能已禁用（避免误删）"

    @staticmethod
    def locate_memory_entry(keyword="", filename="memories.md") -> str:
        return MemoryCore.precise_search_memory(keyword=keyword, filename=filename)

    @staticmethod
    def clear_file(filename: str, backup: bool = True) -> str:
        memory_root = Path(__file__).parent.parent.parent / "agent_memory"
        fpath = memory_root / filename
        if not fpath.exists():
            return f"文件 {filename} 不存在"
        try:
            if backup:
                import shutil
                shutil.copy2(fpath, fpath.with_suffix(fpath.suffix + '.bak'))
            fpath.write_text("", encoding="utf-8")
            return f"文件 {filename} 已清空"
        except Exception as e:
            return f"清空失败: {e}"

    @staticmethod
    def delete_memory_file(filename: str) -> str:
        memory_root = Path(__file__).parent.parent.parent / "agent_memory"
        fpath = memory_root / filename
        if not fpath.exists():
            return f"文件 {filename} 不存在"
        try:
            fpath.unlink()
            return f"文件 {filename} 已删除"
        except Exception as e:
            return f"删除失败: {e}"

    @staticmethod
    def tool_write_file(filename: str, content: str) -> str:
        return MemoryCore.create_file(filename=filename, content=content, overwrite=True)

    @staticmethod
    def tool_read_file(filenames) -> str:
        return MemoryCore.load_files(filenames if isinstance(filenames, list) else [filenames])

    @staticmethod
    def tool_search_memory(keyword: str, target_date=None, llm=None) -> str:
        memory_root = Path(__file__).parent.parent.parent / "agent_memory"
        if not memory_root.exists():
            return "记忆目录不存在"
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

    @staticmethod
    def tool_summarize_and_archive(max_lines=50, llm=None) -> str:
        return "跳过：此功能已废弃"

    @staticmethod
    def tool_write_diary(target_date=None, llm=None) -> str:
        return "跳过：日记已由日记流水线自动生成"

    @staticmethod
    def search_specific_memory(keyword="", target_date=None) -> str:
        return MemoryCore.tool_search_memory(keyword=keyword)

    def update_memory(self, filename: str = "", content: str = "", llm=None) -> str:
        if not filename or not content:
            return "错误：缺少文件名或内容"
        fpath = self._memory_root / filename
        try:
            fpath.parent.mkdir(parents=True, exist_ok=True)
            with open(fpath, 'a', encoding='utf-8') as f:
                f.write("\n" + content)
            return f"记忆已追加到 {filename}"
        except Exception as e:
            return f"记忆更新失败: {e}"
