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
    # 记忆查询噪音词：这些碎片不应成为搜索关键词
    "你记", "记得", "不记得", "还记得", "记不", "记得吗",
    "查查", "查一下", "翻翻", "翻一下", "找到", "查到",
    "讲讲", "说说", "帮我", "帮我查", "帮我找",
    "聊聊", "讲一讲", "说一", "说说话", "说说话吗",
    "发生过", "发生了什么", "有没有", "之前", "最近",
    "怎么", "怎么样",
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


# ── 标签语义扩展 ────────────────────────────────────

_SEMANTIC_MAP: Dict[str, List[str]] = {
    "bug": ["错误", "故障", "异常", "崩溃"],
    "修复": ["修bug", "debug", "调试", "补丁"],
    "食物": ["吃饭", "外卖", "餐厅", "美食", "零食"],
    "学习": ["教程", "文档", "笔记", "课程"],
    "心情": ["情绪", "感受", "开心", "难过", "沮丧"],
    "代码": ["编程", "程序", "脚本", "开发"],
    "音乐": ["歌曲", "歌单", "播放", "演唱会"],
    "游戏": ["手游", "电竞", "switch", "steam", "ps5"],
    "工作": ["上班", "加班", "会议", "项目", "任务"],
    "健康": ["运动", "锻炼", "睡眠", "生病", "体检"],
}

_SEMANTIC_FLAT: Dict[str, List[str]] = {}
for _canon, _syns in _SEMANTIC_MAP.items():
    _all = [_canon] + _syns
    for _w in _all:
        _SEMANTIC_FLAT[_w] = _all


def expand_query_tags(tags: List[str]) -> List[str]:
    """查语义映射表扩展查询标签，去重返回"""
    expanded = list(tags)
    for t in tags:
        synonyms = _SEMANTIC_FLAT.get(t.lower())
        if synonyms:
            for s in synonyms:
                if s not in expanded:
                    expanded.append(s)
    return expanded
