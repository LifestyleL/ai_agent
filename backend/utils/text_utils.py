"""
基础文本处理工具
纯函数，无副作用，可被任意模块组合使用
"""
import re
import math
from typing import List, Dict, Set
from datetime import datetime


# ── 中文停用词 ──────────────────────────────────────

_ZH_STOP_WORDS: Set[str] = {
    "的", "了", "是", "在", "我", "你", "他", "她", "它", "们",
    "和", "与", "或", "也", "就", "都", "而", "及", "把", "被",
    "让", "从", "到", "对", "向", "往", "用", "以", "为",
    "这个", "那个", "一个", "什么", "怎么", "如何", "哪", "哪个",
    "可以", "吗", "讲", "吧", "啊", "呢", "哦", "嗯", "哈",
    "说", "想", "看", "做", "来", "去", "会", "能", "要", "有",
    "不", "很", "好", "还", "这", "那", "些", "得", "着", "过",
    "但", "因为", "所以", "然后", "如果", "虽然", "不过",
    "觉得", "知道", "应该", "可能", "已经", "比较", "一点",
}


# ── 关键词提取 ─────────────────────────────────────

def extract_keywords(text: str, max_kw: int = 8) -> List[str]:
    """简易中文关键词提取：n-gram + TF 排序 + 去停用词 + 去重叠"""
    cleaned = re.sub(r'[^一-龥a-zA-Z0-9]', '', text)
    if not cleaned:
        return []

    freq: Dict[str, int] = {}
    for n in (2, 3, 4):
        for i in range(len(cleaned) - n + 1):
            gram = cleaned[i:i + n]
            if gram in _ZH_STOP_WORDS:
                continue
            freq[gram] = freq.get(gram, 0) + 1

    sorted_grams = sorted(freq.items(), key=lambda x: x[1], reverse=True)

    result: List[str] = []
    for gram, _ in sorted_grams:
        if len(result) >= max_kw:
            break
        # 避免嵌套重复
        if any(gram in r or r in gram for r in result):
            continue
        result.append(gram)

    return result


# ── 字符串相似度 ────────────────────────────────────

def jaccard_similarity(a: str, b: str) -> float:
    """两个字符串的 Jaccard 相似度 (基于字符 bigram)"""
    def bigrams(s: str) -> Set[str]:
        return {s[i:i + 2] for i in range(len(s) - 1)}
    sa = bigrams(a)
    sb = bigrams(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# ── 日期工具 ───────────────────────────────────────

def same_date(ts1: str, ts2: str) -> bool:
    """判断两个 ISO 时间戳是否同一天"""
    return ts1[:10] == ts2[:10]


def parse_iso(ts: str) -> datetime:
    """解析 ISO 时间戳，失败返回当前时间"""
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        return datetime.now()


def days_ago(ts: str) -> float:
    """计算时间戳距今多少天"""
    try:
        dt = datetime.fromisoformat(ts)
        return (datetime.now() - dt).total_seconds() / 86400.0
    except Exception:
        return 0.0


# ── 时间衰减 ───────────────────────────────────────

def time_decay(ts: str, halflife_days: float = 7.0) -> float:
    """指数时间衰减，半衰期可配置"""
    d = days_ago(ts)
    return math.exp(-d / halflife_days)
