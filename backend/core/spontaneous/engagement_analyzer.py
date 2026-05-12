"""
用户参与度自动分析器
滑动窗口行为统计 → 推断用户类型
"""
import time
from collections import deque
from typing import Optional, Dict, Any


class UserEngagementAnalyzer:
    """滑动窗口行为统计，用于自动推断用户类型"""

    def __init__(self, window_days: int = 7, max_rounds: int = 50):
        self.events = deque(maxlen=max_rounds)
        self.window_days = window_days
        self.max_rounds = max_rounds
        self.last_inference_time: float = 0.0

    def record_turn(self, user_msg: Optional[str], ai_msg: Optional[str],
                    is_ai_spontaneous: bool, timestamp: float):
        """集中记录一轮交互（由 AgentDriver 在对话完成后调用）"""
        if user_msg:
            self.events.append({
                "role": "user",
                "timestamp": timestamp,
                "msg_length": len(user_msg),
                "is_initiated_by_user": not is_ai_spontaneous,
                "is_reply_to_spontaneous": is_ai_spontaneous,
            })
        if ai_msg:
            self.events.append({
                "role": "assistant",
                "timestamp": timestamp,
                "msg_length": len(ai_msg),
                "is_spontaneous": is_ai_spontaneous,
            })

    def compute_stats(self) -> Dict[str, float]:
        now = time.time()
        window_start = now - self.window_days * 86400
        recent = [e for e in self.events if e["timestamp"] >= window_start]
        if not recent:
            return {}

        ai_initiatives = [e for e in recent if e["role"] == "assistant"]
        user_replies = [e for e in recent if e["role"] == "user" and e.get("is_reply_to_spontaneous")]
        user_initiated = [e for e in recent if e["role"] == "user" and e.get("is_initiated_by_user")]

        total_initiatives = max(len(ai_initiatives), 1)
        reply_count = len(user_replies)
        reply_rate = reply_count / total_initiatives

        delays = []
        for ai in ai_initiatives:
            next_reply = next((u for u in user_replies if u["timestamp"] > ai["timestamp"]), None)
            if next_reply:
                delays.append(next_reply["timestamp"] - ai["timestamp"])
        avg_delay = sum(delays) / len(delays) if delays else 99999.0

        total_rounds = max(len(recent), 1)
        user_initiated_ratio = len(user_initiated) / total_rounds

        user_msgs = [e for e in recent if e["role"] == "user"]
        ai_msgs = [e for e in recent if e["role"] == "assistant"]
        avg_user_len = sum(e["msg_length"] for e in user_msgs) / max(len(user_msgs), 1)
        avg_ai_len = sum(e["msg_length"] for e in ai_msgs) / max(len(ai_msgs), 1)
        msg_length_ratio = avg_user_len / max(avg_ai_len, 1)

        positive_emotions = [e for e in user_replies if e.get("emotion") in ("happy", "excited")]
        positive_ratio = len(positive_emotions) / max(len(user_replies), 1)

        return {
            "reply_rate": reply_rate,
            "avg_delay": avg_delay,
            "user_initiated_ratio": user_initiated_ratio,
            "msg_length_ratio": msg_length_ratio,
            "positive_emotion_ratio": positive_ratio,
        }

    def infer_type(self) -> str:
        stats = self.compute_stats()
        if not stats:
            return "normal"

        if stats["reply_rate"] < 0.2 and stats["avg_delay"] > 3600:
            return "quiet"
        elif stats["reply_rate"] < 0.5 and stats["avg_delay"] > 600:
            return "busy"
        elif stats["reply_rate"] > 0.8 and stats["user_initiated_ratio"] > 0.4 and stats["msg_length_ratio"] > 0.5:
            return "social"
        return "normal"
