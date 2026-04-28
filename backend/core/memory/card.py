"""
记忆卡片数据结构
纯算法，不使用 LLM
"""
from dataclasses import dataclass, field, asdict
from typing import List, Dict
from datetime import datetime
import random

from utils.text_utils import extract_keywords


@dataclass
class Card:
    """记忆卡片"""
    id: str
    type: str              # "dialogue" | "event" | "fact" | "summary"
    timestamp: str         # ISO 时间戳
    topic: str             # 一句话主题 (≤30字)
    tags: List[str]        # 关键词标签 (3-8个)
    content: str           # 卡片正文 (≤200字)
    detail: str = ""       # 完整原文 (Tier 0 保留)
    importance: float = 0.5
    emotion: str = "neutral"
    tier: int = 0          # 0=raw, 1=compressed, 2=essence, -1=deleted
    links: Dict[str, float] = field(default_factory=dict)  # {target_card_id: weight}


def generate_card_id() -> str:
    """时间戳 + 4位随机数"""
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    rnd = random.randint(1000, 9999)
    return f"card_{ts}_{rnd}"


def score_importance(
    tags: List[str],
    emotion_strength: float = 0.0,
    content_len: int = 0
) -> float:
    """算法计算卡片重要性 0.0-1.0"""
    score = 0.3

    score += min(len(tags) * 0.05, 0.25)
    score += min(emotion_strength / 10.0, 0.2)

    if 60 <= content_len <= 200:
        score += 0.15
    elif content_len > 200:
        score += 0.1
    else:
        score += 0.05

    important_tags = {"bug", "修复", "问题", "完成", "决定", "重要", "记住",
                      "bugfix", "fix", "done", "decision", "important"}
    for t in tags:
        if t.lower() in important_tags:
            score += 0.08

    return round(min(1.0, score), 2)


def card_to_dict(card: Card) -> dict:
    return asdict(card)


def dict_to_card(d: dict) -> Card:
    return Card(
        id=d.get("id", ""),
        type=d.get("type", "dialogue"),
        timestamp=d.get("timestamp", ""),
        topic=d.get("topic", ""),
        tags=d.get("tags", []),
        content=d.get("content", ""),
        detail=d.get("detail", ""),
        importance=d.get("importance", 0.5),
        emotion=d.get("emotion", "neutral"),
        tier=d.get("tier", 0),
        links=d.get("links", {}),
    )
