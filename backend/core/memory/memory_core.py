"""
统一记忆系统 (V5.0)
- 短期记忆：RAM buffer (最近 N 轮对话)
- 卡片记忆：CardStore 图结构存储 (JSONL + 邻接表 + 倒排索引)
- 日记：文件追加 (独立于卡片系统)
- 检索：BFS 图遍历 + 关键词+时间+重要性排序
- 压缩：三层算法压缩 (无 LLM)
"""
import asyncio
import json
import os
import re
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
from core.memory.card import (
    Card, generate_card_id, score_importance, card_to_dict, dict_to_card,
)
from core.memory.card_store import CardStore
from utils.text_utils import extract_keywords


class MemoryCore:
    """统一记忆系统 (V5.0 - 图结构卡片记忆)"""

    def __init__(self, llm_api: Optional[LLMAPI] = None):
        # 短期记忆缓冲区 (RAM驻留，仅用于上下文组装)
        self.short_term_history: List[Dict[str, str]] = []

        # 记忆根目录
        self._memory_root = Path(__file__).parent.parent.parent / "agent_memory"
        self._memory_root.mkdir(exist_ok=True)

        # 卡片存储引擎
        self._card_store = CardStore(memory_root=self._memory_root)
        loaded = self._card_store.load_all()

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

        # 冷加载
        self.personality = self._load_text("core/personality.md")
        self.mood_template = self._load_text("core/mood_blank.md")

        # 日记
        self._last_active_date = datetime.now().strftime("%Y-%m-%d")
        self._pending_recalls: list = []
        self.last_emotion_tag = None
        self._write_threads: list = []  # 兼容旧代码

        # 卡片创建状态
        self._pending_card_data: Optional[Tuple[str, str]] = None  # (user_text, ai_text)

        # 启动补归档
        self._catch_up_diary()
        # 定期压缩检查
        self._card_store.check_and_compress(
            tier1_days=getattr(config, 'CARD_TIER1_AGE_DAYS', 3),
            tier2_days=getattr(config, 'CARD_TIER2_AGE_DAYS', 30),
        )

        print(f"[MemoryCore] V5.0 图结构卡片记忆就绪 "
              f"(短期: {len(self.short_term_history)}条, 卡片: {loaded}张)")

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
    # 短期记忆 (RAM buffer)
    # ================================================================

    def add_short_term(self, role: str, content: str) -> None:
        """追加短期记忆到 RAM buffer"""
        if self.short_term_history:
            last = self.short_term_history[-1]
            if last.get("role") == role and last.get("content") == content:
                return
        self.short_term_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        # 容量上限
        max_cap = getattr(config, 'SHORT_TERM_CAPACITY_BASE', 20)
        if len(self.short_term_history) > max_cap + 10:
            self.short_term_history = self.short_term_history[-max_cap:]

        # 累计满一轮对话时，触发后台卡片创建
        if role == "assistant" and self._pending_card_data:
            user_text, ai_text = self._pending_card_data
            self._pending_card_data = None
            self._async_create_card(user_text, ai_text)

    def get_short_term_count(self) -> int:
        return len(self.short_term_history)

    def get_short_term_context(self, max_turns: Optional[int] = None) -> str:
        if not self.short_term_history:
            return ""
        buffer = self.short_term_history
        if max_turns is not None and max_turns > 0:
            buffer = buffer[-max_turns:]
        formatted = []
        for d in buffer:
            r = d["role"]
            if r == "user":
                role = "用户"
            elif r == "system":
                role = "记忆"
            else:
                role = "助手"
            formatted.append(f"{role}: {d['content']}")
        return "\n".join(formatted)

    def flush(self) -> None:
        """退出时强刷"""
        self._card_store.flush()
        print(f"[MemoryCore] flush: 卡片已落盘")

    # ================================================================
    # 卡片创建 (LLM 提取 + 算法打分/链接)
    # ================================================================

    def _async_create_card(self, user_text: str, ai_text: str):
        """后台线程：LLM 建卡 → CardStore"""
        t = threading.Thread(
            target=self._create_card_sync,
            args=(user_text, ai_text),
            daemon=True,
        )
        t.start()
        self._write_threads.append(t)
        # 清理已完成线程
        self._write_threads = [t for t in self._write_threads if t.is_alive()]

    def _create_card_sync(self, user_text: str, ai_text: str):
        """同步建卡 (在线程中运行)"""
        try:
            if not self._llm_api:
                return

            prompt = (
                '## 记忆卡片生成\n'
                '请从以下对话中提取关键信息，生成一张记忆卡片：\n\n'
                '【对话】\n'
                f'用户: {user_text[:300]}\n'
                f'yume: {ai_text[:300]}\n\n'
                '【输出格式】(严格 JSON，不要输出其他内容)\n'
                '{\n'
                '  "topic": "一句话主题 (≤30字)",\n'
                '  "tags": ["标签1", "标签2", ...],\n'
                '  "content": "卡片正文 (≤200字，概括核心内容)",\n'
                '  "emotion": "neutral|happy|sad|angry|fear|surprise"\n'
                '}'
            )
            result = self._llm_api.ask(prompt)
            if not result or result.isspace():
                return

            # 解析 LLM 输出的 JSON
            card_data = self._parse_card_json(result)
            if not card_data:
                return

            # 算法填充
            tags = card_data.get("tags", [])
            content = card_data.get("content", "")
            emotion = card_data.get("emotion", "neutral")
            topic = card_data.get("topic", "")

            emotion_eng = self._emotion_engine.get_emotion_dict()
            importance = score_importance(
                tags=tags,
                emotion_strength=emotion_eng.get("strength", 0),
                content_len=len(content),
            )

            card = Card(
                id=generate_card_id(),
                type="dialogue",
                timestamp=datetime.now().isoformat(),
                topic=topic,
                tags=tags,
                content=content,
                detail=f"用户: {user_text[:500]}\nyume: {ai_text[:500]}",
                importance=importance,
                emotion=emotion,
                tier=0,
            )

            card_id = self._card_store.append_card(card)
            print(f"[Memory] 卡片已创建: {card_id} topic={topic} importance={importance}")

        except Exception as e:
            print(f"[Memory] 卡片创建失败: {e}")

    def _parse_card_json(self, raw: str) -> Optional[dict]:
        """解析 LLM 返回的 JSON"""
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        # 尝试提取 {...} 块
        m = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        return None

    # ================================================================
    # 搜索 / 检索 (委托 CardStore)
    # ================================================================

    def search_memory(self, keyword: str = "", limit: int = 5) -> str:
        """在卡片中搜索 (替代旧 grep)"""
        if not keyword:
            return "请提供搜索关键词"

        tags = extract_keywords(keyword, max_kw=5)
        cards = self._card_store.retrieve(
            query_tags=tags,
            limit=limit,
            max_depth=getattr(config, 'CARD_BFS_MAX_DEPTH', 3),
            recency_halflife=getattr(config, 'CARD_RECENCY_HALFLIFE_DAYS', 7),
        )

        if not cards:
            return f"未找到关于 '{keyword}' 的记忆"

        lines = [f"搜索到 {len(cards)} 条关于 '{keyword}' 的记忆："]
        for c in cards:
            lines.append(f"- [{c.timestamp[:10]}] {c.topic}: {c.content[:80]}")
        return "\n".join(lines)

    def search_by_date(self, start_date: str = None, end_date: str = None) -> str:
        if not start_date and not end_date:
            return "请提供日期范围"
        s = start_date or "2000-01-01"
        e = end_date or datetime.now().strftime("%Y-%m-%d")
        cards = self._card_store.retrieve_by_date(s, e)
        if not cards:
            return f"日期范围 {start_date}~{end_date} 内无记录"
        lines = [f"--- {c.timestamp[:10]} ---\n{c.topic}: {c.content[:200]}" for c in cards]
        return "\n\n".join(lines)

    def search_diary(self, keyword: str, limit: int = 3) -> str:
        """在卡片中搜索 (兼容旧 search_diary 接口)"""
        tags = extract_keywords(keyword, max_kw=3)
        cards = self._card_store.retrieve(query_tags=tags, limit=limit)
        if not cards:
            return ""
        return "\n".join(f"[{c.timestamp[:10]}] {c.content[:120]}" for c in cards)

    # ================================================================
    # 日记
    # ================================================================

    def append_diary_draft(self, text: str) -> None:
        draft_path = self._memory_root / "diary/drafts/daily_draft.txt"
        try:
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            today = datetime.now().strftime("%Y-%m-%d")
            with open(draft_path, 'a', encoding='utf-8') as f:
                if self._last_active_date != today:
                    f.write(f"\n--- {today} ---\n")
                    self._last_active_date = today
                timestamp = datetime.now().strftime("%H:%M")
                f.write(f"[{timestamp}] {text}\n")
        except Exception as e:
            print(f"[WARN] 日记草稿写入失败: {e}")

    def _catch_up_diary(self) -> None:
        draft_path = self._memory_root / "diary/drafts/daily_draft.txt"
        if not draft_path.exists() or draft_path.stat().st_size == 0:
            return
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            draft_content = draft_path.read_text(encoding="utf-8")
            sections: Dict[str, list] = {}
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
            if not sections:
                mtime = draft_path.stat().st_mtime
                guessed = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
                sections[guessed] = draft_content.split("\n")

            diary_dir = self._memory_root / "diary" / "daily"
            diary_dir.mkdir(parents=True, exist_ok=True)
            archived_count = 0
            remaining_lines: list = []

            for dt, lines in sections.items():
                if dt == today:
                    remaining_lines = lines
                    continue
                body = "\n".join(lines).strip()
                if not body or body == draft_content.strip():
                    continue
                diary_path = diary_dir / f"{dt}.md"
                header = f"# {dt} 对话日记\n\n"
                if diary_path.exists():
                    existing = diary_path.read_text(encoding="utf-8")
                    with open(diary_path, 'w', encoding='utf-8') as f:
                        f.write(existing + "\n\n" + body)
                else:
                    with open(diary_path, 'w', encoding='utf-8') as f:
                        f.write(header + body)
                archived_count += 1
                print(f"[日记] 启动补归档: {dt} ({len(body)} 字符)")

            if archived_count > 0:
                today_header = f"--- {today} ---\n" if remaining_lines else ""
                new_draft = today_header + "\n".join(remaining_lines) if remaining_lines else ""
                draft_path.write_text(new_draft, encoding="utf-8")

        except Exception as e:
            print(f"[WARN] 启动补归档异常: {e}")

    def check_cross_day_diary(self) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        if self._last_active_date == today:
            return
        self._last_active_date = today
        draft_path = self._memory_root / "diary/drafts/daily_draft.txt"
        if not draft_path.exists() or draft_path.stat().st_size == 0:
            return
        try:
            draft_content = draft_path.read_text(encoding="utf-8")
            sections: Dict[str, list] = {}
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

            diary_dir = self._memory_root / "diary" / "daily"
            diary_dir.mkdir(parents=True, exist_ok=True)
            remaining: list = []

            for dt, lines in sections.items():
                if dt == today:
                    remaining = lines
                    continue
                body = "\n".join(lines).strip()
                if not body:
                    continue
                diary_path = diary_dir / f"{dt}.md"
                if diary_path.exists():
                    existing = diary_path.read_text(encoding="utf-8")
                    with open(diary_path, 'w', encoding='utf-8') as f:
                        f.write(existing + "\n\n" + body)
                else:
                    with open(diary_path, 'w', encoding='utf-8') as f:
                        f.write(f"# {dt} 对话日记\n\n{body}")
                print(f"[日记] {dt} 日记已归档 ({len(body)} 字符)")

            today_header = f"--- {today} ---\n" if remaining else ""
            draft_path.write_text(today_header + "\n".join(remaining) if remaining else "", encoding="utf-8")

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
        """构建深层回忆 Prompt 注入 (BFS 检索替代旧 grep)"""
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

    def _build_time_context(self) -> str:
        now = datetime.now()
        hour = now.hour
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday = weekday_names[now.weekday()]

        if 0 <= hour < 5:
            period = "凌晨"
        elif 5 <= hour < 9:
            period = "早上"
        elif 9 <= hour < 12:
            period = "上午"
        elif 12 <= hour < 14:
            period = "中午"
        elif 14 <= hour < 17:
            period = "下午"
        elif 17 <= hour < 19:
            period = "傍晚"
        elif 19 <= hour < 23:
            period = "晚上"
        else:
            period = "深夜"

        return (
            f"【当前时间】\n"
            f"现在是 {now.strftime('%Y年%m月%d日')} {weekday} {period} "
            f"({now.strftime('%H:%M')})"
        )

    def get_time_context(self) -> str:
        return self._build_time_context()

    def build_context(
        self,
        user_input: str,
        max_history_turns: int = 10,
    ) -> str:
        """组装完整上下文供 LLM 使用"""
        parts: List[str] = []

        if self.personality:
            parts.append(f"【人设】\n{self.personality}")

        history = self.short_term_history
        if history:
            recent = history[-(max_history_turns * 2):]
            lines = []
            for d in recent:
                r = d.get("role", "")
                if r == "user":
                    role = "用户"
                elif r == "system":
                    role = "记忆"
                else:
                    role = "yume"
                content = d.get("content", "")
                if content:
                    lines.append(f"{role}: {content}")
            if lines:
                parts.append(f"【近期对话】\n" + "\n".join(lines))

        # 卡片检索
        tags = extract_keywords(user_input, max_kw=3)
        cards = self._card_store.retrieve(query_tags=tags, limit=3)
        if cards:
            card_lines = [f"- {c.topic}: {c.content[:100]}" for c in cards]
            parts.append(f"【相关记忆】\n" + "\n".join(card_lines))

        parts.append(self._build_time_context())
        parts.append(f"【用户输入】\n{user_input}")

        return "\n\n".join(parts)

    # ================================================================
    # 记忆意图检测 + 结构化上下文组装
    # ================================================================

    def detect_memory_intent(self, user_input: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "intent": "chat",
            "date_query": None,
            "keyword_query": None,
            "write_request": False,
        }

        write_words = ["记住", "记一下", "帮我记", "记下来", "写下来", "记一记"]
        if any(w in user_input for w in write_words):
            result["write_request"] = True

        date_patterns = [
            (r'(\d{1,2})号', lambda m: datetime.now().replace(day=int(m.group(1))).strftime("%Y-%m-%d")),
            (r'(\d{1,2})月(\d{1,2})[号日]?', lambda m: f"{datetime.now().year:04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"),
            (r'昨天', lambda m: (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")),
            (r'前天', lambda m: (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")),
        ]

        memory_query_words = [
            "记忆", "记得", "那天", "发生了什么", "讲讲", "说说",
            "查查", "查一下", "翻翻", "翻一下", "查到", "找到",
        ]

        if any(w in user_input for w in memory_query_words):
            for pattern, resolver in date_patterns:
                m = re.search(pattern, user_input)
                if m:
                    result["intent"] = "date_query"
                    result["date_query"] = resolver(m)
                    print(f"[MemoryIntent] 检测到日期查询: {result['date_query']} (来自 '{user_input[:30]}...')")
                    break
            if result["intent"] != "date_query":
                result["intent"] = "keyword_query"
                words = re.findall(r"[一-鿿\w]{2,}", user_input)
                keyword = words[0] if words else user_input[:20]
                result["keyword_query"] = keyword

        return result

    def build_structured_sections(self, user_input: str, deep_recall: str = "") -> Dict[str, Any]:
        """结构化分区: 记忆区用 CardStore BFS 检索"""
        intent = self.detect_memory_intent(user_input)
        tags = extract_keywords(user_input, max_kw=5)

        # ── 日记/长期记忆 ──
        recent_cards = self._card_store.get_recent_cards(3)
        if recent_cards:
            diary_memory = "\n".join(
                f"[{c.timestamp[:10]}] {c.topic}: {c.content[:100]}" for c in recent_cards
            )
        else:
            diary_memory = "（暂无记忆卡片）"

        # ── 精准查询 ──
        precise_query = ""
        if intent["intent"] == "date_query" and intent["date_query"]:
            date_str = intent["date_query"]
            result = self.search_by_date(start_date=date_str, end_date=date_str)
            if result and "无" not in result:
                precise_query = result[:500]
            else:
                precise_query = f"未找到 {date_str} 的记录"

        elif intent["intent"] == "keyword_query" and intent["keyword_query"]:
            kw = intent["keyword_query"]
            result = self.search_memory(keyword=kw, limit=3)
            if result and "未找到" not in result:
                precise_query = result[:400]

        if not precise_query:
            precise_query = "（本次未触发精准查询）"

        # ── pre_search: BFS 检索 ──
        bfs_cards = self._card_store.retrieve(
            query_tags=tags,
            limit=5,
            max_depth=getattr(config, 'CARD_BFS_MAX_DEPTH', 3),
            recency_halflife=getattr(config, 'CARD_RECENCY_HALFLIFE_DAYS', 7),
        )
        if bfs_cards:
            pre_search = "\n---\n".join(
                f"[{c.timestamp[:10]}] {c.topic}: {c.content[:100]}" for c in bfs_cards
            )[:400]
        else:
            pre_search = "（无预检索结果）"

        # ── 深层记忆/潜意识 ──
        if not deep_recall:
            deep_recall_inject, _ = self.build_recall_injection()
            if deep_recall_inject:
                deep_recall = deep_recall_inject.replace("【潜意识浮现】", "").strip()
        if not deep_recall:
            deep_recall = "（无深层记忆浮现）"

        return {
            "diary_memory": diary_memory,
            "precise_query": precise_query,
            "pre_search": pre_search,
            "deep_recall": deep_recall,
            "time_context": self._build_time_context(),
            "write_request": intent["write_request"],
        }

    # ================================================================
    # 深层回忆
    # ================================================================

    def do_deep_memory_recall(self, user_text: str) -> str:
        """深层回忆检索 (BFS)"""
        try:
            tags = extract_keywords(user_text, max_kw=3)
            cards = self._card_store.retrieve(query_tags=tags, limit=2)
            if cards:
                result = "\n".join(f"[{c.timestamp[:10]}] {c.content[:120]}" for c in cards)
                print(f"[DeepMemory] BFS 检索到 {len(cards)} 条相关卡片")
                return "【潜意识浮现的记忆】：\n" + result
        except Exception as e:
            print(f"[DeepMemory] 检索失败: {e}")
        return ""

    # ================================================================
    # 异步记忆写入
    # ================================================================

    def start_async_memory_write(self, user_text: str, ai_reply_text: str):
        """异步写入日记草稿 + 短期记忆 + 触发卡片创建"""
        def task():
            try:
                self._sync_memory_write(user_text, ai_reply_text)
            except Exception as e:
                print(f"[Memory] 异步记忆写入失败: {e}")
        t = threading.Thread(target=task, daemon=False)
        t.start()
        self._write_threads.append(t)

    def _sync_memory_write(self, user_text: str, ai_reply_text: str):
        """同步写入：日记草稿 + 短期记忆 + 排队卡片创建"""
        try:
            self.append_diary_draft(f"用户：{user_text[:200]}")
            self.append_diary_draft(f"我：{ai_reply_text[:200]}")

            # 设置待建卡数据，add_short_term("assistant") 触发建卡
            self._pending_card_data = (user_text, ai_reply_text)

            real_emotion = self._emotion_engine.get_emotion_dict()
            tag_result = {
                "emotion_type": real_emotion.get("type", 0),
                "emotion_strength": real_emotion.get("strength", 1),
                "scene_type": real_emotion.get("scene", "A")
            }
            self.last_emotion_tag = tag_result

            self.add_short_term("user", user_text)
            self.add_short_term("assistant", ai_reply_text)

            print(f"[Memory] 记忆写入完成 (情绪: {tag_result['emotion_type']})")

            # 情绪强烈时触发深层回忆
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
    # 公开方法 (兼容 old API)
    # ================================================================

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

    # ================================================================
    # 静态方法 (工具系统 + 兼容代码使用)
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
        """随机获取长期记忆 (从卡片中采样)"""
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

    @staticmethod
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

    @staticmethod
    def tool_read_file(filenames) -> str:
        return MemoryCore.load_files(filenames if isinstance(filenames, list) else [filenames])

    @staticmethod
    def tool_write_file(filename: str, content: str) -> str:
        return MemoryCore.create_file(filename=filename, content=content, overwrite=True)

    @staticmethod
    def tool_search_memory(keyword: str, target_date=None, llm=None) -> str:
        """搜索记忆 (供工具系统使用)"""
        memory_root = Path(__file__).parent.parent.parent / "agent_memory"
        if not memory_root.exists():
            return "记忆目录不存在"
        # 优先用卡片搜索
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
        # 回退到文件搜索
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

    # ── 以下方法保持兼容 (adapters.py 调用) ──

    @staticmethod
    def tool_summarize_and_archive(max_lines=50, llm=None) -> str:
        return "记忆压缩已由 CardStore 三层算法自动管理"

    @staticmethod
    def tool_write_diary(target_date=None, llm=None) -> str:
        return "日记已由日记流水线自动生成"
