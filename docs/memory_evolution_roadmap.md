# 记忆系统演进路线图

> 基于当前 V5.0 图结构-卡片记事法-层级压缩-双向链接架构
> 目标：半自动化、语义压缩、知识地形可感知、规模化稳定

---

## 当前基线

```
MemoryCore (外观层, ~500行)
  ├── short_term_history: List[dict]          # RAM 缓冲
  ├── CardStore (存储引擎, ~553行)
  │   ├── cards.jsonl: 12 张卡片 (追加写)
  │   ├── graph.json: 128 条边 (邻接表)
  │   ├── index.json: 35 个索引键 (倒排)
  │   ├── retrieve(): BFS + 关键词匹配
  │   └── compress(): 三层比例压缩 (4x / 128x)
  ├── EmotionEngine: 独立情绪模块
  └── Diary: 文件追加 (独立于卡片)
```

**已验证可用的部分**：Card 数据结构、JSONL 追加写、BFS 检索、自动链接算法（阈值需调整）、三层压缩骨架

**已确认的差距**：
1. 全自动建卡无审核 → 幻觉累积
2. 同天卡片互连度过高 → 图退化
3. `_auto_link` O(n) → 规模瓶颈
4. 压缩纯机械截断 → 语义丢失
5. 零聚类/零地形视角 → 无法感知知识结构
6. 全局锁 → 读写互斥

---

## 总体设计原则

1. **半自动优先**：AI 可以"建议"卡片，但最终落盘需要质量门槛。人可以不参与日常，但系统必须有审核能力。
2. **压缩 = 聚合而非截断**：Tier 升级时不是删信息，是提炼信息。低层级保留细节，高层级提炼结构。
3. **多维度知识视角**：同一组卡片，可以从标签、时间、情绪、图社区、重要性五个维度交叉观察。
4. **算法为主，LLM 为辅**：聚类、打分、链接、压缩全部算法化。LLM 只在两个点介入：建卡时提取 topic/tags/content，以及跨卡语义聚合时写摘要。

---

## Phase 1: 地基加固 (预计 2-3 天)

**目标**：修掉已知的稳定性/正确性问题，不改架构。

### 1.1 修复图退化

**问题**：`same_date` 无条件 +0.3，任何共享 1 个标签 (+0.2) 就超过阈值 0.25。同天卡片几乎全部互连 → BFS 从任意种子 1 步到达全图 → 图筛选失效。

**方案**：

```python
# card_store.py _auto_link()
# 改动: 日期加分从二值改为时间距离衰减

def _time_proximity_score(ts1: str, ts2: str) -> float:
    """时间邻近度: 同一天 0.15, 每差一天衰减一半"""
    try:
        d1 = parse_iso(ts1)
        d2 = parse_iso(ts2)
        days = abs((d1 - d2).total_seconds()) / 86400.0
        if days < 1.0:
            return 0.15  # 同一天从 0.3 降到 0.15
        return 0.15 * math.exp(-0.5 * (days - 1))  # 指数衰减
    except Exception:
        return 0.0

# 阈值提高: 0.25 → 0.35
threshold = 0.35
```

**效果**：同天卡片不再自动互连，需要有 2 个共享标签或其他维度加分才会建边。

**改动范围**：`card_store.py:191-223`，约 20 行。

### 1.2 建卡质量门

**问题**：每条对话都触发 LLM 建卡，低质量对话（"好吧好吧"、"嗯"）也生成卡片。

**方案**：

```python
# memory_core.py _create_card_sync()
# 在 LLM 提取后、落盘前加检查

MIN_IMPORTANCE = 0.4       # 低于此分不建卡
MIN_CONTENT_LEN = 15       # 卡片正文至少 15 字
MIN_TAGS = 2               # 至少 2 个标签

# 在 CardStore.append_card() 之前
if importance < MIN_IMPORTANCE:
    print(f"[Memory] 卡片质量不足，跳过: importance={importance}")
    return
if len(content) < MIN_CONTENT_LEN:
    print(f"[Memory] 内容过短，跳过: len={len(content)}")
    return
if len(tags) < MIN_TAGS:
    print(f"[Memory] 标签过少，跳过")
    return
```

**改动范围**：`memory_core.py:179-235`，约 10 行。

### 1.3 读写锁

**问题**：`threading.Lock()` 一把锁管所有。检索和建卡互斥，压缩阻塞检索。

**方案**：

```python
# card_store.py 新增
import threading

class CardStore:
    def __init__(self, ...):
        ...
        self._rw_lock = threading.RLock()
        self._readers = 0
        self._readers_lock = threading.Lock()

    def _acquire_read(self):
        with self._readers_lock:
            self._readers += 1
            if self._readers == 1:
                self._rw_lock.acquire()

    def _release_read(self):
        with self._readers_lock:
            self._readers -= 1
            if self._readers == 0:
                self._rw_lock.release()

    # 检索方法改用 _acquire_read / _release_read
    # 写入方法保持 _rw_lock.acquire / release
```

**效果**：多个 BFS 检索可并发，建卡/压缩互斥但不再阻塞检索。

**改动范围**：`card_store.py`，约 30 行。所有 `with self._lock:` 改为对应的读写锁调用。

### 1.4 Auto-link 性能

**问题**：每追加一张卡，遍历全部已有卡片做相似度计算 → O(n)。

**方案**：用倒排索引预筛选候选卡片，最多比较 30 张。

```python
# card_store.py _auto_link()
def _auto_link(self, new_card: Card):
    # 收集候选: 与 new_card 共享任意 tag 的已有卡片
    candidates: Set[str] = set()
    for tag in new_card.tags:
        tag_lower = tag.lower()
        if tag_lower in self._inverted_index:
            candidates.update(self._inverted_index[tag_lower])

    # 最多取 30 个候选 (按最近时间)
    candidate_cards = []
    for cid in candidates:
        card = self._cards.get(cid)
        if card and card.id != new_card.id and card.tier >= 0:
            candidate_cards.append(card)

    # 按时间排序，取最近 30 个
    candidate_cards.sort(key=lambda c: c.timestamp, reverse=True)
    candidate_cards = candidate_cards[:30]

    # 对候选做相似度计算
    for existing in candidate_cards:
        ...  # 现有逻辑
```

**效果**：100K 张卡片时，建卡从遍历 100K 次降到遍历 ≤30 次。

**改动范围**：`card_store.py:191-223`，约 15 行。

---

## Phase 2: 半自动化转型 (预计 3-4 天)

**目标**：引入卡片生命周期，AI 建议 → 质量打分 → 自动/手动审核 → 落盘。

### 2.1 卡片生命周期

```
                  ┌──────────┐
    LLM 提取 ──→ │ pending   │  (suggestion, 未落盘)
                  └────┬─────┘
                       │ quality check (importance >= 0.4)
                  ┌────▼─────┐
                  │ approved  │  (Tier 0, 正常卡片)
                  └────┬─────┘
                       │ age >= 3 days
                  ┌────▼─────┐
                  │ condensed │  (Tier 1, 4x 压缩)
                  └────┬─────┘
                       │ age >= 30 days
                  ┌────▼─────┐
                  │ essence   │  (Tier 2, 128x 压缩)
                  └────┬─────┘
                       │ importance < 0.2
                  ┌────▼─────┐
                  │ archived  │  (Tier -1, 软删除)
                  └──────────┘
```

**Card 新增字段**：

```python
@dataclass
class Card:
    ...
    status: str = "approved"   # "pending" | "approved" | "archived"
    reviewed_by: str = ""      # "auto" | "user"
    created_at: str = ""       # ISO timestamp
    updated_at: str = ""       # 最后修改时间
```

### 2.2 审核 API (MemoryCore 新增方法)

```python
class MemoryCore:
    def review_pending_cards(self) -> List[Card]:
        """返回所有待审核卡片"""

    def approve_card(self, card_id: str, edits: dict = None) -> str:
        """批准一张卡片 (可选编辑)"""

    def reject_card(self, card_id: str) -> None:
        """拒绝并删除待审核卡片"""

    def edit_card(self, card_id: str, **kwargs) -> None:
        """手动编辑已有卡片"""

    def merge_cards(self, card_ids: List[str]) -> str:
        """合并多张卡片为一张 (手动触发)"""
```

### 2.3 自动批准 / 建议模式

```python
# 配置控制
# default.yaml:
#   memory.card.auto_approve_threshold: 0.6  # >= 0.6 自动批准
#   memory.card.suggestion_mode: false        # true = 全部 pending 等待审核

def _create_card_sync(self, user_text, ai_text):
    ...
    if importance >= config.CARD_AUTO_APPROVE_THRESHOLD:
        card.status = "approved"
        self._card_store.append_card(card)
        print(f"[Memory] 自动批准: {card.id} importance={importance}")
    else:
        card.status = "pending"
        self._card_store.append_card(card)  # 落盘但标记 pending
        print(f"[Memory] 待审核: {card.id} importance={importance}")
```

### 2.4 卡片质量指标

```python
# card_store.py 新增
def get_card_health(self, card_id: str) -> dict:
    """返回卡片质量指标"""
    card = self._cards[card_id]
    return {
        "id": card.id,
        "importance": card.importance,
        "tag_count": len(card.tags),
        "content_len": len(card.content),
        "link_count": len(card.links),
        "is_orphan": len(card.links) == 0,          # 孤立节点
        "is_overlinked": len(card.links) > 20,       # 过度连接
        "tier": card.tier,
        "age_days": days_ago(card.timestamp),
        "quality_flag": self._flag_quality(card),    # "good" | "weak" | "stale"
    }
```

---

## Phase 3: 语义压缩 (预计 3-4 天)

**目标**：压缩不再是"截断前 1/4"，而是保留语义关键句 + 跨卡聚合精华。

### 3.1 智能截断

替代当前的 `_proportional_compress`：

```python
# card_store.py 重写 _proportional_compress

import re

# 高权重模式：包含这些模式的句子优先保留
_HIGH_WEIGHT_PATTERNS = [
    re.compile(p) for p in [
        r'(决定|结论|总之|关键|重要|记住|注意|必须|一定)',
        r'(发现|找到|解决|完成|实现|做到)',
        r'(\d+[个项条张次遍])',           # 数量词
        r'(http|www|https)://',            # URL
        r'(文件|路径|命令|配置|API|代码)',   # 技术名词
        r'([一二三四五六七八九十百千万亿])',    # 中文数字（可能表示要点）
    ]
]

def _smart_compress(text: str, target_ratio: int, min_len: int = 30) -> str:
    """智能压缩：保留高权重句子 + 首尾句"""
    if not text or len(text) <= min_len:
        return text

    target_len = max(len(text) // target_ratio, min_len)

    # 按句号/问号/感叹号分句
    sentences = re.split(r'(?<=[。！？\n])', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if len(sentences) <= 2:
        return text[:target_len]

    scored = []
    for i, s in enumerate(sentences):
        score = 0.0
        # 位置权重：首句 +0.2，末句 +0.2
        if i == 0:
            score += 0.2
        if i == len(sentences) - 1:
            score += 0.2
        # 模式权重
        for pat in _HIGH_WEIGHT_PATTERNS:
            if pat.search(s):
                score += 0.3
                break
        # 长度适中 (15-80 字)
        if 15 <= len(s) <= 80:
            score += 0.1
        scored.append((s, score))

    # 按得分排序，贪心选取直到 target_len
    scored.sort(key=lambda x: x[1], reverse=True)
    result = []
    used = 0
    for s, _ in scored:
        if used + len(s) > target_len and used > min_len:
            break
        result.append(s)
        used += len(s)

    # 按原始顺序输出
    result.sort(key=lambda x: text.find(x))
    return ''.join(result)
```

### 3.2 跨卡语义聚合

替代当前的模板字符串 summary：

```python
# card_store.py _compress_tier0_to_t1()
# 对同 topic 分组后，用 LLM 生成聚合摘要

def _generate_summary(self, cards: List[Card]) -> Optional[Card]:
    """LLM 聚合多张同 topic 卡片为一张精华卡"""
    if not self._llm_api or len(cards) < 3:
        return None

    # 只聚合 importance >= 0.5 的组
    best = max(cards, key=lambda c: c.importance)
    if best.importance < 0.5:
        return None

    # 构建聚合 prompt
    snippets = "\n---\n".join(
        f"[{c.timestamp[:10]}] {c.content[:150]}" for c in cards[:10]
    )
    prompt = (
        "## 记忆聚合\n"
        "以下是关于同一主题的多段对话记录。请提取核心信息，"
        "合成一段连贯的摘要 (≤150字)，只保留关键结论和决定：\n\n"
        f"主题: {best.topic}\n\n"
        f"{snippets}\n\n"
        "输出格式: 纯文本，一段话"
    )

    try:
        summary_text = self._llm_api.ask(prompt)
        if not summary_text or len(summary_text) < 10:
            return None

        return Card(
            id=generate_card_id(),
            type="summary",
            timestamp=datetime.now().isoformat(),
            topic=best.topic,
            tags=list(set(t for c in cards for t in c.tags[:3])),
            content=summary_text[:200],
            importance=best.importance,
            emotion=best.emotion,
            tier=1,
        )
    except Exception:
        return None
```

**重要限制**：LLM 聚合只在压缩时触发（每 6 小时一次，同 topic 卡片 ≥3 张），不是每条对话。频率远低于建卡，成本可控。

### 3.3 压缩回归验证

```python
# card_store.py 新增

def _verify_compression(self, original: str, compressed: str) -> bool:
    """快速验证压缩后是否保留了足够的信息"""
    if not compressed or not original:
        return False
    # 压缩后至少保留原关键词的 60%
    orig_kw = set(extract_keywords(original, max_kw=8))
    comp_kw = set(extract_keywords(compressed, max_kw=8))
    if not orig_kw:
        return True
    retention = len(orig_kw & comp_kw) / len(orig_kw)
    return retention >= 0.6
```

---

## Phase 4: 知识地形 (预计 4-5 天)

**目标**：让系统（和开发者）"一眼看懂"知识库的整体结构。

### 4.1 图社区检测

```python
# card_store.py 新增方法

def detect_communities(self) -> Dict[str, int]:
    """
    标签传播算法检测图社区
    返回: {card_id: community_id}
    """
    # 初始化: 每个节点自成一社区
    labels: Dict[str, int] = {}
    for i, cid in enumerate(self._graph):
        labels[cid] = i

    # 迭代标签传播 (最多 20 轮)
    for _ in range(20):
        changed = False
        for cid in self._graph:
            # 统计邻居的标签分布
            neighbors = self._graph.get(cid, {})
            label_votes: Dict[int, float] = {}
            for nid, weight in neighbors.items():
                if nid in labels:
                    lbl = labels[nid]
                    label_votes[lbl] = label_votes.get(lbl, 0) + weight

            if not label_votes:
                continue

            # 选择权重最高的标签
            best_label = max(label_votes, key=label_votes.get)
            if labels[cid] != best_label:
                labels[cid] = best_label
                changed = True

        if not changed:
            break

    return labels
```

### 4.2 标签共现聚类

```python
def build_tag_clusters(self, min_cooccur: int = 2) -> List[TagCluster]:
    """
    基于标签共现频率聚类
    返回: 标签簇列表，每个簇包含关联标签 + 代表卡片
    """
    # 构建标签共现矩阵
    cooccur: Dict[Tuple[str, str], int] = {}
    tag_cards: Dict[str, List[str]] = {}

    for card in self._cards.values():
        if card.tier < 0:
            continue
        tags_lower = [t.lower() for t in card.tags]
        for t in tags_lower:
            if t not in tag_cards:
                tag_cards[t] = []
            tag_cards[t].append(card.id)
        for i, t1 in enumerate(tags_lower):
            for t2 in tags_lower[i+1:]:
                pair = tuple(sorted([t1, t2]))
                cooccur[pair] = cooccur.get(pair, 0) + 1

    # Union-Find 聚类
    parent: Dict[str, str] = {}

    def find(x):
        if x not in parent:
            parent[x] = x
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for (t1, t2), count in cooccur.items():
        if count >= min_cooccur:
            union(t1, t2)

    # 收集聚类结果
    clusters: Dict[str, List[str]] = {}
    for tag in tag_cards:
        root = find(tag)
        if root not in clusters:
            clusters[root] = []
        clusters[root].append(tag)

    # 为每个聚类生成标签
    result = []
    for root, tags in clusters.items():
        if len(tags) < 2:
            continue
        # 聚类代表卡片: 包含最多该聚类标签的卡片
        all_cids = set()
        for t in tags:
            all_cids.update(tag_cards[t])
        representative = max(all_cids, key=lambda cid:
            len(set(t.lower() for t in self._cards[cid].tags) & set(tags))
        )
        result.append(TagCluster(
            tags=tags,
            card_count=len(all_cids),
            representative_card_id=representative,
            label=max(tags, key=lambda t: len(tag_cards[t])),
        ))

    return result
```

### 4.3 知识地形摘要 API

```python
# memory_core.py 新增方法

def get_knowledge_terrain(self) -> dict:
    """
    返回知识库的"地形图"，供 AI 一眼看懂知识结构
    """
    communities = self._card_store.detect_communities()
    tag_clusters = self._card_store.build_tag_clusters()

    # 按社区统计
    community_stats = {}
    for cid, comm_id in communities.items():
        card = self._card_store.get_card(cid)
        if not card:
            continue
        if comm_id not in community_stats:
            community_stats[comm_id] = {
                "card_count": 0,
                "avg_importance": 0.0,
                "top_topics": [],
                "dominant_emotion": None,
                "date_range": [None, None],
            }
        s = community_stats[comm_id]
        s["card_count"] += 1
        s["avg_importance"] += card.importance
        s["top_topics"].append(card.topic)

    # 计算平均值
    for s in community_stats.values():
        s["avg_importance"] = round(s["avg_importance"] / s["card_count"], 2)
        # Top 3 topics
        from collections import Counter
        s["top_topics"] = [t for t, _ in Counter(s["top_topics"]).most_common(3)]

    return {
        "total_cards": self._card_store.card_count,
        "total_links": sum(len(v) for v in self._card_store._graph.values()),
        "communities": community_stats,
        "tag_clusters": [
            {"label": tc.label, "tags": tc.tags, "card_count": tc.card_count}
            for tc in tag_clusters[:5]
        ],
        "tier_distribution": {
            "tier_0": sum(1 for c in self._card_store._cards.values() if c.tier == 0),
            "tier_1": sum(1 for c in self._card_store._cards.values() if c.tier == 1),
            "tier_2": sum(1 for c in self._card_store._cards.values() if c.tier == 2),
        },
        "emotion_timeline": self._get_emotion_timeline(),
        "orphan_cards": self._find_orphans(),
    }
```

### 4.4 将此地形信息注入 AI 上下文

```python
# actions.py action_think() 中
# 在 build_structured_sections 之后追加地形摘要

terrain = mc.get_knowledge_terrain()
terrain_summary = (
    f"【知识库概况】\n"
    f"共 {terrain['total_cards']} 张记忆卡片, "
    f"{len(terrain['communities'])} 个话题群落, "
    f"{len(terrain['tag_clusters'])} 个标签簇。\n"
    f"主要话题: {', '.join(c['label'] for c in terrain['tag_clusters'][:3])}。"
)
structured["terrain"] = terrain_summary
```

然后更新 `yume_system.md` 模板，添加 `{terrain}` 分区。

---

## Phase 5: 高级检索 (预计 3-4 天)

**目标**：从"关键词匹配 + BFS"升级到多维度检索。

### 5.1 多维度打分

```python
# card_store.py retrieve() 扩展打分维度

def retrieve(
    self,
    query_tags: List[str],
    query_emotion: str = None,
    query_date_range: Tuple[str, str] = None,
    max_depth: int = 3,
    limit: int = 10,
    weights: dict = None,
) -> List[Card]:
    """
    扩展检索权重：
    - keyword: 标签匹配
    - recency: 时间衰减
    - importance: 重要性
    - community: 社区相关性 (同一社区的卡片加分)
    - emotional: 情绪匹配
    - centrality: 图中心度 (链接越多的卡片越可能是枢纽)
    """
    w = weights or {
        "keyword": 0.30,
        "recency": 0.20,
        "importance": 0.20,
        "community": 0.15,
        "emotional": 0.10,
        "centrality": 0.05,
    }

    # 预计算图中心度
    centrality = {}
    for cid, links in self._graph.items():
        centrality[cid] = math.log(len(links) + 2) / 5.0  # 归一化

    # 预计算社区
    communities = self.detect_communities()
    seed_communities = set()
    for seed in seeds:
        if seed in communities:
            seed_communities.add(communities[seed])

    # 打分循环
    for cid, bfs_score in visited.items():
        ...
        # 社区加分
        community_score = 0.0
        if cid in communities and communities[cid] in seed_communities:
            community_score = 0.5

        # 情绪匹配
        emotional_score = 0.0
        if query_emotion and card.emotion == query_emotion:
            emotional_score = 0.5

        # 图中心度
        centrality_score = centrality.get(cid, 0.0)

        final = (
            w["keyword"] * keyword_score +
            w["recency"] * recency +
            w["importance"] * card.importance +
            w["community"] * community_score +
            w["emotional"] * emotional_score +
            w["centrality"] * centrality_score
        )
```

### 5.2 时间推演查询

```python
# memory_core.py 新增

def query_temporal(self, question: str) -> str:
    """
    时间推演查询。
    处理 "这周有什么变化"、"上个月在做什么" 等问题。
    """
    tags = extract_keywords(question, max_kw=3)
    now = datetime.now()

    # 时间窗口识别
    if any(w in question for w in ["这周", "本周", "最近一周"]):
        start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    elif any(w in question for w in ["上个月", "上月"]):
        start = (now - timedelta(days=30)).strftime("%Y-%m-%d")
        end = (now - timedelta(days=now.day)).strftime("%Y-%m-%d")
    elif any(w in question for w in ["变化", "改变", "不同"]):
        # 变化检测: 比较最近 vs 之前
        start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    else:
        start = (now - timedelta(days=14)).strftime("%Y-%m-%d")

    end = now.strftime("%Y-%m-%d")
    cards = self._card_store.retrieve_by_date(start, end, limit=15)

    if not cards:
        return f"{start} 至今无记录"

    # 按时间排序并分组
    cards.sort(key=lambda c: c.timestamp)
    groups = {}
    for c in cards:
        week = c.timestamp[:7]  # 按周分组
        if week not in groups:
            groups[week] = []
        groups[week].append(c)

    lines = [f"{start} 至今共 {len(cards)} 条记录:"]
    for week, week_cards in groups.items():
        topics = ", ".join(c.topic[:20] for c in week_cards[:3])
        lines.append(f"  {week}: {len(week_cards)} 条 ({topics}...)")

    return "\n".join(lines)
```

### 5.3 标签语义扩展 (可选，无向量 DB)

```python
# utils/text_utils.py 新增

# 轻量语义标签映射 (硬编码常见同义/近义词)
_SEMANTIC_MAP: Dict[str, List[str]] = {
    "bug": ["错误", "故障", "问题", "bug", "报错", "异常"],
    "食物": ["吃饭", "外卖", "食堂", "餐厅", "午饭", "晚饭", "早餐", "红烧肉"],
    "调试": ["debug", "测试", "调试", "修bug", "fix", "调参"],
    "记忆": ["记忆", "回忆", "忘记", "记住", "记录", "存储"],
    "情绪": ["开心", "难过", "生气", "委屈", "惊讶", "happy", "sad"],
}

def expand_query_tags(tags: List[str]) -> List[str]:
    """扩展查询标签的同义词"""
    expanded = set(tags)
    for tag in tags:
        tag_lower = tag.lower()
        for key, synonyms in _SEMANTIC_MAP.items():
            if tag_lower in synonyms or tag_lower == key:
                expanded.update(synonyms)
                break
    return list(expanded)
```

**说明**：这不是向量搜索，是规则式语义映射。维护成本低，不会引入 embedding 依赖。后续如果数据量大且需要真正语义搜索，可以再加轻量 embedding（如 sentence-transformers 的小模型）作为可选维度，不替代现有 BFS。

---

## Phase 6: 规模化 (预计 3-4 天)

**目标**：支撑 10K-100K 卡片级别。

### 6.1 热冷分离

```python
# card_store.py 改造

class CardStore:
    def __init__(self, ...):
        ...
        self._hot_cache: Dict[str, Card] = {}      # Tier 0+1, 全量
        self._cold_index: Dict[str, int] = {}       # Tier 2, card_id → JSONL 字节偏移
        self._max_hot = 2000                        # 热缓存上限

    def load_all(self):
        """启动时只加载热卡片，冷卡片只建偏移索引"""
        if not self._cards_jsonl.exists():
            return 0
        loaded = 0
        with open(self._cards_jsonl, 'r', encoding='utf-8') as f:
            while True:
                offset = f.tell()
                line = f.readline()
                if not line:
                    break
                try:
                    d = json.loads(line)
                    card = dict_to_card(d)
                    if card.tier >= 0:
                        if card.tier <= 1:
                            self._hot_cache[card.id] = card
                        else:  # Tier 2
                            self._cold_index[card.id] = offset
                        loaded += 1
                except Exception:
                    pass
        return loaded

    def get_card(self, card_id: str) -> Optional[Card]:
        if card_id in self._hot_cache:
            return self._hot_cache[card_id]
        if card_id in self._cold_index:
            # 懒加载: 从 JSONL 读一行
            return self._load_cold_card(card_id)
        return None

    def _load_cold_card(self, card_id: str) -> Optional[Card]:
        offset = self._cold_index[card_id]
        with open(self._cards_jsonl, 'r', encoding='utf-8') as f:
            f.seek(offset)
            line = f.readline()
            try:
                return dict_to_card(json.loads(line))
            except Exception:
                return None
```

### 6.2 JSONL 压缩 (Compaction)

```python
# card_store.py 新增

def compact(self):
    """
    定期压缩 JSONL:
    - 移除软删除 (tier=-1) 的卡片
    - 重写为紧凑格式
    """
    tmp_path = self._cards_jsonl.with_suffix('.jsonl.compact')
    kept = 0
    with open(self._cards_jsonl, 'r', encoding='utf-8') as fin:
        with open(tmp_path, 'w', encoding='utf-8') as fout:
            for line in fin:
                try:
                    d = json.loads(line)
                    if d.get("tier", 0) < 0:
                        continue
                    fout.write(line)
                    kept += 1
                except Exception:
                    continue

    # 原子替换
    old_path = self._cards_jsonl.with_suffix('.jsonl.old')
    self._cards_jsonl.rename(old_path)
    tmp_path.rename(self._cards_jsonl)
    old_path.unlink()

    print(f"[CardStore] Compaction: {kept} cards kept")
    return kept
```

### 6.3 图边剪枝

```python
# card_store.py 新增

def prune_edges(self, min_weight: float = 0.4):
    """
    剪除弱边: 权重低于阈值的边删除
    控制图密度，避免 BFS 爆炸
    """
    pruned = 0
    for cid, links in self._graph.items():
        weak = [nid for nid, w in links.items() if w < min_weight]
        for nid in weak:
            del links[nid]
            # 删反向边
            if nid in self._graph and cid in self._graph[nid]:
                del self._graph[nid][cid]
            pruned += 1
    self._save_graph()
    print(f"[CardStore] 剪枝: {pruned} 条弱边删除")
```

---

## 执行顺序与依赖关系

```
Phase 1 (地基) ──→ Phase 2 (半自动) ──→ Phase 3 (语义压缩)
                                           │
                                           ▼
                                      Phase 4 (地形) ──→ Phase 5 (高级检索)
                                           │
                                           ▼
                                      Phase 6 (规模化)
```

- **Phase 1 必须最先做**：图退化修复和性能优化是所有后续阶段的前提
- **Phase 2 可以与 Phase 1 并行**：质量门和审核 API 相对独立
- **Phase 3 依赖 Phase 1.2**：只有卡片质量稳定了，语义压缩才有意义（垃圾进垃圾出）
- **Phase 4 依赖 Phase 1.1**：图社区检测需要健康的图结构
- **Phase 5 依赖 Phase 4**：多维度检索需要社区和聚类信息
- **Phase 6 最后做**：在功能稳定后再优化规模

---

## 预期数据指标

| 指标 | 当前 | Phase 1 | Phase 3 | Phase 6 |
|------|------|---------|---------|---------|
| 图平均度 | ~10 (12卡128边) | ~3-5 | ~3-5 | ~3-5 |
| 建卡耗时 | ~3s (LLM) | ~3s (含质量检查) | ~3s | ~3s |
| 检索耗时 | <1ms (12卡) | <1ms | <5ms | <10ms (100K卡) |
| 启动耗时 | <100ms | <100ms | <200ms | <1s (100K卡) |
| 内存占用 | ~2MB | ~2MB | ~3MB | ~50MB (100K卡) |
| 卡片通过率 | 100% | ~60% (质量过滤后) | ~60% | ~60% |
| 孤立卡片比例 | 0% (全互连) | ~15-20% | ~15% | ~10% |
