"""
上下文组装器：搜索、检索、时间上下文、结构化分区
"""
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path
import config
from utils.text_utils import extract_keywords


class ContextBuilder:
    def __init__(self, card_store, memory_root: Path, short_term=None, intent_judge=None):
        self._card_store = card_store
        self._memory_root = memory_root
        self._short_term = short_term
        self._intent_judge = intent_judge  # 前置 LLM 意图判断器（可选）
        self.personality = ""
        self._pending_recalls: list = []

    # ── 搜索 / 检索 ──

    def search_memory(self, keyword: str = "", limit: int = 5) -> str:
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
            return f"未找到与 '{keyword}' 明显相关的记忆"
        lines = [f"找到 {len(cards)} 条可能与 '{keyword}' 相关的记忆（请判断是否真的相关）："]
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
        """搜索日记文件：按日期关键词或标题匹配 .md 文件，优先返回 ## 日记 摘要"""
        import re as _re
        daily_dir = self._memory_root / "diary" / "daily"
        if not daily_dir.exists():
            return ""

        results = []
        for f in sorted(daily_dir.glob("*.md"), reverse=True):
            date_str = f.stem
            try:
                content = f.read_text(encoding="utf-8")
            except Exception:
                continue

            # 检查日期或标题匹配
            title_match = _re.search(r'^#\s*(.*)', content)
            title = title_match.group(1).strip() if title_match else date_str
            if keyword not in date_str and keyword not in title:
                continue

            # 优先提取 ## 日记 摘要段
            diary_m = _re.search(r'## 日记\n(.*?)(?=\n## |\n---|\Z)', content, _re.DOTALL)
            if diary_m and diary_m.group(1).strip():
                results.append(diary_m.group(1).strip())
            else:
                # 其次取浓缩对话
                condensed_m = _re.search(r'## 浓缩对话\n(.*?)(?=\Z)', content, _re.DOTALL)
                if condensed_m and condensed_m.group(1).strip():
                    results.append(condensed_m.group(1).strip()[:500])
                else:
                    results.append(content[:300].strip())

            if len(results) >= limit:
                break

        # 如果没找到日期匹配，退回到卡片搜索
        if not results:
            tags = extract_keywords(keyword, max_kw=3)
            cards = self._card_store.retrieve(query_tags=tags, limit=limit)
            if cards:
                return "\n".join(f"[{c.timestamp[:10]}] {c.content[:120]}" for c in cards)
            return ""

        return "\n---\n".join(results)

    # ── 索引（供 AI 主动查记忆时参考） ──

    def _build_card_index(self) -> str:
        """构建卡片话题索引 — 日记独立分类 + 卡片按类别层级展示"""
        from core.memory.card_store import get_tag_category

        try:
            cards = list(self._card_store._iterate_visible())
        except Exception:
            return ""
        if not cards:
            return "（暂无记忆卡片）"

        # ── 日记：独立成类，平级展示 ──
        diary_tags = self._card_store.parse_diary_tags()
        diary_date_set: Set[str] = set()
        diary_tag_list: List[str] = []
        for tag, dates in diary_tags.items():
            diary_tag_list.append(tag)
            for d in dates:
                diary_date_set.add(d)
        total_diaries = len(diary_date_set)

        # ── 卡片标签 → 分类聚合 ──
        cat_tags: Dict[str, Dict[str, int]] = {}  # cat -> {tag -> count}
        for c in cards:
            for t in c.tags:
                cat = get_tag_category(t)
                cat_tags.setdefault(cat, {}).setdefault(t, 0)
                cat_tags[cat][t] += 1

        sorted_cats = sorted(cat_tags.items(), key=lambda x: sum(x[1].values()), reverse=True)

        lines = [f"记忆索引（{len(cards)}张卡片，{total_diaries}篇日记）："]

        # 日记行（独立分类，最高级平级）
        if diary_tag_list:
            lines.append(f"▸ 日记 ({total_diaries}篇) — " + "、".join(diary_tag_list[:12]))

        # 卡片分类行
        for cat, tag_counts in sorted_cats:
            top_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:8]
            tag_names = [t for t, _ in top_tags]
            unique_tags = len(tag_counts)
            line = f"▸ {cat} ({unique_tags}标签) — " + "、".join(tag_names)
            if unique_tags > 8:
                line += "..."
            lines.append(line)

        return "\n".join(lines)

    def _build_diary_index(self) -> str:
        """构建日记文件索引 — 列出 daily/*.md 及标题"""
        import re as _re
        daily_dir = self._memory_root / "diary" / "daily"
        if not daily_dir.exists():
            return "（暂无日记文件）"

        files = sorted(daily_dir.glob("*.md"))
        if not files:
            return "（暂无日记文件）"

        lines = []
        for f in files:
            date_str = f.stem
            try:
                content = f.read_text(encoding="utf-8")
                # 提取标题
                title_match = _re.search(r'^#\s*(.*)', content)
                title = title_match.group(1).strip() if title_match else date_str
                title = title.replace("对话日记", "").strip() or date_str

                # 提取 ## 日记 摘要段第一句作为 snippet
                diary_m = _re.search(r'## 日记\n(.*?)(?=\n## |\n---|\Z)', content, _re.DOTALL)
                if diary_m:
                    snippet = diary_m.group(1).strip()[:60].replace("\n", " ")
                    lines.append(f"- {date_str}: {snippet}...")
                else:
                    lines.append(f"- {date_str}")
            except Exception:
                lines.append(f"- {date_str}")

        return "\n".join(lines) if lines else "（暂无日记文件）"

    # ── 回忆注入 ──

    def build_recall_injection(self) -> Tuple[str, int]:
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

    # ── 时间上下文 ──

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

    # ── 时间推演查询 ──

    def _query_temporal(self, question: str) -> str:
        """解析自然语言时间窗口，返回按周分组的记忆摘要（含日记）"""
        from datetime import datetime, timedelta
        now = datetime.now()
        start_date = end_date = None
        label = ""

        # ── 具体日期解析（优先级最高） ──
        specific_date = self._parse_specific_date(question)
        if specific_date:
            start_date = specific_date
            end_date = specific_date
            label = specific_date

        # ── 相对时间 ──
        if not start_date:
            m = re.search(r'(这[周个]|本[周个])', question)
            if m:
                start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")
                end_date = now.strftime("%Y-%m-%d")
                label = "最近一周"

        if not start_date:
            m = re.search(r'(上[个]?月)', question)
            if m:
                first_of_this_month = now.replace(day=1)
                last_of_prev_month = first_of_this_month - timedelta(days=1)
                start_date = last_of_prev_month.replace(day=1).strftime("%Y-%m-%d")
                end_date = last_of_prev_month.strftime("%Y-%m-%d")
                label = "上个月"

        if not start_date:
            m = re.search(r'最近\s*(\d+)\s*天', question)
            if m:
                n = int(m.group(1))
                start_date = (now - timedelta(days=n)).strftime("%Y-%m-%d")
                end_date = now.strftime("%Y-%m-%d")
                label = f"最近{n}天"

        if not start_date:
            m = re.search(r'(\d+)\s*天前', question)
            if m:
                n = int(m.group(1))
                day = (now - timedelta(days=n)).strftime("%Y-%m-%d")
                start_date = day
                end_date = day
                label = f"{n}天前"

        if not start_date:
            return ""

        # ── 日记查询（单日优先查日记文件） ──
        diary_text = ""
        if start_date == end_date:
            diary_path = self._memory_root / "diary" / "daily" / f"{start_date}.md"
            if diary_path.exists():
                try:
                    raw = diary_path.read_text(encoding="utf-8")
                    raw = raw.replace("\r\n", "\n")
                    # 返回摘要部分（分割线之前）
                    for marker in ["\n\n---\n\n## 浓缩对话", "\n---\n## 浓缩对话"]:
                        if marker in raw:
                            raw = raw.split(marker)[0]
                            break
                    diary_text = raw.strip()[:800]
                except Exception:
                    pass

        cards = self._card_store.retrieve_by_date(start_date, end_date)

        if not cards and not diary_text:
            return f"{label}（{start_date}~{end_date}）无记忆记录"

        parts = []
        if diary_text:
            parts.append(f"【{label} 日记】\n{diary_text}")

        if cards:
            weeks: dict = {}
            for c in cards:
                ts = c.timestamp[:10] if c.timestamp else "?"
                try:
                    dt = datetime.fromisoformat(ts)
                    week_start = (dt - timedelta(days=dt.weekday())).strftime("%Y-%m-%d")
                except Exception:
                    week_start = ts
                weeks.setdefault(week_start, []).append(c)

            lines = [f"【{label}记忆卡片】（{start_date}~{end_date}）"]
            for wk in sorted(weeks):
                wk_cards = weeks[wk]
                topics = {}
                for c in wk_cards:
                    t = c.topic[:30]
                    topics[t] = topics.get(t, 0) + 1
                top = sorted(topics.items(), key=lambda x: x[1], reverse=True)[:3]
                topic_summary = ", ".join(f"{t}({n}张)" for t, n in top)
                lines.append(f"  {wk} 起一周: {len(wk_cards)} 张 | {topic_summary}")
            parts.append("\n".join(lines))

        return "\n\n".join(parts)

    @staticmethod
    def _parse_specific_date(question: str) -> Optional[str]:
        """从问题中提取具体日期，返回 YYYY-MM-DD 或 None"""
        from datetime import datetime
        now = datetime.now()

        # 完整日期: 2026-05-09, 2026年5月9日
        m = re.search(r'(\d{4})[年-](\d{1,2})[月-](\d{1,2})日?', question)
        if m:
            try:
                return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            except ValueError:
                pass

        # 月-日: 5-9号, 5/9, 5.9
        m = re.search(r'(?<!\d)(\d{1,2})[-./](\d{1,2})号?', question)
        if m:
            try:
                return f"{now.year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
            except ValueError:
                pass

        # 中文日期: 5月9日, 5月9号
        m = re.search(r'(\d{1,2})月(\d{1,2})[日号]', question)
        if m:
            try:
                return f"{now.year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
            except ValueError:
                pass

        # 相对日期词
        relative = {"今天": 0, "昨天": 1, "前天": 2, "大前天": 3}
        for word, offset in relative.items():
            if word in question:
                return (now - timedelta(days=offset)).strftime("%Y-%m-%d")

        return None

    # ── 上下文组装 ──

    def build_context(self, user_input: str, max_history_turns: int = 10) -> str:
        parts: List[str] = []
        if self.personality:
            parts.append(f"【人设】\n{self.personality}")

        if self._short_term:
            history = self._short_term.short_term_history
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

        tags = extract_keywords(user_input, max_kw=3)
        cards = self._card_store.retrieve(query_tags=tags, limit=3)
        if cards:
            card_lines = [f"- {c.topic}: {c.content[:100]}" for c in cards]
            parts.append(f"【相关记忆】\n" + "\n".join(card_lines))

        parts.append(self._build_time_context())
        parts.append(f"【用户输入】\n{user_input}")
        return "\n\n".join(parts)

    # ── 记忆意图检测 ──

    def detect_memory_intent(self, user_input: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "intent": "chat",
            "date_query": None,
            "keyword_query": None,
            "write_request": False,
            "temporal_query": None,
        }
        write_words = ["记住", "记一下", "帮我记", "记下来", "写下来", "记一记"]
        if any(w in user_input for w in write_words):
            result["write_request"] = True

        # ── 前置 LLM 意图判断（优先，失败回退规则检测） ──
        llm_judged = False
        if self._intent_judge:
            llm_result = self._intent_judge.judge(user_input)
            if llm_result:
                llm_judged = True
                if llm_result.get("write_request"):
                    result["write_request"] = True
                domains = llm_result.get("domains", [])
                keywords = llm_result.get("keywords", [])

                if "temporal" in domains:
                    result["intent"] = "temporal_query"
                    result["temporal_query"] = user_input
                    print(f"[MemoryIntent] LLM判断: 时间推演查询 '{user_input[:30]}...'")
                    return result

                if llm_result.get("needs_search") and keywords:
                    result["intent"] = "keyword_query"
                    result["keyword_query"] = keywords[0]  # 取第一个关键词用于精确搜索
                    # 保留全部关键词供后续 BFS 使用
                    result["_llm_keywords"] = keywords
                    print(f"[MemoryIntent] LLM判断: 记忆查询, 关键词={keywords} (输入: '{user_input[:30]}...')")
                    return result
                elif not llm_result.get("needs_search"):
                    print(f"[MemoryIntent] LLM判断: 闲聊，无需查询 (输入: '{user_input[:30]}...')")
                    return result
                # needs_search 但无关键词 → 继续规则检测兜底

        # ── 规则检测（LLM 判断失败或结果不完整时的回退） ──
        if llm_judged:
            return result  # LLM 已判断但无需进一步处理

        # 时间推演词（优先检测，避免被 keyword_query 抢走）
        temporal_patterns = [
            r'(这[周个]|本[周个])', r'(上[个]?月)', r'最近\s*\d+\s*天',
            r'\d+\s*天前', r'(变化|趋势|进展|演变)',
        ]
        if any(re.search(p, user_input) for p in temporal_patterns):
            result["intent"] = "temporal_query"
            result["temporal_query"] = user_input
            print(f"[MemoryIntent] 检测到时间推演查询: '{user_input[:30]}...'")
            return result

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
        # 记忆查询前缀词：需要从提取的关键词中剥离
        _MEMORY_PREFIX_WORDS = [
            "你记得", "还记得", "记不记得", "记得吗", "你记不记得",
            "查查", "查一下", "翻翻", "翻一下", "讲讲", "说说",
            "帮我查", "帮我找", "帮我回忆",
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
                # 剥离记忆查询前缀，提取真正的搜索关键词
                query = user_input
                for prefix in sorted(_MEMORY_PREFIX_WORDS, key=len, reverse=True):
                    if query.startswith(prefix):
                        query = query[len(prefix):]
                        break
                # 再去掉末尾的语气词和问号
                query = re.sub(r'[吗呢吧啊的了吗？?！!。.]+$', '', query.strip())
                # 取第一个有意义的 2+ 字词作为关键词
                words = re.findall(r"[一-鿿\w]{2,}", query)
                keyword = words[0] if words else query[:20]
                result["keyword_query"] = keyword
                print(f"[MemoryIntent] 检测到记忆查询, 关键词: '{keyword}' (原始: '{user_input[:30]}...')")
        return result

    # ── 结构化分区 ──

    def build_structured_sections(self, user_input: str, deep_recall: str = "") -> Dict[str, Any]:
        intent = self.detect_memory_intent(user_input)
        # 优先使用 LLM 判断的关键词，否则回退到规则提取
        llm_keywords = intent.pop("_llm_keywords", None)
        tags = llm_keywords if llm_keywords else extract_keywords(user_input, max_kw=5)

        recent_cards = self._card_store.get_recent_cards(3)
        if recent_cards:
            diary_memory = "\n".join(
                f"[{c.timestamp[:10]}] {c.topic}: {c.content[:100]}" for c in recent_cards
            )
        else:
            diary_memory = "（暂无记忆卡片）"

        precise_query = ""
        if intent["intent"] == "temporal_query" and intent.get("temporal_query"):
            result = self._query_temporal(intent["temporal_query"])
            if result:
                precise_query = result[:500]
            else:
                precise_query = "（未找到时间推演结果）"
        elif intent["intent"] == "date_query" and intent["date_query"]:
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

        if not deep_recall:
            deep_recall_inject, _ = self.build_recall_injection()
            if deep_recall_inject:
                deep_recall = deep_recall_inject.replace("【潜意识浮现】", "").strip()
        if not deep_recall:
            deep_recall = "（无深层记忆浮现）"

        return {
            "diary_memory": "",
            "precise_query": precise_query,
            "pre_search": "",
            "deep_recall": deep_recall,
            "time_context": self._build_time_context(),
            "card_index": "",
            "diary_index": "",
            "write_request": intent["write_request"],
            "terrain": "",
        }

    # ── 深层回忆 ──

    def do_deep_memory_recall(self, user_text: str) -> str:
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

    # ── 活动类型检测 ──

    # ── 知识地形摘要 ──

    def _build_terrain_summary(self) -> str:
        """构建知识地形摘要文本（轻量，不触发完整 terrain 计算）"""
        cards = list(self._card_store._iterate_visible())
        if not cards:
            return ""

        total = len(cards)
        topic_counter: Dict[str, int] = {}
        tag_counter: Dict[str, int] = {}
        for c in cards:
            topic_counter[c.topic[:20]] = topic_counter.get(c.topic[:20], 0) + 1
            for t in c.tags:
                t_lower = t.lower()
                tag_counter[t_lower] = tag_counter.get(t_lower, 0) + 1

        top_topics = sorted(topic_counter.items(), key=lambda x: x[1], reverse=True)[:3]
        top_tags = sorted(tag_counter.items(), key=lambda x: x[1], reverse=True)[:5]

        orphans = sum(1 for c in cards
                      if not self._card_store._graph.get(c.id, {}))
        health = "良好"
        if orphans > max(5, total * 0.3):
            health = "需整理"
        elif orphans > max(2, total * 0.15):
            health = "一般"

        lines = [
            f"共 {total} 张记忆卡片",
            f"主要话题: {', '.join(f'{t}({n}张)' for t, n in top_topics) if top_topics else '暂无'}",
            f"常用标签: {', '.join(f'{t}({n}次)' for t, n in top_tags) if top_tags else '暂无'}",
            f"孤立卡片: {orphans}张",
            f"健康状态: {health}",
        ]
        return "【知识库概况】\n" + "\n".join(lines)

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
