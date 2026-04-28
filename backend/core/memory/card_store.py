"""
CardStore —— 记忆卡片存储引擎
- JSONL 追加写 (cards.jsonl)
- 邻接表图 (graph.json)
- 倒排索引 (内存构建 + 定期写盘)
- BFS 检索
- 三层算法压缩 (无 LLM)
"""
from __future__ import annotations

import json
import os
import math
import time
import threading
from datetime import datetime
from typing import Dict, List, Set, Optional, Tuple
from pathlib import Path
from collections import deque

from .card import (
    Card, dict_to_card, card_to_dict, generate_card_id,
    score_importance,
)
from utils.text_utils import (
    extract_keywords, same_date, jaccard_similarity, parse_iso,
)


class CardStore:
    """记忆卡片存储引擎"""

    def __init__(self, memory_root: Optional[Path] = None):
        if memory_root is None:
            memory_root = Path(__file__).parent.parent.parent / "agent_memory"

        self._root = memory_root
        self._cards_dir = self._root / "cards"
        self._cards_dir.mkdir(parents=True, exist_ok=True)

        self._cards_jsonl = self._cards_dir / "cards.jsonl"
        self._graph_json = self._cards_dir / "graph.json"
        self._index_json = self._cards_dir / "index.json"

        # 内存缓存
        self._cards: Dict[str, Card] = {}
        self._graph: Dict[str, Dict[str, float]] = {}
        self._inverted_index: Dict[str, Set[str]] = {}
        self._lock = threading.Lock()

        # 压缩相关
        self._last_compression_check = time.time()
        self._compression_interval = 6 * 3600  # 默认 6 小时

    # ── 加载 / 初始化 ────────────────────────────────

    def load_all(self) -> int:
        """启动时加载所有卡片 + 重建索引"""
        loaded = 0
        if self._cards_jsonl.exists():
            try:
                with open(self._cards_jsonl, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            card = dict_to_card(d)
                            if card.tier >= 0:  # 跳过软删除
                                self._cards[card.id] = card
                                loaded += 1
                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                print(f"[CardStore] 加载 cards.jsonl 失败: {e}")

        # 加载图
        if self._graph_json.exists():
            try:
                self._graph = json.loads(self._graph_json.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[CardStore] 加载 graph.json 失败: {e}")

        # 重建倒排索引
        self._rebuild_index()

        print(f"[CardStore] 加载完成: {loaded} 卡片, {len(self._graph)} 图节点, {len(self._inverted_index)} 索引键")
        return loaded

    def _rebuild_index(self):
        """从内存卡片重建倒排索引"""
        self._inverted_index.clear()
        for card in self._cards.values():
            for tag in card.tags:
                tag_lower = tag.lower()
                if tag_lower not in self._inverted_index:
                    self._inverted_index[tag_lower] = set()
                self._inverted_index[tag_lower].add(card.id)

    def _save_graph(self):
        """原子写图文件"""
        try:
            tmp = self._graph_json.with_suffix('.json.tmp')
            tmp.write_text(json.dumps(self._graph, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._graph_json)
        except Exception as e:
            print(f"[CardStore] 保存 graph.json 失败: {e}")

    def _save_index(self):
        """原子写索引文件"""
        try:
            data = {k: list(v) for k, v in self._inverted_index.items()}
            tmp = self._index_json.with_suffix('.json.tmp')
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._index_json)
        except Exception as e:
            print(f"[CardStore] 保存 index.json 失败: {e}")

    # ── 卡片 CRUD ────────────────────────────────────

    def append_card(self, card: Card) -> str:
        """追加一张新卡片 (JSONL + 内存 + 倒排索引 + 自动链接)"""
        with self._lock:
            # 分配 ID
            if not card.id:
                card.id = generate_card_id()

            # 自动链接
            self._auto_link(card)

            # 写入 JSONL
            try:
                with open(self._cards_jsonl, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(card_to_dict(card), ensure_ascii=False) + "\n")
            except Exception as e:
                print(f"[CardStore] 写入 cards.jsonl 失败: {e}")

            # 更新内存
            self._cards[card.id] = card

            # 更新图
            self._graph[card.id] = card.links

            # 更新倒排索引
            for tag in card.tags:
                tag_lower = tag.lower()
                if tag_lower not in self._inverted_index:
                    self._inverted_index[tag_lower] = set()
                self._inverted_index[tag_lower].add(card.id)

            # 定期写盘图+索引
            self._maybe_save()

            return card.id

    def get_card(self, card_id: str) -> Optional[Card]:
        with self._lock:
            return self._cards.get(card_id)

    def delete_card(self, card_id: str, soft: bool = True):
        """删除卡片 (默认软删除: tier=-1)"""
        with self._lock:
            card = self._cards.get(card_id)
            if not card:
                return
            if soft:
                card.tier = -1
            else:
                del self._cards[card_id]
                if card_id in self._graph:
                    del self._graph[card_id]
                # 清理倒排索引
                for tag in card.tags:
                    tag_lower = tag.lower()
                    if tag_lower in self._inverted_index:
                        self._inverted_index[tag_lower].discard(card_id)

    def update_card(self, card_id: str, **kwargs):
        """更新卡片字段"""
        with self._lock:
            card = self._cards.get(card_id)
            if not card:
                return
            for k, v in kwargs.items():
                if hasattr(card, k):
                    setattr(card, k, v)

    # ── 自动链接 ─────────────────────────────────────

    def _auto_link(self, new_card: Card):
        """为卡片自动建立双向链接 (算法，不用 LLM)"""
        threshold = 0.25
        for existing in self._cards.values():
            if existing.id == new_card.id or existing.tier < 0:
                continue

            score = 0.0

            # 共享标签
            shared = set(t.lower() for t in new_card.tags) & set(t.lower() for t in existing.tags)
            score += len(shared) * 0.2

            # 同一天
            if new_card.timestamp and existing.timestamp:
                if same_date(new_card.timestamp, existing.timestamp):
                    score += 0.3

            # 同情绪
            if new_card.emotion and existing.emotion:
                if new_card.emotion == existing.emotion:
                    score += 0.15

            # 主题 Jaccard
            score += jaccard_similarity(new_card.topic, existing.topic) * 0.1

            if score >= threshold:
                weight = min(1.0, round(score, 2))
                new_card.links[existing.id] = weight
                existing.links[new_card.id] = weight
                self._graph[existing.id] = existing.links

        self._graph[new_card.id] = new_card.links

    # ── BFS 检索 ─────────────────────────────────────

    def retrieve(
        self,
        query_tags: List[str],
        max_depth: int = 3,
        limit: int = 10,
        keyword_weight: float = 0.5,
        recency_weight: float = 0.3,
        importance_weight: float = 0.2,
        recency_halflife: int = 7,
    ) -> List[Card]:
        """
        BFS 检索：从种子卡片出发，沿图遍历，返回排序结果
        """
        with self._lock:
            # 1. 找种子卡片
            seeds: List[str] = []
            seen_seeds: Set[str] = set()
            for tag in query_tags:
                tag_lower = tag.lower()
                for idx_tag, card_ids in self._inverted_index.items():
                    if tag_lower in idx_tag or idx_tag in tag_lower:
                        for cid in card_ids:
                            if cid not in seen_seeds:
                                seen_seeds.add(cid)
                                seeds.append(cid)

            if not seeds:
                # 无种子时返回最近的高重要性卡片
                valid = [c for c in self._cards.values() if c.tier >= 0]
                valid.sort(key=lambda c: (c.importance, c.timestamp), reverse=True)
                return valid[:limit]

            # 2. BFS
            visited: Dict[str, float] = {}
            queue: deque = deque()
            for sid in seeds:
                queue.append((sid, 0, 1.0))

            while queue:
                cid, depth, incoming = queue.popleft()
                if cid in visited and visited[cid] >= incoming:
                    continue
                visited[cid] = max(visited.get(cid, 0), incoming)
                if depth >= max_depth:
                    continue
                links = self._graph.get(cid, {})
                for linked_id, weight in links.items():
                    if linked_id not in visited:
                        queue.append((linked_id, depth + 1, incoming * weight))

            # 3. 打分排序
            scored: List[Tuple[Card, float]] = []
            now = datetime.now()
            for cid, bfs_score in visited.items():
                card = self._cards.get(cid)
                if not card or card.tier < 0:
                    continue

                # 关键词匹配
                card_tags_lower = set(t.lower() for t in card.tags)
                query_lower = set(t.lower() for t in query_tags)
                keyword_score = len(card_tags_lower & query_lower) / max(len(query_lower), 1)

                # 时间衰减
                days_ago = 0.0
                if card.timestamp:
                    try:
                        days_ago = (now - parse_iso(card.timestamp)).total_seconds() / 86400.0
                    except Exception:
                        pass
                recency = math.exp(-days_ago / recency_halflife)

                final = (
                    keyword_weight * keyword_score +
                    recency_weight * recency +
                    importance_weight * card.importance
                )
                scored.append((card, final))

            scored.sort(key=lambda x: x[1], reverse=True)
            return [c for c, s in scored[:limit]]

    def retrieve_by_date(self, start_date: str, end_date: str, limit: int = 20) -> List[Card]:
        """按日期范围检索"""
        with self._lock:
            results = []
            for card in self._cards.values():
                if card.tier < 0 or not card.timestamp:
                    continue
                ts = card.timestamp[:10]
                if start_date <= ts <= end_date:
                    results.append(card)
            results.sort(key=lambda c: c.timestamp, reverse=True)
            return results[:limit]

    def retrieve_by_emotion(self, emotion: str, limit: int = 10) -> List[Card]:
        """按情绪检索"""
        with self._lock:
            results = [c for c in self._cards.values()
                       if c.tier >= 0 and c.emotion == emotion]
            results.sort(key=lambda c: c.importance, reverse=True)
            return results[:limit]

    # ── 双向链路查询 ─────────────────────────────────

    def get_linked_cards(self, card_id: str, depth: int = 1) -> List[Card]:
        """获取与指定卡片关联的卡片"""
        with self._lock:
            result: List[Card] = []
            visited: Set[str] = {card_id}
            frontier = [card_id]

            for _ in range(depth):
                next_frontier = []
                for cid in frontier:
                    links = self._graph.get(cid, {})
                    for linked_id in sorted(links, key=links.get, reverse=True):
                        if linked_id not in visited:
                            visited.add(linked_id)
                            card = self._cards.get(linked_id)
                            if card and card.tier >= 0:
                                result.append(card)
                                next_frontier.append(linked_id)
                frontier = next_frontier
                if not frontier:
                    break

            return result

    def get_backlinks(self, card_id: str) -> List[Card]:
        """获取指向指定卡片的卡片"""
        with self._lock:
            result = []
            for other_id, links in self._graph.items():
                if card_id in links:
                    card = self._cards.get(other_id)
                    if card and card.tier >= 0:
                        result.append(card)
            result.sort(key=lambda c: self._graph[c.id].get(card_id, 0), reverse=True)
            return result

    # ── 三层压缩 (纯算法) ─────────────────────────────

    def check_and_compress(self, tier1_days: int = 3, tier2_days: int = 30):
        """检查是否需要压缩"""
        now = time.time()
        if now - self._last_compression_check < self._compression_interval:
            return
        self._last_compression_check = now

        tier0_cutoff = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        # 简化：用现在时间往前推
        cutoff_t1 = (datetime.now() - _days_delta(tier1_days)).isoformat()
        cutoff_t2 = (datetime.now() - _days_delta(tier2_days)).isoformat()

        self._compress_tier0_to_t1(cutoff_t1)
        self._compress_tier1_to_t2(cutoff_t2)

    def _compress_tier0_to_t1(self, cutoff: str):
        """Tier 0 → Tier 1: 对同 topic 分组，保留 top-3，其余截断"""
        with self._lock:
            # 收集需要压缩的 Tier 0 卡片 (早于 cutoff)
            candidates = [
                c for c in self._cards.values()
                if c.tier == 0 and c.timestamp < cutoff
            ]
            if len(candidates) < 5:
                return

            # 按 topic 相似度分组 (Jaccard ≥ 0.3 归一组)
            groups: List[List[Card]] = []
            assigned: Set[str] = set()

            for card in candidates:
                if card.id in assigned:
                    continue
                group = [card]
                assigned.add(card.id)
                for other in candidates:
                    if other.id in assigned:
                        continue
                    if jaccard_similarity(card.topic, other.topic) >= 0.3:
                        group.append(other)
                        assigned.add(other.id)
                groups.append(group)

            for group in groups:
                if len(group) < 2:
                    continue
                # 按 importance 排序
                group.sort(key=lambda c: c.importance, reverse=True)
                # 保留 top-3: 标记为 Tier 0 (保持不变)
                keep = group[:3]
                # 其余: 4x 比例压缩 → Tier 1
                rest = group[3:]
                for card in rest:
                    card.tier = 1
                    card.content = _proportional_compress(card.content, 4)
                    card.detail = ""

                # 生成一张 summary 卡片
                if group[0].importance >= 0.5:
                    summary = Card(
                        id=generate_card_id(),
                        type="summary",
                        timestamp=datetime.now().isoformat(),
                        topic=group[0].topic,
                        tags=list(set(t for c in group for t in c.tags[:4])),
                        content=f"关于「{group[0].topic}」的{len(group)}段对话已自动整理。",
                        importance=group[0].importance,
                        emotion=group[0].emotion,
                        tier=1,
                    )
                    # 链接到组内卡片
                    for c in keep:
                        summary.links[c.id] = 0.8
                        c.links[summary.id] = 0.8
                    self._cards[summary.id] = summary

            # 写盘
            self._save_graph()

    def _compress_tier1_to_t2(self, cutoff: str):
        """Tier 1 → Tier 2: 同 topic 只保留精华卡，其余软删除"""
        with self._lock:
            candidates = [
                c for c in self._cards.values()
                if c.tier == 1 and c.timestamp < cutoff
            ]
            if len(candidates) < 3:
                return

            groups: List[List[Card]] = []
            assigned: Set[str] = set()

            for card in candidates:
                if card.id in assigned:
                    continue
                group = [card]
                assigned.add(card.id)
                for other in candidates:
                    if other.id in assigned:
                        continue
                    if jaccard_similarity(card.topic, other.topic) >= 0.3:
                        group.append(other)
                        assigned.add(other.id)
                groups.append(group)

            for group in groups:
                if len(group) < 2:
                    continue
                group.sort(key=lambda c: c.importance, reverse=True)
                # 保留 importance 最高的，128x 比例压缩 → Tier 2
                best = group[0]
                best.tier = 2
                best.content = _proportional_compress(best.content, 128)
                # 合并 links
                for other in group[1:]:
                    for linked_id, w in other.links.items():
                        if linked_id != best.id:
                            best.links[linked_id] = max(best.links.get(linked_id, 0), w)
                    # 软删除
                    other.tier = -1

            self._save_graph()

    # ── 最近卡片 ─────────────────────────────────────

    def get_recent_cards(self, n: int = 3) -> List[Card]:
        with self._lock:
            valid = [c for c in self._cards.values() if c.tier >= 0]
            valid.sort(key=lambda c: c.timestamp, reverse=True)
            return valid[:n]

    def get_random_card(self, n: int = 1) -> List[Card]:
        import random
        with self._lock:
            valid = [c for c in self._cards.values() if c.tier >= 0]
            if len(valid) <= n:
                return valid
            return random.sample(valid, n)

    # ── 统计 / 健康 ──────────────────────────────────

    @property
    def card_count(self) -> int:
        return sum(1 for c in self._cards.values() if c.tier >= 0)

    def flush(self):
        """强制落盘图+索引"""
        self._save_graph()
        self._save_index()

    def _maybe_save(self):
        """每 30 次写入落盘一次索引"""
        if not hasattr(self, '_write_count'):
            self._write_count = 0
        self._write_count += 1
        if self._write_count % 30 == 0:
            self._save_graph()
            self._save_index()


def _days_delta(days: int):
    """返回 days 天前的 timedelta"""
    from datetime import timedelta
    return timedelta(days=days)


def _proportional_compress(text: str, ratio: int) -> str:
    """比例压缩：保留原文的 1/ratio，按句号分割取前 N 句"""
    if not text:
        return ""
    target_len = max(len(text) // ratio, 20)  # 最低保留 20 字符
    sentences = text.replace("。", "。\n").replace("！", "！\n").replace("？", "？\n").split("\n")
    result = ""
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        if len(result) + len(s) > target_len:
            break
        result += s
    return result if result else text[:target_len]
