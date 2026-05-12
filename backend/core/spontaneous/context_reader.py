"""
上下文读取器：读取短期记忆、长期记忆、自言自语等，为发言提供材料
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from ..memory.memory_facade import MemoryFacade as MemoryCore


class ContextReader:
    """读取各种内存数据，为主动发言提供上下文"""

    def __init__(self, memory_core: MemoryCore):
        self.memory_core = memory_core

    def read_short_term(self, max_entries: int = 10) -> List[Dict[str, Any]]:
        """读取短期记忆（最近对话）"""
        history = self.memory_core.short_term_history
        if not history:
            return []
        return history[-max_entries:]

    def read_long_term_summary(self) -> str:
        """读取长期记忆的总结（从卡片存储）"""
        try:
            recent = self.memory_core._card_store.get_recent_cards(5)
            if recent:
                lines = [f"[{c.timestamp[:10]}] {c.topic}: {c.content[:100]}" for c in recent]
                return "\n".join(lines)
            return ""
        except Exception as e:
            print(f"[ContextReader] 读取长期记忆失败: {e}")
            return ""

    def read_recent_thoughts(self) -> str:
        """读取近期的自言自语（情绪模板）"""
        try:
            mood_content = self.memory_core.load_mood_templates()
            if mood_content and "❌" not in mood_content:
                lines = [line.strip() for line in mood_content.split('\n') if line.strip()]
                return "\n".join(lines[-10:]) if lines else ""
            return ""
        except Exception as e:
            print(f"[ContextReader] 读取自言自语失败: {e}")
            return ""

    def read_daily_diary(self) -> str:
        """读取今天的日记（如果有）"""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            diary_path = Path(__file__).parent.parent.parent / "agent_memory" / "diary" / "daily" / f"{today}.md"

            if diary_path.exists():
                with open(diary_path, 'r', encoding='utf-8') as f:
                    return f.read()
            return ""
        except Exception as e:
            print(f"[ContextReader] 读取日记失败: {e}")
            return ""

    def get_time_context(self) -> Dict[str, str]:
        """获取时间上下文（早中晚、星期几等）"""
        now = datetime.now()
        hour = now.hour

        # 时间段
        if 5 <= hour < 12:
            time_of_day = "早上"
        elif 12 <= hour < 14:
            time_of_day = "中午"
        elif 14 <= hour < 18:
            time_of_day = "下午"
        elif 18 <= hour < 22:
            time_of_day = "晚上"
        else:
            time_of_day = "深夜"

        # 星期几
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        weekday = weekdays[now.weekday()]

        return {
            "time_of_day": time_of_day,
            "weekday": weekday,
            "hour": str(hour),
            "date": now.strftime("%Y年%m月%d日")
        }

    def build_context_summary(self) -> Dict[str, Any]:
        """构建完整的上下文摘要"""
        short_term = self.read_short_term(max_entries=5)
        long_term = self.read_long_term_summary()
        thoughts = self.read_recent_thoughts()
        diary = self.read_daily_diary()
        time_ctx = self.get_time_context()

        # 分析最近对话主题
        topics = []
        if short_term:
            last_user_msgs = [d['content'] for d in short_term if d.get('role') == 'user']
            if last_user_msgs:
                # 简单提取关键词（实际可以更智能）
                last_msg = last_user_msgs[-1][:50]
                topics.append(f"最近聊到: {last_msg}")

        return {
            "short_term_count": len(short_term),
            "recent_topics": topics,
            "long_term_summary": long_term[:200] + "..." if len(long_term) > 200 else long_term,
            "recent_thoughts": thoughts,
            "has_diary": bool(diary),
            "time_context": time_ctx,
            "raw_short_term": short_term[-3:] if short_term else []  # 最后3条
        }

    async def get_lightweight_context(self, short_term_n: int = 3, top_card_n: int = 1) -> dict:
        """轻量上下文，供追问/唤醒生成使用，不触发完整 BFS 检索"""
        ctx: Dict[str, Any] = {"recent_turns": [], "top_card": None}
        try:
            history = self.memory_core.short_term_history
            if history:
                recent = history[-(short_term_n * 2):]
                ctx["recent_turns"] = [
                    {"role": d.get("role", ""), "content": d.get("content", "")}
                    for d in recent
                ]
        except Exception:
            pass
        try:
            if hasattr(self.memory_core, "_card_store"):
                cards = self.memory_core._card_store.get_recent_cards(top_card_n)
                if cards:
                    ctx["top_card"] = {"topic": cards[0].topic, "content": cards[0].content[:120]}
        except Exception:
            pass
        return ctx

    def search_relevant_memories(self, keywords: list, limit: int = 5) -> list:
        """BFS检索与关键词相关的记忆卡片"""
        if not keywords or not hasattr(self.memory_core, '_card_store'):
            return []
        try:
            cards = self.memory_core._card_store.retrieve(
                query_tags=keywords, limit=limit,
                max_depth=3, recency_halflife=7
            )
            return [
                {"topic": c.topic, "content": c.content[:150],
                 "timestamp": c.timestamp, "emotion": c.emotion}
                for c in cards
            ]
        except Exception as e:
            print(f"[ContextReader] 记忆搜索失败: {e}")
            return []