"""
响应追踪器：追踪用户对主动发言的反馈，用于优化策略
"""

import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from enum import Enum


class ResponseType(Enum):
    """用户响应类型"""
    POSITIVE = "positive"  # 正面回应（积极回复、继续对话）
    NEUTRAL = "neutral"    # 中性回应（简单回复）
    NEGATIVE = "negative"  # 负面回应（拒绝、无视、负面情绪）
    IGNORE = "ignore"      # 完全无视（长时间不回复）


class ResponseTracker:
    """追踪用户对主动发言的反馈"""

    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = Path(data_dir) if data_dir else Path(__file__).parent.parent.parent / "agent_memory" / "spontaneous"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.response_history = []  # 内存中的响应历史
        self.last_spontaneous_text = ""  # 上一次主动发言的内容
        self.last_spontaneous_time = 0   # 上一次主动发言的时间

        # 加载历史数据
        self._load_history()

    def _load_history(self):
        """加载历史响应数据"""
        history_file = self.data_dir / "response_history.json"
        if history_file.exists():
            try:
                with open(history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.response_history = data.get("history", [])
                print(f"[ResponseTracker] 加载了{len(self.response_history)}条响应历史")
            except Exception as e:
                print(f"[ResponseTracker] 加载历史失败: {e}")
                self.response_history = []

    def _save_history(self):
        """保存响应历史到文件"""
        history_file = self.data_dir / "response_history.json"
        try:
            data = {
                "history": self.response_history[-100:],  # 只保存最近100条
                "updated": datetime.now().isoformat()
            }
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ResponseTracker] 保存历史失败: {e}")

    def record_spontaneous(self, text: str, context: Dict[str, Any]):
        """记录一次主动发言"""
        self.last_spontaneous_text = text
        self.last_spontaneous_time = time.time()

        record = {
            "type": "spontaneous",
            "timestamp": self.last_spontaneous_time,
            "text": text,
            "context": {
                "silence_duration": context.get("silence_duration", 0),
                "priority": context.get("priority", 1),
                "trigger_reason": context.get("trigger_reason", ""),
                "time_of_day": context.get("time_context", {}).get("time_of_day", "")
            },
            "user_response": None,  # 等待用户响应
            "response_type": None,
            "response_time": None
        }

        self.response_history.append(record)
        print(f"[ResponseTracker] 记录主动发言: '{text[:30]}...'")

    def record_response(self, user_input: str, time_to_respond: Optional[float] = None) -> ResponseType:
        """
        记录用户对上一次主动发言的响应

        Args:
            user_input: 用户输入文本
            time_to_respond: 从主动发言到用户响应的时间（秒），如果为None则自动计算

        Returns:
            ResponseType: 响应的分类
        """
        if not self.last_spontaneous_text:
            print("[ResponseTracker] 没有待追踪的主动发言")
            return ResponseType.NEUTRAL

        if time_to_respond is None:
            time_to_respond = time.time() - self.last_spontaneous_time

        # 分类用户响应
        response_type = self._classify_response(user_input, time_to_respond)

        # 找到对应的主动发言记录
        for record in reversed(self.response_history):
            if record.get("type") == "spontaneous" and record.get("user_response") is None:
                record["user_response"] = user_input
                record["response_type"] = response_type.value
                record["response_time"] = time_to_respond
                record["classified_at"] = time.time()
                break

        print(f"[ResponseTracker] 记录用户响应: {response_type.value} (响应时间: {time_to_respond:.1f}s)")
        print(f"  用户输入: '{user_input[:50]}...'")

        # 保存历史
        self._save_history()

        return response_type

    def _classify_response(self, user_input: str, time_to_respond: float) -> ResponseType:
        """分类用户响应"""
        user_input_lower = user_input.lower()

        # 1. 检查是否无视（长时间不响应）
        if time_to_respond > 300:  # 5分钟无响应
            return ResponseType.IGNORE

        # 2. 负面响应关键词
        negative_keywords = ["别", "不要", "不想", "闭嘴", "安静", "烦", "讨厌", "走开", "gun"]
        for keyword in negative_keywords:
            if keyword in user_input_lower:
                return ResponseType.NEGATIVE

        # 3. 简短/中性响应
        if len(user_input.strip()) < 3:
            return ResponseType.NEUTRAL

        neutral_patterns = ["嗯", "哦", "啊", "好", "行", "知道了", "OK", "ok"]
        for pattern in neutral_patterns:
            if pattern in user_input_lower:
                return ResponseType.NEUTRAL

        # 4. 正面响应关键词
        positive_keywords = ["谢谢", "好的", "可以", "不错", "喜欢", "哈哈", "嘿嘿", "有趣"]
        for keyword in positive_keywords:
            if keyword in user_input_lower:
                return ResponseType.POSITIVE

        # 5. 问题/继续对话的迹象
        question_words = ["吗", "？", "?", "为什么", "怎么", "如何", "什么", "谁", "哪里"]
        for word in question_words:
            if word in user_input_lower:
                return ResponseType.POSITIVE

        # 6. 长度判断
        if len(user_input) > 15:  # 较长的回复通常表示积极
            return ResponseType.POSITIVE

        return ResponseType.NEUTRAL

    def get_recent_stats(self, hours: int = 24) -> Dict[str, Any]:
        """获取最近N小时的统计数据"""
        cutoff = time.time() - (hours * 3600)

        recent_records = [
            r for r in self.response_history
            if r.get("timestamp", 0) > cutoff and r.get("type") == "spontaneous"
        ]

        total = len(recent_records)
        if total == 0:
            return {
                "total": 0,
                "positive_rate": 0,
                "avg_response_time": 0,
                "effectiveness": 0
            }

        # 统计响应类型
        type_counts = {"positive": 0, "neutral": 0, "negative": 0, "ignore": 0}
        response_times = []

        for record in recent_records:
            resp_type = record.get("response_type")
            if resp_type and resp_type in type_counts:
                type_counts[resp_type] += 1

            resp_time = record.get("response_time")
            if resp_time and resp_time < 300:  # 排除无视的
                response_times.append(resp_time)

        positive_rate = type_counts["positive"] / total if total > 0 else 0
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0

        # 计算有效性分数（正面率 * 响应速度因子）
        speed_factor = max(0, 1 - (avg_response_time / 180)) if avg_response_time > 0 else 0.5
        effectiveness = positive_rate * speed_factor

        return {
            "total": total,
            "type_counts": type_counts,
            "positive_rate": positive_rate,
            "avg_response_time": avg_response_time,
            "effectiveness": effectiveness,
            "time_range_hours": hours
        }

    def get_insights(self) -> List[Dict[str, Any]]:
        """获取洞察建议"""
        insights = []
        stats_24h = self.get_recent_stats(24)

        if stats_24h["total"] < 5:
            insights.append({
                "type": "insufficient_data",
                "message": "数据不足，需要更多主动发言样本",
                "priority": "low"
            })
            return insights

        positive_rate = stats_24h["positive_rate"]
        avg_response_time = stats_24h["avg_response_time"]

        # 洞察1：正面率
        if positive_rate < 0.3:
            insights.append({
                "type": "low_positive_rate",
                "message": f"正面响应率较低 ({positive_rate:.0%})，建议减少主动发言频率或调整话题",
                "priority": "high"
            })
        elif positive_rate > 0.7:
            insights.append({
                "type": "high_positive_rate",
                "message": f"正面响应率较高 ({positive_rate:.0%})，可以适当增加主动发言",
                "priority": "medium"
            })

        # 洞察2：响应时间
        if avg_response_time > 120:
            insights.append({
                "type": "slow_response",
                "message": f"平均响应时间较长 ({avg_response_time:.0f}秒)，用户可能需要更长时间思考",
                "priority": "medium"
            })

        # 洞察3：无视率
        ignore_rate = stats_24h["type_counts"]["ignore"] / stats_24h["total"]
        if ignore_rate > 0.4:
            insights.append({
                "type": "high_ignore_rate",
                "message": f"无视率较高 ({ignore_rate:.0%})，可能发言时机不佳或话题不合适",
                "priority": "high"
            })

        # 洞察4：负面率
        negative_rate = stats_24h["type_counts"]["negative"] / stats_24h["total"]
        if negative_rate > 0.2:
            insights.append({
                "type": "high_negative_rate",
                "message": f"负面响应率较高 ({negative_rate:.0%})，需要调整发言风格或内容",
                "priority": "high"
            })

        return insights

    def should_adjust_strategy(self) -> bool:
        """是否应该调整策略（基于近期表现）"""
        stats = self.get_recent_stats(6)  # 最近6小时
        if stats["total"] < 3:
            return False

        positive_rate = stats["positive_rate"]
        ignore_rate = stats["type_counts"]["ignore"] / stats["total"]

        # 如果正面率很低或无视率很高，需要调整
        if positive_rate < 0.2 or ignore_rate > 0.5:
            return True

        return False