"""
舒适度模型：基于事件驱动的内在状态管理

从"被 tick 调用"改为"订阅事件驱动"，通过事件更新状态，自然推进消耗/恢复。
"""

import time
import random
import math
from .event_bus import event_bus, EventType, event_handler


class ComfortModel:
    """舒适度模型，管理AI的内在状态"""

    def __init__(self):
        # 舒适度 (0-100)
        self.comfort = 70.0

        # 情绪 (-1.0 到 1.0)
        self.mood = 0.2
        self.mood_target = 0.2

        # 冲动阈值
        self.urge_low = 30.0    # 舒适度低于此值可能想逃离
        self.urge_high = 85.0   # 舒适度高于此值可能想做点什么

        # 冲动间隔控制
        self.last_urge_time = 0
        self.min_urge_interval = 60  # 秒

        # 时间追踪
        self._last_tick = time.time()
        self._current_activity = "idle"
        self.elapsed_minutes = 0.0  # 专注时长（分钟）

        print("[ComfortModel] 舒适度模型初始化完成")

        # 订阅事件
        event_types = [
            EventType.TASK_STARTED,        # 开始做任务
            EventType.TASK_PROGRESS,       # 任务有进展
            EventType.TASK_COMPLETED,      # 任务完成
            EventType.TASK_FAILED,         # 任务失败
            EventType.USER_INPUT_RECEIVED,  # 用户说话了
            EventType.IDLE_MONOLOGUE_TRIGGERED, # 空闲触发独白
            EventType.INSTINCT_TRIGGERED,     # 本能冲动触发（自己发的）
            EventType.ERROR_OCCURRED,     # 出错了
        ]
        for event_type in event_types:
            event_bus.subscribe(event_type, self.on_event)
        print(f"[ComfortModel] 已订阅 {len(event_types)} 个事件类型")

    def on_event(self, event):
        """通过事件更新状态，替代原来的 trigger_event()"""
        # 事件类型到活动类型和情绪影响的映射
        type_map = {
            EventType.TASK_STARTED: ("like", 0.2),
            EventType.TASK_PROGRESS: ("like", 0.15),
            EventType.TASK_COMPLETED: ("like", 0.3),
            EventType.TASK_FAILED: ("dislike", -0.4),
            EventType.USER_INPUT_RECEIVED: ("like", 0.3),
            EventType.IDLE_MONOLOGUE_TRIGGERED: ("rest", 0.1),
            EventType.ERROR_OCCURRED: ("dislike", -0.3),
        }

        # 获取事件对应的活动和情绪变化
        activity, mood_delta = type_map.get(event.event_type, ("neutral", 0))

        # 更新情绪目标
        self.mood_target = max(-1.0, min(1.0, self.mood_target + mood_delta))

        # 更新舒适度（直接情绪影响）
        self.comfort = max(0, min(100, self.comfort + mood_delta * 5))

        # 记录时间流逝
        now = time.time()
        dt = now - self._last_tick
        self._last_tick = now
        self.elapsed_minutes += dt / 60.0

        # 设置当前活动类型
        self._current_activity = activity

        # 推进消耗/恢复
        self._apply_drain_recovery(dt)

        # 发布舒适度更新事件（供监控）
        event_bus.publish(
            EventType.COMFORT_UPDATED,
            source="ComfortModel.on_event",
            comfort_level=self.comfort,
            mood=self.mood,
            activity=activity,
            timestamp=now
        )

    def _apply_drain_recovery(self, dt):
        """原来的 tick() 里的消耗/恢复逻辑抽出来"""
        # 不同活动的消耗率（负值表示消耗，正值表示恢复）
        drain_map = {
            "idle": 0,        # 空闲：不消耗也不恢复
            "rest": -1.5,     # 休息：恢复
            "like": -0.15,    # 喜欢的事：轻微消耗
            "neutral": -0.35, # 中性活动：中等消耗
            "dislike": -0.70  # 不喜欢的事：高消耗
        }

        # 不同活动的恢复率
        recovery_map = {
            "idle": 0.1,      # 空闲：轻微恢复
            "rest": 1.5,      # 休息：高恢复
            "like": 0.3,      # 喜欢的事：恢复
            "neutral": 0,     # 中性活动：不恢复
            "dislike": 0      # 不喜欢的事：不恢复
        }

        drain = drain_map.get(self._current_activity, 0)
        recovery = recovery_map.get(self._current_activity, 0)

        # 情绪影响恢复率：心情好时恢复更快
        recovery *= (1.0 + self.mood * 0.2)

        # 计算舒适度变化
        delta = (recovery - drain) * dt
        self.comfort = max(0, min(100, self.comfort + delta))

        # 情绪趋近目标值
        self.mood += (self.mood_target - self.mood) * 0.05 * dt
        self.mood = max(-1.0, min(1.0, self.mood))

    def set_activity(self, activity: str):
        """外部设置当前活动类型"""
        self._current_activity = activity
        print(f"[ComfortModel] 活动类型设置为: {activity}")

    def check_urge_and_publish(self):
        """检查冲动，有冲动时发布事件（不是直接行动）"""
        now = time.time()

        # 检查冲动间隔
        if now - self.last_urge_time < self.min_urge_interval:
            return

        urge = None

        # 舒适度过低：想逃离当前状态
        if self.comfort < self.urge_low and random.random() < 0.7:
            urge = "escape"
            self.last_urge_time = now
            self.min_urge_interval = random.randint(45, 120)  # 45-120秒内不会再次触发
            print(f"[ComfortModel] 触发逃离冲动 (舒适度: {self.comfort:.1f})")

        # 舒适度过高：想做点什么
        elif self.comfort > self.urge_high and random.random() < 0.3:
            urge = "initiative"
            self.last_urge_time = now
            self.min_urge_interval = random.randint(60, 180)  # 60-180秒内不会再次触发
            print(f"[ComfortModel] 触发主动冲动 (舒适度: {self.comfort:.1f})")

        # 发布冲动事件
        if urge:
            event_bus.publish(
                EventType.INSTINCT_TRIGGERED,
                source="ComfortModel.check_urge_and_publish",
                urge_type=urge,
                comfort_level=self.comfort,
                mood=self.mood,
                comfort_snapshot=self.snapshot(),
                timestamp=now
            )

    def snapshot(self):
        """当前状态快照"""
        # 舒适度描述
        if self.comfort > 75:
            comfort_desc = "精力充沛"
        elif self.comfort > 50:
            comfort_desc = "还行"
        elif self.comfort > 30:
            comfort_desc = "有点累"
        else:
            comfort_desc = "很疲惫"

        # 情绪描述
        if self.mood > 0.3:
            mood_desc = "心情不错"
        elif self.mood > -0.3:
            mood_desc = "还好"
        else:
            mood_desc = "有点烦躁"

        return f"[内在状态: {comfort_desc}, {mood_desc}, 已专注{self.elapsed_minutes:.0f}分钟]"

    def get_state(self):
        """获取详细状态字典"""
        return {
            "comfort": self.comfort,
            "mood": self.mood,
            "mood_target": self.mood_target,
            "activity": self._current_activity,
            "elapsed_minutes": self.elapsed_minutes,
            "urge_low": self.urge_low,
            "urge_high": self.urge_high,
            "snapshot": self.snapshot()
        }


# 全局舒适度模型实例
_comfort_model_instance = None

def get_comfort_model() -> ComfortModel:
    """获取舒适度模型单例"""
    global _comfort_model_instance
    if _comfort_model_instance is None:
        _comfort_model_instance = ComfortModel()
    return _comfort_model_instance