"""
记忆门面 (MemoryFacade)
组装所有记忆子组件，提供与旧 MemoryCore 完全兼容的公开 API

实现 MemoryCapability 协议，支持 DI 容器管理生命周期。
"""
import json
import os
import tempfile
import shutil
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

import config
from core.emotion.emotion_engine import EmotionEngine
from core.llm.llm_factory import LLMFactory
from core.memory.card import Card
from core.memory.card_store import CardStore
from core.memory.short_term import ShortTermMemory
from core.memory.card_manager import CardManager
from core.memory.diary_writer import DiaryWriter
from core.memory.diary_processor import DiaryProcessor
from core.memory.context_builder import ContextBuilder
from core.memory.intent_judge import IntentJudge
from core.memory import tools
from core.memory.context_compressor import ContextCompressor


class MemoryFacade:
    """统一记忆系统门面 (V5.1 - 拆分为6文件)"""

    name = "memory"
    version = "5.1"

    def __init__(self, llm_api=None):
        # ── 路径 ──
        self._memory_root = Path(__file__).parent.parent.parent / "agent_memory"
        self._memory_root.mkdir(exist_ok=True)

        # ── 核心引擎 ──
        self._card_store = CardStore(memory_root=self._memory_root)
        loaded = self._card_store.load_all()
        self._emotion_engine = EmotionEngine()

        # ── LLM ──
        self._llm_api = llm_api
        if self._llm_api is None and config.DEEPSEEK_API_KEY:
            self._llm_api = LLMFactory.get_default()

        # 注入 LLM 到 CardStore（供 _generate_summary 使用）
        self._card_store._llm_api = self._llm_api

        # ── 前置 LLM 意图判断器 ──
        self._intent_judge = IntentJudge(self._llm_api) if self._llm_api else None

        # ── 子组件 (5个) ──
        self._short_term = ShortTermMemory(card_store=self._card_store)
        self._compressor = ContextCompressor(llm_api=self._llm_api)
        self._short_term.set_compressor(self._compressor)
        self._diary_writer = DiaryWriter(memory_root=self._memory_root)
        self._diary_processor = DiaryProcessor(memory_root=self._memory_root)
        self._context_builder = ContextBuilder(
            card_store=self._card_store,
            memory_root=self._memory_root,
            short_term=self._short_term,
            intent_judge=self._intent_judge,
        )
        self._card_manager = CardManager(
            card_store=self._card_store,
            llm_api=self._llm_api,
            emotion_engine=self._emotion_engine,
            short_term=self._short_term,
            diary_writer=self._diary_writer,
            context_builder=self._context_builder,
        )

        # ── 回调接线 ──
        self._short_term.set_card_creator(self._card_manager._async_create_card)

        # ── 冷加载 ──
        self.personality = self._load_text("core/personality.md")
        self.mood_template = self._load_text("core/mood_blank.md")
        self._context_builder.personality = self.personality

        # ── 日记状态（代理到 DiaryWriter._last_active_date，单一真相源） ──

        # ── 兼容属性 ──
        self._pending_recalls: list = []
        self.last_emotion_tag = None
        self._write_threads: list = []

        # ── 启动补归档 + 压缩 ──
        catchup_dates = self._diary_writer._catch_up_diary()
        for date_str in catchup_dates:
            self._diary_processor.process_daily_diary_async(date_str)
        self._card_store.check_and_compress(
            tier1_days=getattr(config, 'CARD_TIER1_AGE_DAYS', 3),
            tier2_days=getattr(config, 'CARD_TIER2_AGE_DAYS', 30),
        )

        print(f"[MemoryCore] V5.1 门面模式就绪 "
              f"(短期: {len(self._short_term.short_term_history)}条, 卡片: {loaded}张)")

    # ── Capability 协议 ──

    @property
    def enabled(self) -> bool:
        return True

    async def initialize(self, deps) -> None:
        pass  # 初始化已在 __init__ 完成

    async def shutdown(self) -> None:
        """优雅关闭：等待异步写线程完成"""
        for t in getattr(self, '_write_threads', []):
            try:
                t.join(timeout=2.0)
            except Exception:
                pass

    def get_status(self) -> dict:
        short_count = self._short_term.get_short_term_count() if hasattr(self._short_term, 'get_short_term_count') else 0
        card_count = len(self._card_store._cards) if hasattr(self._card_store, '_cards') else 0
        return {
            "short_term_turns": short_count,
            "card_count": card_count,
            "last_active_date": self._last_active_date,
            "emotion": self.last_emotion_tag,
        }

    # ── MemoryCapability 窄接口别名 ──

    def search(self, keyword: str, limit: int = 5) -> str:
        return self.search_memory(keyword, limit)

    # ================================================================
    # 向后兼容的属性代理
    # ================================================================

    @property
    def _last_active_date(self):
        return self._diary_writer._last_active_date

    @_last_active_date.setter
    def _last_active_date(self, value):
        self._diary_writer._last_active_date = value

    @property
    def short_term_history(self):
        return self._short_term.short_term_history

    @short_term_history.setter
    def short_term_history(self, value):
        self._short_term.short_term_history = value

    # ================================================================
    # 文件 I/O 辅助
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

    def _write_json(self, file_path: Path, data: Any) -> None:
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
    # 公开 API — 委托给子组件
    # ================================================================

    def load_personality(self) -> str:
        return self.personality

    def load_mood_templates(self) -> str:
        return self.mood_template

    def load_tools_index(self) -> str:
        return self._load_text("tools/tools_index.md")

    # ── 短期记忆 ──

    def add_short_term(self, role: str, content: str) -> None:
        self._short_term.add_short_term(role, content)

    def get_short_term_count(self) -> int:
        return self._short_term.get_short_term_count()

    def get_short_term_context(self, max_turns: Optional[int] = None) -> str:
        return self._short_term.get_short_term_context(max_turns)

    def get_compressed_summary(self) -> str:
        return self._short_term.get_compressed_summary()

    def get_context_for_prompt(self, max_recent: int = 8) -> str:
        return self._short_term.get_context_for_prompt(max_recent)

    def get_short_term_visual(self) -> str:
        return self._short_term.get_short_term_visual()

    def flush(self) -> None:
        self._short_term.flush()
        print(f"[MemoryCore] flush: 卡片已落盘")

    # ── 卡片创建 ──

    def start_async_memory_write(self, user_text: str, ai_reply_text: str, source: str = ""):
        self._card_manager.start_async_memory_write(user_text, ai_reply_text, source)

    # ── 卡片审核 ──

    def review_pending_cards(self) -> List[Card]:
        """获取所有待审核卡片"""
        return self._card_store.get_pending_cards()

    def approve_card(self, card_id: str, edits: dict = None) -> str:
        """批准待审核卡片，可选编辑字段后批准"""
        return self._card_store.approve_card(card_id, edits)

    def reject_card(self, card_id: str) -> None:
        """拒绝并归档待审核卡片"""
        self._card_store.reject_card(card_id)

    def edit_card(self, card_id: str, **kwargs) -> None:
        """编辑卡片字段"""
        self._card_store.update_card(card_id, **kwargs)

    def merge_cards(self, card_ids: List[str]) -> str:
        """合并多张卡片到最重要的一张，其余软删除"""
        return self._card_store.merge_cards(card_ids)

    # ── 时间推演查询 ──

    def query_temporal(self, question: str) -> str:
        """解析自然语言时间窗口，返回按周分组的记忆摘要"""
        import re
        from datetime import datetime, timedelta
        now = datetime.now()

        # 时间窗口解析
        start_date = end_date = None
        label = ""

        m = re.search(r'(这[周个]|本[周个])', question)
        if m:
            start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")
            end_date = now.strftime("%Y-%m-%d")
            label = "最近一周"

        m = re.search(r'(上[个]?月)', question)
        if m:
            first_of_this_month = now.replace(day=1)
            last_of_prev_month = first_of_this_month - timedelta(days=1)
            start_date = last_of_prev_month.replace(day=1).strftime("%Y-%m-%d")
            end_date = last_of_prev_month.strftime("%Y-%m-%d")
            label = "上个月"

        m = re.search(r'最近\s*(\d+)\s*天', question)
        if m:
            n = int(m.group(1))
            start_date = (now - timedelta(days=n)).strftime("%Y-%m-%d")
            end_date = now.strftime("%Y-%m-%d")
            label = f"最近{n}天"

        m = re.search(r'(\d+)\s*天前', question)
        if m:
            n = int(m.group(1))
            day = (now - timedelta(days=n)).strftime("%Y-%m-%d")
            start_date = day
            end_date = day
            label = f"{n}天前"

        if not start_date:
            return ""

        cards = self._card_store.retrieve_by_date(start_date, end_date)

        if not cards:
            return f"{label}（{start_date}~{end_date}）无记忆记录"

        # 按周分组
        weeks: Dict[str, List[Card]] = {}
        for c in cards:
            ts = c.timestamp[:10] if c.timestamp else "?"
            try:
                dt = datetime.fromisoformat(ts)
                week_start = (dt - timedelta(days=dt.weekday())).strftime("%Y-%m-%d")
            except Exception:
                week_start = ts
            weeks.setdefault(week_start, []).append(c)

        lines = [f"【{label}记忆摘要】（{start_date}~{end_date}）"]
        for wk in sorted(weeks):
            wk_cards = weeks[wk]
            topics = {}
            for c in wk_cards:
                t = c.topic[:30]
                topics[t] = topics.get(t, 0) + 1
            top = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:3]
            topic_summary = ", ".join(f"{t}({n}张)" for t, n in top)
            lines.append(f"  {wk} 起一周: {len(wk_cards)} 张 | {topic_summary}")

        return "\n".join(lines)

    # ── 知识地形 ──

    def get_knowledge_terrain(self) -> dict:
        """返回知识库地形图，供 AI 了解记忆库整体结构"""
        from collections import Counter

        communities = self._card_store.detect_communities()
        tag_clusters = self._card_store.build_tag_clusters()
        orphans = self._card_store._find_orphans()

        community_stats: Dict[int, dict] = {}
        for cid, comm_id in communities.items():
            card = self._card_store.get_card(cid)
            if not card:
                continue
            if comm_id not in community_stats:
                community_stats[comm_id] = {
                    "card_count": 0,
                    "avg_importance": 0.0,
                    "top_topics": [],
                    "dominant_emotion": "neutral",
                }
            s = community_stats[comm_id]
            s["card_count"] += 1
            s["avg_importance"] += card.importance
            s["top_topics"].append(card.topic)

        for s in community_stats.values():
            s["avg_importance"] = round(s["avg_importance"] / s["card_count"], 2) if s["card_count"] else 0
            s["top_topics"] = [t for t, _ in Counter(s["top_topics"]).most_common(3)]

        # 每个社区的 dominant_emotion
        comm_emotions: Dict[int, Counter] = {}
        for cid, comm_id in communities.items():
            card = self._card_store._cards.get(cid)
            if not card:
                continue
            if comm_id not in comm_emotions:
                comm_emotions[comm_id] = Counter()
            comm_emotions[comm_id][card.emotion] += 1
        for comm_id, counter in comm_emotions.items():
            if comm_id in community_stats:
                top = counter.most_common(1)
                community_stats[comm_id]["dominant_emotion"] = top[0][0] if top else "neutral"

        # 全局 dominant emotion
        global_emotions = Counter()
        for card in self._card_store._cards.values():
            if card.tier >= 0 and card.status != "pending":
                global_emotions[card.emotion] += 1
        top_global = global_emotions.most_common(1)

        tier_counts = {"tier_0": 0, "tier_1": 0, "tier_2": 0}
        for card in self._card_store._cards.values():
            if card.status == "pending":
                continue
            key = f"tier_{card.tier}"
            if key in tier_counts:
                tier_counts[key] += 1

        total_cards = sum(tier_counts.values())
        orphan_count = len(orphans)
        health = "good"
        if orphan_count > max(5, total_cards * 0.3):
            health = "degraded"
        elif orphan_count > max(2, total_cards * 0.15):
            health = "warning"

        return {
            "total_cards": total_cards,
            "total_links": sum(len(v) for v in self._card_store._graph.values()),
            "community_count": len(community_stats),
            "communities": community_stats,
            "tag_clusters": [
                {"label": tc.label, "tags": tc.tags, "card_count": tc.card_count}
                for tc in tag_clusters[:5]
            ],
            "tier_distribution": tier_counts,
            "orphan_cards": orphan_count,
            "dominant_emotion": top_global[0][0] if top_global else "neutral",
            "health": health,
        }

    # ── 搜索 / 检索 ──

    def search_memory(self, keyword: str = "", limit: int = 5) -> str:
        return self._context_builder.search_memory(keyword, limit)

    def search_by_date(self, start_date: str = None, end_date: str = None) -> str:
        return self._context_builder.search_by_date(start_date, end_date)

    def search_diary(self, keyword: str, limit: int = 3) -> str:
        return self._context_builder.search_diary(keyword, limit)

    # ── 日记 ──

    def append_diary_draft(self, text: str) -> None:
        self._diary_writer.append_diary_draft(text)

    def check_cross_day_diary(self) -> None:
        archived = self._diary_writer.check_cross_day_diary()
        for date_str in archived:
            self._diary_processor.process_daily_diary_async(date_str)

    # ── 上下文组装 ──

    def build_recall_injection(self) -> Tuple[str, int]:
        return self._context_builder.build_recall_injection()

    def get_time_context(self) -> str:
        return self._context_builder.get_time_context()

    def build_context(self, user_input: str, max_history_turns: int = 10) -> str:
        return self._context_builder.build_context(user_input, max_history_turns)

    def detect_memory_intent(self, user_input: str) -> Dict[str, Any]:
        return self._context_builder.detect_memory_intent(user_input)

    def build_structured_sections(self, user_input: str, deep_recall: str = "") -> Dict[str, Any]:
        return self._context_builder.build_structured_sections(user_input, deep_recall)

    def detect_activity_type(self, text: str) -> str:
        return ContextBuilder.detect_activity_type(text)

    def do_deep_memory_recall(self, user_text: str) -> str:
        return self._context_builder.do_deep_memory_recall(user_text)

    # ── 情绪 ──

    def get_current_emotion(self) -> Dict[str, Any]:
        return self._emotion_engine.get_emotion_dict()

    def update_and_get_emotion(self, new_type: int, new_strength: float) -> Dict[str, Any]:
        self._emotion_engine.update_emotion(new_type, new_strength)
        return self._emotion_engine.get_emotion_dict()

    # ── 兼容旧 API ──

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

    def get_random_long_term_memory_v3(self, count: int = 1) -> str:
        return self.get_random_long_term_memory(count)

    # ================================================================
    # 静态方法 — 委托给 tools.py 模块函数
    # ================================================================

    @staticmethod
    def load_files(filenames: list) -> str:
        return tools.load_files(filenames)

    @staticmethod
    def append_to_file(filename: str, content: str) -> None:
        tools.append_to_file(filename, content)

    @staticmethod
    def get_random_long_term_memory(n: int = 3) -> str:
        return tools.get_random_long_term_memory(n)

    @staticmethod
    def set_short_term_memory_cache(history: list) -> None:
        tools.set_short_term_memory_cache(history)

    @staticmethod
    def write_file(filename: str, content: str) -> None:
        tools.write_file(filename, content)

    @staticmethod
    def create_file(filename: str = "", content: str = "", overwrite: bool = False) -> str:
        return tools.create_file(filename, content, overwrite)

    @staticmethod
    def load_tool_docs() -> str:
        return tools.load_tool_docs()

    @staticmethod
    def tool_read_file(filenames) -> str:
        return tools.tool_read_file(filenames)

    @staticmethod
    def tool_write_file(filename: str, content: str) -> str:
        return tools.tool_write_file(filename, content)

    @staticmethod
    def tool_search_memory(keyword: str, target_date=None, llm=None) -> str:
        return tools.tool_search_memory(keyword, target_date, llm)

    @staticmethod
    def tool_summarize_and_archive(max_lines=50, llm=None) -> str:
        return tools.tool_summarize_and_archive(max_lines, llm)

    @staticmethod
    def tool_write_diary(target_date=None, llm=None) -> str:
        return tools.tool_write_diary(target_date, llm)
