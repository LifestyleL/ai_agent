"""
触发策略：决定何时应该主动发言
基于沉默时长、上下文丰富度、时间因素等
"""

import time
import random
from typing import Dict, Any, Optional
from datetime import datetime, timedelta


class TriggerPolicy:
    """主动发言的触发策略"""

    def __init__(self):
        self.last_user_activity = time.time()
        self.last_spoke_time = 0
        self.conversation_lull_start = None  # 对话"冷场"开始时间
        self.trigger_history = []  # 触发记录，用于分析模式

    def update_user_activity(self):
        """用户有新活动时调用（发送消息、ASR识别到语音等）"""
        self.last_user_activity = time.time()
        self.conversation_lull_start = None  # 重置冷场计时
        print(f"[TriggerPolicy] 用户活动更新: {time.ctime(self.last_user_activity)}")

    def update_spoke(self):
        """AI刚发言后调用"""
        self.last_spoke_time = time.time()
        print(f"[TriggerPolicy] AI发言更新: {time.ctime(self.last_spoke_time)}")

    def _calculate_silence_duration(self) -> float:
        """计算沉默时长（秒）"""
        return time.time() - max(self.last_user_activity, self.last_spoke_time)

    def _should_start_lull_timer(self, silence_duration: float) -> bool:
        """是否应该开始冷场计时"""
        # 沉默超过30秒，且还没有开始冷场计时
        if silence_duration > 30 and self.conversation_lull_start is None:
            self.conversation_lull_start = time.time()
            print(f"[TriggerPolicy] 开始冷场计时 (沉默{silence_duration:.1f}秒)")
            return True
        return False

    def _get_time_based_probability(self, hour: int) -> float:
        """基于时间的触发概率（白天高，深夜低）"""
        if 7 <= hour < 23:
            return 0.7  # 白天活跃时间
        elif 23 <= hour or hour < 2:
            return 0.3  # 深夜，较低概率
        else:
            return 0.1  # 凌晨，很低概率

    def _get_context_richness_factor(self, context: Dict[str, Any]) -> float:
        """基于上下文丰富度的因子"""
        factor = 0.5  # 基础值

        # 短期记忆越多，触发概率越高
        short_term_count = context.get("short_term_count", 0)
        if short_term_count >= 3:
            factor += 0.2
        elif short_term_count == 0:
            factor -= 0.2

        # 有长期记忆内容，因子增加
        long_term = context.get("long_term_summary", "")
        if long_term and len(long_term) > 50:
            factor += 0.1

        # 有近期自言自语，因子增加
        thoughts = context.get("recent_thoughts", "")
        if thoughts:
            factor += 0.1

        # 有日记，因子增加
        if context.get("has_diary", False):
            factor += 0.1

        return max(0.1, min(1.0, factor))  # 限制在0.1-1.0之间

    def evaluate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        评估是否应该触发主动发言

        Returns:
            {
                "should_trigger": bool,
                "silence_duration": float,
                "trigger_reason": str,
                "priority": int (1-5, 5最高),
                "details": Dict
            }
        """
        silence_duration = self._calculate_silence_duration()
        now = datetime.now()
        hour = now.hour

        # 基础检查：沉默时间太短不触发（生产环境30分钟）
        if silence_duration < 1800:
            return {
                "should_trigger": False,
                "silence_duration": silence_duration,
                "trigger_reason": "沉默时间不足",
                "priority": 1,
                "details": {"min_silence": 1800}
            }

        # 检查冷场
        self._should_start_lull_timer(silence_duration)

        # 计算触发概率
        time_prob = self._get_time_based_probability(hour)
        context_factor = self._get_context_richness_factor(context)

        # 基础触发概率 = 时间概率 * 上下文因子
        base_probability = time_prob * context_factor

        # 沉默时间加成（沉默越久，概率越高）
        silence_factor = min(1.0, silence_duration / 300)  # 5分钟封顶
        final_probability = base_probability * (0.5 + silence_factor * 0.5)

        # 如果有冷场计时，额外加成
        if self.conversation_lull_start:
            lull_duration = time.time() - self.conversation_lull_start
            if lull_duration > 60:  # 冷场超过1分钟
                final_probability *= 1.5
                print(f"[TriggerPolicy] 冷场加成: {lull_duration:.1f}秒")

        # 限制在0-1之间
        final_probability = max(0.05, min(0.95, final_probability))

        # 随机决定
        should_trigger = random.random() < final_probability

        # 生成触发原因
        trigger_reason = ""
        if should_trigger:
            reasons = []
            if silence_duration > 120:
                reasons.append(f"沉默{silence_duration:.0f}秒")
            if context_factor > 0.7:
                reasons.append("上下文丰富")
            if hour in [9, 10, 14, 15, 20, 21]:
                reasons.append("活跃时段")
            if self.conversation_lull_start:
                reasons.append("避免冷场")

            trigger_reason = " + ".join(reasons) if reasons else "随机触发"

        # 优先级计算（基于概率和沉默时间）
        priority = 1
        if final_probability > 0.7:
            priority = 4
        elif final_probability > 0.5:
            priority = 3
        elif final_probability > 0.3:
            priority = 2

        if silence_duration > 180:  # 沉默超过3分钟，优先级提高
            priority = min(5, priority + 1)

        # 记录触发历史（最多保留50条）
        trigger_record = {
            "timestamp": time.time(),
            "should_trigger": should_trigger,
            "probability": final_probability,
            "silence_duration": silence_duration,
            "reason": trigger_reason,
            "priority": priority
        }
        self.trigger_history.append(trigger_record)
        if len(self.trigger_history) > 50:
            self.trigger_history.pop(0)

        result = {
            "should_trigger": should_trigger,
            "silence_duration": silence_duration,
            "trigger_reason": trigger_reason,
            "priority": priority,
            "details": {
                "probability": final_probability,
                "time_probability": time_prob,
                "context_factor": context_factor,
                "silence_factor": silence_factor,
                "hour": hour,
                "has_lull_timer": self.conversation_lull_start is not None
            }
        }

        if should_trigger:
            print(f"[TriggerPolicy] 触发主动发言: {trigger_reason}")
            print(f"  详情: 概率={final_probability:.2f}, 沉默={silence_duration:.1f}s, 优先级={priority}")

        return result