"""
Drive模型：AI原生的算力分配模型

抛弃人类的“疲劳”，回归AI的“算力分配”。
管理对话投入度(engagement)和自驱力(drive)，实现AI原生的行为模式。
"""

import time
import random
import threading
from .event_bus import event_bus, EventType, Event, event_handler


class DriveModel:
    """
    驱动模型：管理AI的内在驱动力

    核心状态：
    - engagement: 对话投入度 (0~1) 越高表示越专注
    - drive: 自驱力/无聊度 (0~1) 越高表示越想自己找事做

    工作模式：
    1. 用户互动时重置自驱力，提升投入度
    2. 空闲时投入度自然衰减，自驱力增长
    3. 自驱力满值时触发自发行为
    """

    def __init__(self):
        # 核心状态
        self.engagement = 0.5   # 对话投入度 (0~1)
        self.drive = 0.0        # 自驱力/无聊度 (0~1)

        # 时间追踪
        self._last_interaction = time.time()

        # 线程控制
        self._running = False
        self._tick_thread = None

        # 注册事件处理器
        self._setup_event_handlers()

        print("[DriveModel] 驱动模型初始化完成")

    def _setup_event_handlers(self):
        """设置事件处理器"""
        # 用户活动事件：重置自驱力，提升投入度
        @event_handler([EventType.USER_INPUT_RECEIVED, EventType.TASK_COMPLETED])
        def on_user_activity(event: Event):
            """用户有动静，重置自驱力，提升投入度"""
            self.drive = max(0, self.drive - 0.5)
            self.engagement = min(1.0, self.engagement + 0.2)
            self._last_interaction = time.time()
            print(f"[DriveModel] 用户活动: engagement={self.engagement:.2f}, drive={self.drive:.2f}")

    def tick(self):
        """每秒推进状态"""
        now = time.time()
        idle_time = now - self._last_interaction

        # 1. 投入度随时间自然衰减
        self.engagement = max(0.0, self.engagement - 0.002)

        # 2. 自驱力随空闲时间增长 (超过60秒开始飙升)
        if idle_time > 60:
            self.drive = min(1.0, self.drive + 0.005)

        # 3. 触发自驱行为
        if self.drive > 0.85 and random.random() < 0.05:
            print(f"[DriveModel] 自驱力溢出！drive={self.drive:.2f}，触发自发行为")
            self.drive = 0.0  # 清空内驱力，防止连续触发

            # 发布自发行为触发事件
            event_bus.publish(
                EventType.SPONTANEOUS_ACTION_TRIGGERED,
                source="DriveModel.tick",
                engagement=self.engagement,
                drive=self.drive,
                idle_time=idle_time,
                timestamp=now
            )

    def _tick_loop(self):
        """后台推进循环"""
        while self._running:
            try:
                self.tick()
            except Exception as e:
                print(f"[DriveModel] tick异常: {e}")
            time.sleep(1.0)

    def start(self):
        """启动驱动模型"""
        if self._running:
            return

        self._running = True
        self._tick_thread = threading.Thread(target=self._tick_loop, daemon=True)
        self._tick_thread.start()
        print("[DriveModel] 驱动模型已启动")

    def stop(self):
        """停止驱动模型"""
        self._running = False
        if self._tick_thread:
            self._tick_thread.join(timeout=2.0)
        print("[DriveModel] 驱动模型已停止")

    def get_state(self):
        """获取当前状态"""
        return {
            "engagement": self.engagement,
            "drive": self.drive,
            "idle_time": time.time() - self._last_interaction,
            "last_interaction": self._last_interaction
        }


# 全局单例
_drive_model = None

def get_drive_model() -> DriveModel:
    """获取驱动模型单例"""
    global _drive_model
    if _drive_model is None:
        _drive_model = DriveModel()
    return _drive_model