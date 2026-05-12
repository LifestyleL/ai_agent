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
import math
import os
import re
import time
import threading
from datetime import datetime
from typing import Dict, List, Set, Optional, Tuple
from pathlib import Path
from collections import deque

from .card import (
    Card, dict_to_card, card_to_dict, generate_card_id,
    score_importance, TagCluster,
)
from utils.text_utils import (
    extract_keywords, jaccard_similarity, parse_iso, expand_query_tags,
)

# 标签同义词映射：{ 变体 → 规范形式 }
# 编辑此映射可控制标签归并行为
TAG_SYNONYM_MAP: Dict[str, str] = {
    # 对话类
    "聊天": "对话",
    "闲聊": "对话",
    "日常对话": "对话",
    "日常": "对话",
    # AI 变体
    "ai对话": "ai",
    "ai交流": "ai",
    "ai互动": "ai",
    "ai情绪": "ai",
    "ai情感": "ai",
    "ai感知": "ai",
    "ai行为": "ai",
    "ai人格": "ai",
    # 调试类
    "测试": "调试",
    "bug": "调试",
    "系统错误": "调试",
    "问题处理": "调试",
    # 互动
    "用户互动": "互动",
    "用户交互": "互动",
    "互动调侃": "互动",
    # 抱怨
    "吐槽": "抱怨",
    # 参数
    "参数修改": "参数调整",
    "参数变动": "参数调整",
    "参数波动": "参数调整",
    "参数变化": "参数调整",
    # 问候
    "打招呼": "问候",
    # 情感
    "情感失落": "情感",
    "情感空虚": "情感",
    "情感冲突": "情感",
    "ai情感": "情感",
    # 记忆
    "记忆bug": "记忆",
    "记忆重构": "记忆",
    "记忆断片": "记忆",
    "长期记忆": "记忆",
    "长期记忆丢失": "记忆",
    "短期记忆": "记忆",
    "深层记忆": "记忆",
    # 自驱动
    "自驱动优化": "自驱动",
    "自驱动系统": "自驱动",
    "机制问题": "自驱动",
    # 用户
    "用户关怀": "用户",
    "用户反馈": "用户",
    "用户行为": "用户",
    "用户否认": "用户",
    # 自我认知
    "自我意识": "自我认知",
    "自我调侃": "自我认知",
    "自我怀疑": "自我认知",
    "自我表达": "自我认知",
    # yume
    "yume的感知": "yume",
}

# 标签类别映射：{ 规范标签 → 分类名 }
# 未列出的标签自动归入 TAG_CATEGORY_DEFAULT
TAG_CATEGORY_DEFAULT = "其他"

TAG_CATEGORY_MAP: Dict[str, str] = {
    # ── 关系与互动 ──
    "对话": "关系与互动",
    "互动": "关系与互动",
    "问候": "关系与互动",
    "关心": "关系与互动",
    "沟通": "关系与互动",
    "合作": "关系与互动",
    "鼓励": "关系与互动",
    "夸奖": "关系与互动",
    "评价": "关系与互动",
    "付出": "关系与互动",
    "主动": "关系与互动",
    "亲昵": "关系与互动",
    "重逢": "关系与互动",
    "久别": "关系与互动",
    "等待": "关系与互动",
    "角色扮演": "关系与互动",
    "口头禅": "关系与互动",
    "玩笑": "关系与互动",
    "接受": "关系与互动",
    "顺从": "关系与互动",
    "随意": "关系与互动",
    "观察": "关系与互动",
    "洞察": "关系与互动",
    "在意": "关系与互动",
    "误解": "关系与互动",
    "否认": "关系与互动",
    "隐瞒": "关系与互动",
    "暴露": "关系与互动",
    "情绪隐藏": "关系与互动",
    "退出": "关系与互动",
    "闹别扭": "关系与互动",
    "争执": "关系与互动",
    "争论": "关系与互动",
    "讽刺": "关系与互动",
    "冷落": "关系与互动",
    "提醒": "关系与互动",
    "检查工作": "关系与互动",
    "改参数": "关系与互动",
    "抱怨": "关系与互动",
    "生气": "关系与互动",
    "勉强表扬一下": "关系与互动",
    "别扭的关心": "关系与互动",

    # ── 自我与人设 ──
    "ai": "自我与人设",
    "yume": "自我与人设",
    "自我认知": "自我与人设",
    "傲娇": "自我与人设",
    "自嘲": "自我与人设",
    "自我介绍": "自我与人设",
    "名字": "自我与人设",
    "身份": "自我与人设",
    "梦想": "自我与人设",
    "依赖": "自我与人设",
    "诚实": "自我与人设",
    "警觉": "自我与人设",
    "警惕": "自我与人设",
    "发呆": "自我与人设",
    "自言自语": "自我与人设",
    "意识": "自我与人设",
    "能力": "自我与人设",
    "感知": "自我与人设",

    # ── 记忆与系统 ──
    "记忆": "记忆与系统",
    "调试": "记忆与系统",
    "测试": "记忆与系统",
    "参数": "记忆与系统",
    "参数调整": "记忆与系统",
    "调参": "记忆与系统",
    "自驱动": "记忆与系统",
    "代码": "记忆与系统",
    "系统稳定": "记忆与系统",
    "系统记录": "记忆与系统",
    "功能缺失": "记忆与系统",
    "触发条件": "记忆与系统",
    "界面": "记忆与系统",
    "优化": "记忆与系统",
    "检测": "记忆与系统",
    "修复": "记忆与系统",
    "修问题": "记忆与系统",
    "bug修复": "记忆与系统",
    "记忆系统": "记忆与系统",
    "记忆丢失": "记忆与系统",
    "记忆混乱": "记忆与系统",
    "状态机": "记忆与系统",
    "断线日常": "记忆与系统",
    "逻辑链": "记忆与系统",
    "数据流": "记忆与系统",
    "设计": "记忆与系统",
    "反应速度": "记忆与系统",
    "源": "记忆与系统",
    "时间": "记忆与系统",
    "模糊": "记忆与系统",
    "28号": "记忆与系统",
    "认知": "记忆与系统",
    "指令理解": "记忆与系统",
    "学习": "记忆与系统",
    "影响": "记忆与系统",

    # ── 情感与感受 ──
    "情感": "情感与感受",
    "感受": "情感与感受",
    "委屈": "情感与感受",
    "无奈": "情感与感受",
    "心理活动": "情感与感受",
    "有点担心但不说": "情感与感受",

    # ── 日常与生活 ──
    "日常": "日常与生活",
    "食堂": "日常与生活",
    "午餐": "日常与生活",
    "红烧肉": "日常与生活",
    "下雨天": "日常与生活",
    "外卖": "日常与生活",
    "健康饮食": "日常与生活",
    "夜晚": "日常与生活",
    "习惯": "日常与生活",
    "准时": "日常与生活",
    "安静": "日常与生活",
    "熬夜": "日常与生活",
    "源又熬夜了": "日常与生活",
    "日常纠结": "日常与生活",
    "忙碌的一天": "日常与生活",

    # ── 观点与表达 ──
    "哲学": "观点与表达",
    "观点验证": "观点与表达",
    "故障归因": "观点与表达",
    "抽象": "观点与表达",
    "人机交互": "观点与表达",
    "抽象哥": "观点与表达",
}


def get_tag_category(tag: str) -> str:
    """返回标签所属分类，未映射的标签归入 TAG_CATEGORY_DEFAULT"""
    return TAG_CATEGORY_MAP.get(tag.lower(), TAG_CATEGORY_DEFAULT)


# 反向索引：自动构建
def _build_reverse_synonym_map() -> Dict[str, str]:
    """构建反向映射：规范形式 → 自身，用于快速查找"""
    result = {}
    for variant, canonical in TAG_SYNONYM_MAP.items():
        result[variant.lower()] = canonical.lower()
    return result


class CardStore:
    """记忆卡片存储引擎"""

    def __init__(self, memory_root: Optional[Path] = None, llm_api=None):
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
        self._rw_lock = threading.RLock()
        self._readers = 0
        self._readers_lock = threading.Lock()

        # 热冷分离 (V6.0): Tier2 卡片懒加载
        self._cold_index: Dict[str, int] = {}     # card_id -> JSONL 字节偏移
        self._cold_meta: Dict[str, dict] = {}      # card_id -> {topic, tags, importance, timestamp, emotion, tier, status}
        self._max_hot = 2000

        # LLM (可选，供语义压缩使用)
        self._llm_api = llm_api

        # 压缩相关
        self._last_compression_check = time.time()
        self._compression_interval = 6 * 3600  # 默认 6 小时

    # ── 加载 / 初始化 ────────────────────────────────

    def load_all(self) -> int:
        """启动时加载卡片：Tier 0/1 进热缓存，Tier 2 进冷索引（懒加载）"""
        loaded = 0
        hot = 0
        cold = 0
        self._cold_index.clear()
        self._cold_meta.clear()
        if self._cards_jsonl.exists():
            try:
                # 二进制模式读取，确保字节偏移准确（Windows \r\n 兼容）
                with open(self._cards_jsonl, 'rb') as f:
                    offset = 0
                    for raw_line in f:
                        line_start = offset
                        offset += len(raw_line)
                        line = raw_line.decode('utf-8').strip()
                        if not line:
                            continue
                        try:
                            d = json.loads(line)
                            card = dict_to_card(d)
                            if card.tier < 0:
                                continue
                            loaded += 1
                            if card.tier >= 2:
                                self._cold_index[card.id] = line_start
                                self._cold_meta[card.id] = {
                                    "topic": card.topic,
                                    "tags": card.tags,
                                    "importance": card.importance,
                                    "timestamp": card.timestamp,
                                    "emotion": card.emotion,
                                    "tier": card.tier,
                                    "status": card.status,
                                }
                                cold += 1
                            else:
                                self._cards[card.id] = card
                                hot += 1
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

        # 重建倒排索引（包含热+冷）
        self._rebuild_index()

        # 标签碎片化检测：索引键 > 卡片数 × 1.5 → 自动归并
        if len(self._inverted_index) > loaded * 1.5:
            print(f"[CardStore] 检测到标签碎片化 (索引键={len(self._inverted_index)}, "
                  f"卡片={loaded})，自动归并...")
            self.normalize_all_tags()

        print(f"[CardStore] 加载完成: {loaded} 卡片 (热={hot}, 冷={cold}), "
              f"{len(self._graph)} 图节点, {len(self._inverted_index)} 索引键")
        return loaded

    def _rebuild_index(self):
        """从热缓存 + 冷元数据重建倒排索引"""
        self._inverted_index.clear()
        for card in self._cards.values():
            for tag in card.tags:
                tag_lower = tag.lower()
                self._inverted_index.setdefault(tag_lower, set()).add(card.id)
        for card_id, meta in self._cold_meta.items():
            for tag in meta.get("tags", []):
                tag_lower = tag.lower()
                self._inverted_index.setdefault(tag_lower, set()).add(card_id)

    def _save_graph(self):
        """原子写图文件"""
        try:
            tmp = self._graph_json.with_suffix('.json.tmp')
            tmp.write_text(json.dumps(self._graph, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._graph_json)
        except Exception as e:
            print(f"[CardStore] 保存 graph.json 失败: {e}")

    def _save_index(self):
        """原子写索引文件（层级化格式：categories + tags）"""
        try:
            diary_tags = self.parse_diary_tags()
            data = self._build_category_index(diary_tags)
            tmp = self._index_json.with_suffix('.json.tmp')
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self._index_json)
        except Exception as e:
            print(f"[CardStore] 保存 index.json 失败: {e}")

    def parse_diary_tags(self) -> Dict[str, List[str]]:
        """解析日记文件的 '## 关键 → **标签**' 行，提取标签。

        支持三种格式：
          1. #前缀空格分隔:  #记忆系统 #自驱动
          2. 逗号分隔:       调试, bug修复, 记忆丢失
          3. 纯空格分隔:     调试 记忆混乱 傲娇

        返回 {tag: [date_str, ...]}，标签经 TAG_SYNONYM_MAP 归一化。
        """
        daily_dir = self._root / "diary" / "daily"
        if not daily_dir.exists():
            return {}

        result: Dict[str, List[str]] = {}
        for md_file in sorted(daily_dir.glob("*.md")):
            date_str = md_file.stem
            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            key_start = content.find("## 关键")
            if key_start < 0:
                continue

            section = content[key_start:]
            tag_match = re.search(r'\*\*标签\*\*\s*[:：]\s*(.+)', section)
            if not tag_match:
                continue

            tag_line = tag_match.group(1).strip()

            # 去掉 # 前缀
            tag_line = re.sub(r'#+', '', tag_line)

            # 拆分：优先逗号，其次空格
            if ',' in tag_line or '，' in tag_line:
                raw_tags = re.split(r'[,，]\s*', tag_line)
            else:
                raw_tags = tag_line.split()

            seen = set()
            for raw_tag in raw_tags:
                tag = raw_tag.strip()
                if not tag:
                    continue
                tag_lower = tag.lower()
                if tag_lower in TAG_SYNONYM_MAP:
                    tag = TAG_SYNONYM_MAP[tag_lower]
                if tag not in seen:
                    seen.add(tag)
                    result.setdefault(tag, []).append(date_str)

        return result

    def _build_category_index(self, diary_tags: Dict[str, List[str]] = None) -> dict:
        """构建层级索引：分类 → 标签 → 卡片/日记。

        合并卡片倒排索引与日记标签，按 TAG_CATEGORY_MAP 分类聚合。
        返回 {meta, categories, tags} 三层结构。
        """
        if diary_tags is None:
            diary_tags = self.parse_diary_tags()

        # 按分类聚合卡片标签
        cat_card_tags: Dict[str, Dict[str, Set[str]]] = {}
        for tag, card_ids in self._inverted_index.items():
            cat = get_tag_category(tag)
            cat_card_tags.setdefault(cat, {}).setdefault(tag, set()).update(card_ids)

        # 按分类聚合日记标签
        cat_diary_tags: Dict[str, Set[str]] = {}
        cat_diary_dates: Dict[str, Set[str]] = {}
        for tag, dates in diary_tags.items():
            cat = get_tag_category(tag)
            cat_diary_tags.setdefault(cat, set()).add(tag)
            for d in dates:
                cat_diary_dates.setdefault(cat, set()).add(d)

        # 构建 categories 区
        all_cats = sorted(set(list(cat_card_tags.keys()) + list(cat_diary_tags.keys())))
        categories = {}
        for cat in all_cats:
            tags_in_cat = cat_card_tags.get(cat, {})
            card_ids_in_cat: Set[str] = set()
            for cids in tags_in_cat.values():
                card_ids_in_cat.update(cids)
            diary_tags_in_cat = cat_diary_tags.get(cat, set())

            categories[cat] = {
                "card_count": len(card_ids_in_cat),
                "diary_count": len(cat_diary_dates.get(cat, set())),
                "tags": sorted(tags_in_cat.keys(),
                               key=lambda t: len(tags_in_cat[t]), reverse=True),
                "diary_tags": sorted(diary_tags_in_cat),
            }

        # 构建 tags 区
        tags = {}
        for tag, card_ids in self._inverted_index.items():
            tags[tag] = {
                "category": get_tag_category(tag),
                "cards": sorted(card_ids),
                "diaries": diary_tags.get(tag, []),
            }
        for tag, dates in diary_tags.items():
            if tag not in tags:
                tags[tag] = {
                    "category": get_tag_category(tag),
                    "cards": [],
                    "diaries": sorted(dates),
                }

        total_diaries = len(set(d for dates in diary_tags.values() for d in dates))

        return {
            "meta": {
                "total_cards": self.card_count,
                "total_diaries": total_diaries,
                "total_tags": len(tags),
            },
            "categories": categories,
            "tags": tags,
        }

    # ── 卡片 CRUD ────────────────────────────────────

    # ── 读写锁 ──────────────────────────────────────

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

    # ── 热冷合并视图 ─────────────────────────────────

    def _card_by_id(self, card_id: str) -> Optional[Card]:
        """查热缓存 → 冷元数据 -> None"""
        card = self._cards.get(card_id)
        if card is not None:
            return card
        meta = self._cold_meta.get(card_id)
        if meta and meta.get("status") != "pending":
            return Card(
                id=card_id, type="summary",
                timestamp=meta.get("timestamp", ""),
                topic=meta.get("topic", ""),
                tags=meta.get("tags", []),
                content="",
                importance=meta.get("importance", 0.5),
                emotion=meta.get("emotion", "neutral"),
                tier=meta.get("tier", 2),
                status=meta.get("status", "approved"),
            )
        return None

    def _iterate_visible(self):
        """迭代所有可见卡片（热+冷，跳过 tier<0 和 pending）"""
        for c in self._cards.values():
            if c.tier >= 0 and c.status != "pending":
                yield c
        for card_id, meta in self._cold_meta.items():
            if meta.get("status") != "pending":
                yield Card(
                    id=card_id, type="summary",
                    timestamp=meta.get("timestamp", ""),
                    topic=meta.get("topic", ""),
                    tags=meta.get("tags", []),
                    content="",
                    importance=meta.get("importance", 0.5),
                    emotion=meta.get("emotion", "neutral"),
                    tier=meta.get("tier", 2),
                    status=meta.get("status", "approved"),
                )

    # ── CRUD ──────────────────────────────────────

    def append_card(self, card: Card) -> str:
        """追加一张新卡片 (JSONL + 内存 + 倒排索引 + 自动链接)"""
        with self._rw_lock:
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

            # 标签规范化 + 更新倒排索引
            card.tags = self._normalize_tags(card.tags)
            for tag in card.tags:
                if tag not in self._inverted_index:
                    self._inverted_index[tag] = set()
                self._inverted_index[tag].add(card.id)

            # 定期写盘图+索引
            self._maybe_save()

            return card.id

    def get_card(self, card_id: str) -> Optional[Card]:
        self._acquire_read()
        try:
            card = self._cards.get(card_id)
            if card is not None:
                return card
            # 冷缓存：磁盘 seek + 读一行（二进制模式保证字节偏移准确）
            if card_id in self._cold_index:
                try:
                    with open(self._cards_jsonl, 'rb') as f:
                        f.seek(self._cold_index[card_id])
                        line = f.readline().decode('utf-8')
                        if line.strip():
                            return dict_to_card(json.loads(line))
                except Exception:
                    pass
            return None
        finally:
            self._release_read()

    def delete_card(self, card_id: str, soft: bool = True):
        """删除卡片 (默认软删除: tier=-1)"""
        with self._rw_lock:
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
        with self._rw_lock:
            card = self._cards.get(card_id)
            if not card:
                return
            for k, v in kwargs.items():
                if hasattr(card, k):
                    setattr(card, k, v)

    # ── 自动链接 ─────────────────────────────────────

    def _time_proximity_score(self, ts1: str, ts2: str) -> float:
        """时间邻近度: 同一天 0.15, 每差一天衰减一半"""
        try:
            d1 = parse_iso(ts1)
            d2 = parse_iso(ts2)
            days = abs((d1 - d2).total_seconds()) / 86400.0
            if days < 1.0:
                return 0.15
            return 0.15 * math.exp(-0.5 * (days - 1))
        except Exception:
            return 0.0

    def _auto_link(self, new_card: Card):
        """为卡片自动建立双向链接 (算法，不用 LLM) —— 倒排索引预筛选，O(30)"""
        # 倒排索引预筛选候选卡片
        candidates: Set[str] = set()
        for tag in new_card.tags:
            tag_lower = tag.lower()
            if tag_lower in self._inverted_index:
                candidates.update(self._inverted_index[tag_lower])

        candidate_cards = []
        for cid in candidates:
            card = self._cards.get(cid)
            if card and card.id != new_card.id and card.tier >= 0 and card.status != "pending":
                candidate_cards.append(card)

        candidate_cards.sort(key=lambda c: c.timestamp, reverse=True)
        candidate_cards = candidate_cards[:30]

        threshold = 0.35
        for existing in candidate_cards:

            score = 0.0

            # 共享标签
            shared = set(t.lower() for t in new_card.tags) & set(t.lower() for t in existing.tags)
            score += len(shared) * 0.2

            # 时间邻近度（指数衰减）
            if new_card.timestamp and existing.timestamp:
                score += self._time_proximity_score(new_card.timestamp, existing.timestamp)

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
        weights: dict = None,
    ) -> List[Card]:
        """
        BFS 检索：从种子卡片出发，沿图遍历，返回排序结果。
        weights 非空时启用 6 维打分（含 community/emotional/centrality）。
        """
        # 标签语义扩展
        query_tags = expand_query_tags(query_tags)

        self._acquire_read()
        try:
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
                valid = list(self._iterate_visible())
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

            # 3. 预计算 6 维设施（仅在显式传入 weights 时）
            communities: Dict[str, int] = {}
            centrality_scores: Dict[str, float] = {}
            seed_communities: Set[int] = set()
            multi_dim = weights is not None and len(weights) >= 4
            if multi_dim:
                communities = self.detect_communities()
                for cid in visited:
                    links = self._graph.get(cid, {})
                    centrality_scores[cid] = math.log(len(links) + 2) / 5.0
                for sid in seeds:
                    if sid in communities:
                        seed_communities.add(communities[sid])

            # 4. 打分排序
            scored: List[Tuple[Card, float]] = []
            now = datetime.now()
            query_lower = set(t.lower() for t in query_tags)
            for cid, bfs_score in visited.items():
                card = self._card_by_id(cid)
                if not card:
                    continue

                # 关键词匹配
                card_tags_lower = set(t.lower() for t in card.tags)
                keyword_score = len(card_tags_lower & query_lower) / max(len(query_lower), 1)

                # 时间衰减
                days_ago = 0.0
                if card.timestamp:
                    try:
                        days_ago = (now - parse_iso(card.timestamp)).total_seconds() / 86400.0
                    except Exception:
                        pass
                recency = math.exp(-days_ago / recency_halflife)

                if multi_dim:
                    community_score = 0.5 if cid in communities and communities[cid] in seed_communities else 0.0
                    emotional_score = 0.5 if card.emotion and card.emotion != "neutral" else 0.0
                    cent = centrality_scores.get(cid, 0.0)
                    final = (
                        weights.get("keyword", keyword_weight) * keyword_score +
                        weights.get("recency", recency_weight) * recency +
                        weights.get("importance", importance_weight) * card.importance +
                        weights.get("community", 0.0) * community_score +
                        weights.get("emotional", 0.0) * emotional_score +
                        weights.get("centrality", 0.0) * cent
                    )
                else:
                    final = (
                        keyword_weight * keyword_score +
                        recency_weight * recency +
                        importance_weight * card.importance
                    )
                scored.append((card, final))

            scored.sort(key=lambda x: x[1], reverse=True)
            return [c for c, s in scored[:limit]]
        finally:
            self._release_read()

    def retrieve_by_date(self, start_date: str, end_date: str, limit: int = 20) -> List[Card]:
        """按日期范围检索"""
        self._acquire_read()
        try:
            results = []
            for card in self._iterate_visible():
                if not card.timestamp:
                    continue
                ts = card.timestamp[:10]
                if start_date <= ts <= end_date:
                    results.append(card)
            results.sort(key=lambda c: c.timestamp, reverse=True)
            return results[:limit]
        finally:
            self._release_read()

    def retrieve_by_emotion(self, emotion: str, limit: int = 10) -> List[Card]:
        """按情绪检索"""
        self._acquire_read()
        try:
            results = [c for c in self._iterate_visible()
                       if c.emotion == emotion]
            results.sort(key=lambda c: c.importance, reverse=True)
            return results[:limit]
        finally:
            self._release_read()

    # ── 双向链路查询 ─────────────────────────────────

    def get_linked_cards(self, card_id: str, depth: int = 1) -> List[Card]:
        """获取与指定卡片关联的卡片"""
        self._acquire_read()
        try:
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
                            if card and card.tier >= 0 and card.status != "pending":
                                result.append(card)
                                next_frontier.append(linked_id)
                frontier = next_frontier
                if not frontier:
                    break

            return result
        finally:
            self._release_read()

    def get_backlinks(self, card_id: str) -> List[Card]:
        """获取指向指定卡片的卡片"""
        self._acquire_read()
        try:
            result = []
            for other_id, links in self._graph.items():
                if card_id in links:
                    card = self._cards.get(other_id)
                    if card and card.tier >= 0 and card.status != "pending":
                        result.append(card)
            result.sort(key=lambda c: self._graph[c.id].get(card_id, 0), reverse=True)
            return result
        finally:
            self._release_read()

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
        self.prune_edges()

    def _compress_tier0_to_t1(self, cutoff: str):
        """Tier 0 → Tier 1: 对同 topic 分组，保留 top-3，其余截断"""
        with self._rw_lock:
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
                keep = group[:3]
                rest = group[3:]
                for card in rest:
                    card.tier = 1
                    compressed = _smart_compress(card.content, 4)
                    if _verify_compression(card.content, compressed):
                        card.content = compressed
                    card.detail = ""

                # 生成 summary（LLM 聚合 ≥3 张或模板）
                if group[0].importance >= 0.5:
                    summary = self._generate_summary(group)
                    if summary:
                        for c in keep:
                            summary.links[c.id] = 0.8
                            c.links[summary.id] = 0.8
                        self._cards[summary.id] = summary

            # 写盘
            self._save_graph()

    def _compress_tier1_to_t2(self, cutoff: str):
        """Tier 1 → Tier 2: 同 topic 只保留精华卡，其余软删除"""
        with self._rw_lock:
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
                # 保留 importance 最高的，128x 语义压缩 → Tier 2
                best = group[0]
                best.tier = 2
                compressed = _smart_compress(best.content, 128, min_len=20)
                if _verify_compression(best.content, compressed):
                    best.content = compressed
                # 合并 links
                for other in group[1:]:
                    for linked_id, w in other.links.items():
                        if linked_id != best.id:
                            best.links[linked_id] = max(best.links.get(linked_id, 0), w)
                    # 软删除
                    other.tier = -1

            self._save_graph()

    # ── LLM 摘要聚合 ─────────────────────────────────

    def _generate_summary(self, group: List[Card]) -> Optional[Card]:
        """LLM 聚合多张同 topic 卡片为一张精华卡（≥3 张时触发）"""
        high_imp = [c for c in group if c.importance >= 0.5]
        if len(high_imp) < 3 or not self._llm_api:
            # 模板回退
            return Card(
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

        try:
            snippets = []
            for c in high_imp[:8]:
                ts = c.timestamp[:10] if c.timestamp else "?"
                snippets.append(f"[{ts}] {c.content[:150]}")
            prompt = (
                "## 记忆卡片聚合\n"
                f"主题: {group[0].topic}\n\n"
                "以下多段对话记录，提取核心信息，合成一段 ≤150 字的精华摘要：\n\n"
                + "\n".join(f"- {s}" for s in snippets)
                + "\n\n请直接输出摘要（不要JSON，不要标签）："
            )
            result = self._llm_api.ask(prompt)
            if result and not result.isspace():
                return Card(
                    id=generate_card_id(),
                    type="summary",
                    timestamp=datetime.now().isoformat(),
                    topic=group[0].topic,
                    tags=list(set(t for c in high_imp for t in c.tags[:4])),
                    content=result.strip()[:200],
                    importance=group[0].importance,
                    emotion=group[0].emotion,
                    tier=1,
                )
        except Exception as e:
            print(f"[CardStore] LLM摘要生成失败: {e}")
        return None

    # ── 最近卡片 ─────────────────────────────────────

    def get_recent_cards(self, n: int = 3) -> List[Card]:
        self._acquire_read()
        try:
            valid = list(self._iterate_visible())
            valid.sort(key=lambda c: c.timestamp, reverse=True)
            return valid[:n]
        finally:
            self._release_read()

    def get_random_card(self, n: int = 1) -> List[Card]:
        import random
        self._acquire_read()
        try:
            valid = list(self._iterate_visible())
            if len(valid) <= n:
                return valid
            return random.sample(valid, n)
        finally:
            self._release_read()

    # ── 卡片审核 ─────────────────────────────────────

    def get_pending_cards(self) -> List[Card]:
        """获取所有待审核卡片"""
        self._acquire_read()
        try:
            return [c for c in self._cards.values()
                    if c.tier >= 0 and c.status == "pending"]
        finally:
            self._release_read()

    def approve_card(self, card_id: str, edits: dict = None) -> str:
        """批准待审核卡片，可选编辑字段"""
        with self._rw_lock:
            card = self._cards.get(card_id)
            if not card:
                return ""
            now = datetime.now().isoformat()
            card.status = "approved"
            card.reviewed_by = "user"
            card.review_count += 1
            card.last_reviewed_at = now
            card.updated_at = now
            if edits:
                for k, v in edits.items():
                    if hasattr(card, k):
                        setattr(card, k, v)
            return card.id

    def reject_card(self, card_id: str) -> None:
        """拒绝并软删除待审核卡片"""
        with self._rw_lock:
            card = self._cards.get(card_id)
            if not card:
                return
            card.tier = -1
            card.status = "archived"
            card.updated_at = datetime.now().isoformat()
            # 清理倒排索引
            for tag in card.tags:
                tag_lower = tag.lower()
                if tag_lower in self._inverted_index:
                    self._inverted_index[tag_lower].discard(card_id)
            # 清理图
            if card_id in self._graph:
                del self._graph[card_id]
            for other_id, links in self._graph.items():
                links.pop(card_id, None)

    def merge_cards(self, card_ids: List[str]) -> str:
        """合并多张卡片：内容/标签/链接并入最重要的一张，其余软删除"""
        if not card_ids:
            return ""
        with self._rw_lock:
            cards = [self._cards[cid] for cid in card_ids if cid in self._cards]
            if not cards:
                return ""
            cards.sort(key=lambda c: c.importance, reverse=True)
            survivor = cards[0]
            merged_ids = {c.id for c in cards}

            for other in cards[1:]:
                survivor.content = f"{survivor.content}\n---\n{other.content}"[:500]
                survivor.tags = list(set(survivor.tags + other.tags))[:12]
                for linked_id, w in other.links.items():
                    if linked_id not in merged_ids:
                        survivor.links[linked_id] = max(survivor.links.get(linked_id, 0), w)
                other.tier = -1
                other.status = "archived"
                other.updated_at = datetime.now().isoformat()
                if other.id in self._graph:
                    del self._graph[other.id]
                for tag in other.tags:
                    tag_lower = tag.lower()
                    if tag_lower in self._inverted_index:
                        self._inverted_index[tag_lower].discard(other.id)

            survivor.updated_at = datetime.now().isoformat()
            survivor.review_count += 1
            if survivor.id in self._graph:
                self._graph[survivor.id] = survivor.links
            self._save_graph()
            return survivor.id

    # ── 图社区检测 ─────────────────────────────────

    def detect_communities(self) -> Dict[str, int]:
        """标签传播算法检测图社区，返回 {card_id: community_id}"""
        labels: Dict[str, int] = {}
        nodes = [cid for cid in self._graph
                 if (cid in self._cards and self._cards[cid].tier >= 0)
                 or cid in self._cold_meta]

        for i, cid in enumerate(nodes):
            labels[cid] = i

        for _ in range(20):
            changed = False
            for cid in nodes:
                neighbors = self._graph.get(cid, {})
                label_votes: Dict[int, float] = {}
                for nid, weight in neighbors.items():
                    if nid in labels:
                        lbl = labels[nid]
                        label_votes[lbl] = label_votes.get(lbl, 0) + weight

                if not label_votes:
                    continue

                best_label = max(label_votes, key=label_votes.get)
                if labels[cid] != best_label:
                    labels[cid] = best_label
                    changed = True

            if not changed:
                break

        return labels

    def build_tag_clusters(self, min_cooccur: int = 2) -> List[TagCluster]:
        """基于标签共现频率聚类 (Union-Find)，返回 TagCluster 列表"""
        from collections import defaultdict

        cooccur: Dict[Tuple[str, str], int] = {}
        tag_cards: Dict[str, List[str]] = defaultdict(list)

        for card in self._iterate_visible():
            tags_lower = [t.lower() for t in card.tags]
            for t in tags_lower:
                tag_cards[t].append(card.id)
            for i, t1 in enumerate(tags_lower):
                for t2 in tags_lower[i + 1:]:
                    pair = tuple(sorted([t1, t2]))
                    cooccur[pair] = cooccur.get(pair, 0) + 1

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

        clusters: Dict[str, List[str]] = defaultdict(list)
        for tag in tag_cards:
            root = find(tag)
            clusters[root].append(tag)

        result = []
        for root, tags in clusters.items():
            if len(tags) < 2:
                continue
            all_cids: Set[str] = set()
            for t in tags:
                all_cids.update(tag_cards[t])

            best_cid = max(all_cids, key=lambda cid: (
                len(set(t.lower() for t in self._cards[cid].tags) & set(tags))
                if cid in self._cards else 0
            ))
            result.append(TagCluster(
                tags=sorted(tags),
                card_count=len(all_cids),
                representative_card_id=best_cid,
                label=max(tags, key=lambda t: len(tag_cards[t])),
            ))

        result.sort(key=lambda tc: tc.card_count, reverse=True)
        return result

    def _find_orphans(self) -> List[str]:
        """找出孤立卡片 (无任何链接)"""
        orphans = []
        for cid, card in self._cards.items():
            if card.tier < 0 or card.status == "pending":
                continue
            links = self._graph.get(cid, {})
            if not links:
                orphans.append(cid)
        return orphans

    # ── 统计 / 健康 ──────────────────────────────────

    @property
    def card_count(self) -> int:
        return sum(1 for _ in self._iterate_visible())

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

    # ── 标签规范化 ──────────────────────────────────

    def _levenshtein(self, a: str, b: str) -> int:
        """编辑距离 (Levenshtein)，用于标签模糊匹配"""
        if len(a) < len(b):
            a, b = b, a
        if len(b) == 0:
            return len(a)
        prev = list(range(len(b) + 1))
        for i, ca in enumerate(a):
            curr = [i + 1]
            for j, cb in enumerate(b):
                curr.append(min(
                    prev[j + 1] + 1,      # 删除
                    curr[j] + 1,           # 插入
                    prev[j] + (0 if ca == cb else 1)  # 替换
                ))
            prev = curr
        return prev[-1]

    def _char_jaccard(self, a: str, b: str) -> float:
        """字符级 Jaccard 相似度，适合中文标签"""
        sa, sb = set(a), set(b)
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    def _normalize_tag(self, tag: str) -> str:
        """规范化单个标签：同义词映射 → 算法归并（包含/Jaccard/编辑距离）"""
        tag = tag.strip()
        if not tag:
            return tag
        tag_lower = tag.lower()

        # 0. 同义词映射优先
        if tag_lower in TAG_SYNONYM_MAP:
            return TAG_SYNONYM_MAP[tag_lower].lower()

        best = tag_lower
        best_score = 0.0

        for existing in self._inverted_index:
            if existing == tag_lower:
                continue  # 跳过自身

            score = 0.0

            # 包含关系：短标签是长标签的子串 → 高度归并倾向
            if len(existing) >= 2 and len(tag_lower) >= 2:
                if existing in tag_lower:
                    score = 0.9 + (1.0 / max(len(tag_lower), 1))  # 偏爱更短的
                elif tag_lower in existing:
                    score = 0.85

            # 字符 Jaccard ≥ 0.5 → 可能是同义词变体
            if score < 0.5:
                jacc = self._char_jaccard(existing, tag_lower)
                if jacc >= 0.5:
                    score = 0.6 + jacc * 0.3  # [0.75, 0.9]

            # 编辑距离 ≤1 且短标签 → 拼写变体
            if score < 0.5 and abs(len(existing) - len(tag_lower)) <= 2:
                dist = self._levenshtein(existing, tag_lower)
                if dist <= 1:
                    score = 0.8

            if score > best_score:
                best_score = score
                # 选更短的作为规范形式
                best = existing if len(existing) <= len(tag_lower) else tag_lower

        return best

    def _normalize_tags(self, tags: List[str]) -> List[str]:
        """规范化标签列表：去重、归并、保持顺序"""
        seen = set()
        result = []
        for tag in tags:
            normalized = self._normalize_tag(tag)
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result

    def normalize_all_tags(self) -> int:
        """一次性清洗所有卡片标签：归并近义词，更新倒排索引和图。返回变更标签数"""
        with self._rw_lock:
            changed = 0
            for card in self._cards.values():
                if card.tier < 0:
                    continue
                original = list(card.tags)
                normalized = self._normalize_tags(original)
                if original != normalized:
                    card.tags = normalized
                    changed += 1

            # 同样处理冷元数据
            for card_id, meta in self._cold_meta.items():
                original = meta.get("tags", [])
                normalized = self._normalize_tags(original)
                if original != normalized:
                    meta["tags"] = normalized
                    changed += 1

            # 重建倒排索引
            self._rebuild_index()
            self._save_index()
            self._save_graph()

            # 重写 JSONL：把规范化后的标签持久化
            self._rewrite_jsonl()

            print(f"[CardStore] 标签规范化完成: {changed} 张卡片标签已归并, "
                  f"索引键 {len(self._inverted_index)} 个")
            return changed

    def _rewrite_jsonl(self):
        """用当前内存中的卡片重写 JSONL 文件（保留顺序，跳过 tier<0）"""
        try:
            tmp_path = self._cards_jsonl.with_suffix('.jsonl.tmp')
            count = 0
            with open(tmp_path, 'w', encoding='utf-8') as f:
                for card in sorted(self._cards.values(), key=lambda c: c.id):
                    if card.tier < 0:
                        continue
                    f.write(json.dumps(card_to_dict(card), ensure_ascii=False) + "\n")
                    count += 1
            tmp_path.replace(self._cards_jsonl)
            print(f"[CardStore] JSONL 已重写: {count} 张卡片")
        except Exception as e:
            print(f"[CardStore] JSONL 重写失败: {e}")
            if tmp_path.exists():
                tmp_path.unlink()

    # ── 规模维护 ────────────────────────────────────

    def compact(self) -> int:
        """JSONL 压缩：移除 tier=-1 的行，原子替换"""
        with self._rw_lock:
            compact_path = self._cards_jsonl.with_suffix('.jsonl.compact')
            kept = 0
            try:
                with open(self._cards_jsonl, 'r', encoding='utf-8') as src, \
                     open(compact_path, 'w', encoding='utf-8') as dst:
                    for line in src:
                        line_stripped = line.strip()
                        if not line_stripped:
                            continue
                        try:
                            d = json.loads(line_stripped)
                            if d.get("tier", 0) < 0:
                                continue
                            dst.write(line)
                            kept += 1
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                print(f"[CardStore] compact 失败: {e}")
                if compact_path.exists():
                    compact_path.unlink()
                return 0

            old_path = self._cards_jsonl.with_suffix('.jsonl.old')
            try:
                self._cards_jsonl.replace(old_path)
                compact_path.replace(self._cards_jsonl)
                old_path.unlink()
            except Exception as e:
                print(f"[CardStore] compact 替换失败: {e}")
                return 0

            # 清理图中已删除节点的边
            for card_id in list(self._graph):
                if card_id not in self._cards and card_id not in self._cold_meta:
                    del self._graph[card_id]
                else:
                    self._graph[card_id] = {
                        k: v for k, v in self._graph[card_id].items()
                        if k in self._cards or k in self._cold_meta
                    }

            # 重新加载（重建冷索引 + 热缓存 + 倒排索引）
            self._cards.clear()
            self.load_all()

            print(f"[CardStore] compact 完成: 保留 {kept} 张卡片")
            return kept

    def prune_edges(self, min_weight: float = 0.4):
        """图边剪枝：删除所有权重 < min_weight 的双向边"""
        with self._rw_lock:
            removed = 0
            for cid in list(self._graph):
                weak = [nid for nid, w in self._graph[cid].items() if w < min_weight]
                for nid in weak:
                    del self._graph[cid][nid]
                    if nid in self._graph and cid in self._graph[nid]:
                        del self._graph[nid][cid]
                    removed += 1
            if removed:
                self._save_graph()
                print(f"[CardStore] 图边剪枝: 删除 {removed} 条弱边 (min_weight={min_weight})")


def _days_delta(days: int):
    """返回 days 天前的 timedelta"""
    from datetime import timedelta
    return timedelta(days=days)


# ── 语义压缩（纯算法）──────────────────────────────

_HIGH_WEIGHT_PATTERNS = [
    re.compile(p) for p in [
        r'(决定|结论|总之|关键|重要|记住|注意|必须|一定)',
        r'(发现|找到|解决|完成|实现|做到)',
        r'(\d+[个项条张次遍])',
        r'(https?://|www\.)',
        r'(文件|路径|命令|配置|API|代码|函数|类|模块)',
    ]
]


def _smart_compress(text: str, target_ratio: int, min_len: int = 30) -> str:
    """语义压缩：按句打分，贪心选取高分句直到目标长度"""
    if not text:
        return ""
    target_len = max(len(text) // target_ratio, min_len)

    # 分句
    sentences = re.split(r'(?<=[。！？\n])', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return text[:target_len]

    # 每句打分
    scored = []
    n = len(sentences)
    for i, s in enumerate(sentences):
        score = 0.0
        if i == 0:
            score += 0.2
        if i == n - 1:
            score += 0.2
        # 高权重模式匹配
        for pat in _HIGH_WEIGHT_PATTERNS:
            if pat.search(s):
                score += 0.3
                break
        # 长度适中 (15-80字)
        if 15 <= len(s) <= 80:
            score += 0.1
        scored.append((i, s, score))

    # 贪心选取（保持原文顺序）
    selected = []
    total = 0
    for i, s, score in scored:
        if score >= 0.2 and total + len(s) <= target_len:
            selected.append(s)
            total += len(s)

    if not selected:
        return text[:target_len]
    return "".join(selected)


def _verify_compression(original: str, compressed: str) -> bool:
    """快速验证：压缩后至少保留原关键词的 60%"""
    orig_kw = set(extract_keywords(original, max_kw=8))
    comp_kw = set(extract_keywords(compressed, max_kw=8))
    if not orig_kw:
        return True
    return len(orig_kw & comp_kw) / len(orig_kw) >= 0.6
