"""
频率限制器：防止主动发言过于频繁
"""

import time
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, Any
import config


class FreqLimiter:
    """频率限制器，确保主动发言不会过于频繁"""

    def __init__(self):
        self.history = deque(maxlen=20)
        self.last_attempt_time = 0
        self.consecutive_rejects = 0
        self._reject_multiplier = 1.0

        self.rules = {
            "min_interval": config.SPONTANEOUS_MIN_INTERVAL,
            "max_per_hour": config.SPONTANEOUS_MAX_PER_HOUR,
            "max_per_day": config.SPONTANEOUS_MAX_PER_DAY,
            "cool_down_after_reject": config.SPONTANEOUS_COOL_DOWN_AFTER_REJECT,
            "reject_multiplier_max": 3.0,
        }

    def apply_parameters(self, params):
        """根据用户画像更新运行时限制"""
        self.rules["min_interval"] = params.min_interval
        self.rules["max_per_hour"] = params.max_per_hour
        self.rules["max_per_day"] = params.max_per_day
        self.rules["reject_multiplier_max"] = params.reject_multiplier_max

    def reset_reject_multiplier(self):
        self._reject_multiplier = 1.0

    def record_spoke(self):
        """记录一次发言"""
        now = time.time()
        self.history.append(now)
        self.last_attempt_time = now
        self.consecutive_rejects = 0  # 重置连续拒绝计数
        print(f"[FreqLimiter] 记录发言: {datetime.fromtimestamp(now).strftime('%H:%M:%S')}")

    def record_reject(self, reason: str = ""):
        """记录一次拒绝（触发但被限制）"""
        self.consecutive_rejects += 1
        self.last_attempt_time = time.time()
        print(f"[FreqLimiter] 记录拒绝: {reason} (连续{self.consecutive_rejects}次)")

    def _count_recent(self, seconds: int) -> int:
        """统计最近N秒内的发言次数"""
        now = time.time()
        cutoff = now - seconds
        return sum(1 for ts in self.history if ts >= cutoff)

    def _get_hourly_count(self) -> int:
        """统计过去一小时内的发言次数"""
        return self._count_recent(3600)

    def _get_daily_count(self) -> int:
        """统计过去24小时内的发言次数"""
        return self._count_recent(86400)

    def check(self, priority: int = 1) -> Dict[str, Any]:
        """
        检查是否允许发言

        Args:
            priority: 触发优先级（1-5，越高越可能突破限制）

        Returns:
            {
                "allowed": bool,
                "reasons": List[str],  # 拒绝原因
                "next_allowed_in": float,  # 距离下次允许的秒数
                "stats": Dict[str, int]  # 统计数据
            }
        """
        now = time.time()
        reasons = []
        stats = {}

        # 0. 绝对禁止（max_per_hour == 0 表示该类型完全不允许主动发言）
        if self.rules["max_per_hour"] <= 0:
            reasons.append("该用户类型禁止主动发言 (max_per_hour=0)")
            return {
                "allowed": False,
                "reasons": reasons,
                "next_allowed_in": 86400,
                "stats": {"disabled": 1}
            }

        # 1. 检查最小间隔
        if self.history:
            last_spoke = self.history[-1]
            interval = now - last_spoke
            min_interval = self.rules["min_interval"]

            # 高优先级可以缩短最小间隔
            if priority >= 4:
                min_interval = max(15, min_interval * 0.7)  # 减少30%
            elif priority >= 3:
                min_interval = max(20, min_interval * 0.8)  # 减少20%

            if interval < min_interval:
                reasons.append(f"距离上次发言仅{interval:.1f}秒 (需等待{min_interval:.0f}秒)")
                stats["interval_violation"] = 1

        # 2. 检查被拒绝后的冷却
        if self.consecutive_rejects > 0:
            reject_cooldown = self.rules["cool_down_after_reject"] * min(3, self.consecutive_rejects)
            since_last_attempt = now - self.last_attempt_time

            if since_last_attempt < reject_cooldown:
                reasons.append(f"连续拒绝{self.consecutive_rejects}次后冷却中 ({reject_cooldown:.0f}秒)")
                stats["reject_cooldown"] = 1

        # 3. 检查每小时限制
        hourly_count = self._get_hourly_count()
        max_per_hour = self.rules["max_per_hour"]

        # 高优先级可以突破限制
        allowance_multiplier = 1.0
        if priority >= 5:
            allowance_multiplier = 1.5  # 增加50%限额
        elif priority >= 4:
            allowance_multiplier = 1.2  # 增加20%限额

        adjusted_max_per_hour = int(max_per_hour * allowance_multiplier)

        if hourly_count >= adjusted_max_per_hour:
            reasons.append(f"本小时已发言{hourly_count}次 (限额{adjusted_max_per_hour})")
            stats["hourly_limit"] = 1

        # 4. 检查每日限制
        daily_count = self._get_daily_count()
        max_per_day = self.rules["max_per_day"]

        if daily_count >= max_per_day:
            reasons.append(f"今日已发言{daily_count}次 (日限额{max_per_day})")
            stats["daily_limit"] = 1

        # 5. 特殊规则：深夜限制
        hour = datetime.now().hour
        if config.SPONTANEOUS_NIGHT_START <= hour < config.SPONTANEOUS_NIGHT_END:
            if priority < 4:  # 非高优先级不发言
                reasons.append(f"凌晨{hour}点限制发言 (需优先级≥4)")
                stats["night_limit"] = 1

        # 计算下次允许时间
        next_allowed = 0
        if reasons:
            # 找到最长的限制时间
            delays = []

            if stats.get("interval_violation"):
                delays.append(self.rules["min_interval"] - interval)

            if stats.get("reject_cooldown"):
                delays.append(reject_cooldown - since_last_attempt)

            if stats.get("hourly_limit"):
                # 计算下一小时的时间
                next_hour = (int(now / 3600) + 1) * 3600
                delays.append(next_hour - now)

            if stats.get("daily_limit"):
                # 计算明天的时间
                tomorrow = datetime.now().replace(hour=0, minute=0, second=0) + timedelta(days=1)
                delays.append(tomorrow.timestamp() - now)

            if delays:
                next_allowed = max(delays)

        allowed = len(reasons) == 0

        result = {
            "allowed": allowed,
            "reasons": reasons,
            "next_allowed_in": next_allowed,
            "stats": {
                "hourly_count": hourly_count,
                "daily_count": daily_count,
                "total_recent": len(self.history),
                "consecutive_rejects": self.consecutive_rejects,
                "priority": priority
            }
        }

        if not allowed:
            print(f"[FreqLimiter] 发言被限制: {', '.join(reasons)}")
            print(f"  统计: 时{hourly_count}/日{daily_count}, 连续拒绝{self.consecutive_rejects}次")
            # 只有"实质限制"(额度/深夜)才算拒绝，纯时序违规不进入级联冷却
            is_substantial_reject = bool(
                stats.get("hourly_limit") or stats.get("daily_limit") or stats.get("night_limit")
            )
            if is_substantial_reject:
                self.record_reject("频率限制")
        else:
            print(f"[FreqLimiter] 允许发言 (时{hourly_count}/日{daily_count}, 优先级{priority})")

        return result

    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        now = time.time()
        hourly_count = self._get_hourly_count()
        daily_count = self._get_daily_count()

        recent_intervals = []
        if len(self.history) >= 2:
            timestamps = sorted(self.history)
            for i in range(1, len(timestamps)):
                recent_intervals.append(timestamps[i] - timestamps[i-1])

        avg_interval = sum(recent_intervals) / len(recent_intervals) if recent_intervals else 0

        return {
            "total_spokes": len(self.history),
            "hourly_count": hourly_count,
            "daily_count": daily_count,
            "consecutive_rejects": self.consecutive_rejects,
            "last_spoke_ago": now - self.history[-1] if self.history else float('inf'),
            "last_attempt_ago": now - self.last_attempt_time if self.last_attempt_time > 0 else float('inf'),
            "avg_interval": avg_interval,
            "rules": self.rules.copy()
        }