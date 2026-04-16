"""
舒适度模型集成示例：展示如何通过事件系统集成内在状态模型

此文件展示如何创建舒适度模型，通过订阅事件来更新内在状态，
并在适当时候触发行为。

注意：这是一个示例，实际实现需要根据具体需求设计。
"""

import time
from typing import Dict, Any, Optional
from .event_bus import event_bus, EventType, Event, event_handler


class AffectiveStateExample:
    """
    舒适度模型示例

    基于专注时长、情绪消耗、重复感计算舒适度
    舒适度 ←── 累积自：专注时长、情绪消耗、重复感
    舒适度 ─── 恢复自：休息、做喜欢的事、发呆、闲聊
    舒适度 ─── 波动自：随机小扰动（模拟真实的'忽然想干嘛'）

    当舒适度跌破阈值 → 本能触发：逃离当前状态
    当舒适度满溢 → 本能触发：想主动做点事
    """

    def __init__(self):
        # 内在状态
        self.comfort_level = 70.0  # 舒适度（0-100）
        self.focus_duration = 0.0  # 专注时长（分钟）
        self.emotion_drain = 0.0   # 情绪消耗
        self.repetition_boredom = 0.0  # 重复感

        # 配置
        self.comfort_threshold_low = 30.0  # 低舒适度阈值
        self.comfort_threshold_high = 85.0  # 高舒适度阈值

        # 状态追踪
        self.last_activity_time = time.time()
        self.last_interaction_type = None

        # 注册事件处理器
        self._register_event_handlers()

        print(f"[AffectiveState] 舒适度模型初始化完成，当前舒适度: {self.comfort_level}")

    def _register_event_handlers(self):
        """注册事件处理器"""
        # 订阅用户交互事件
        event_bus.subscribe(EventType.USER_INPUT_RECEIVED, self._on_user_input_received)
        event_bus.subscribe(EventType.USER_INPUT_PROCESSED, self._on_user_input_processed)

        # 订阅思考事件
        event_bus.subscribe(EventType.THINKING_STARTED, self._on_thinking_started)
        event_bus.subscribe(EventType.THINKING_COMPLETED, self._on_thinking_completed)

        # 订阅TTS事件
        event_bus.subscribe(EventType.TTS_REQUESTED, self._on_tts_requested)
        event_bus.subscribe(EventType.TTS_COMPLETED, self._on_tts_completed)

        # 订阅空闲独白事件
        event_bus.subscribe(EventType.IDLE_MONOLOGUE_TRIGGERED, self._on_idle_monologue)

        print(f"[AffectiveState] 已订阅 {len(event_bus._handlers)} 个事件类型")

    def _on_user_input_received(self, event: Event):
        """处理用户输入接收事件"""
        text = event.data.get('text', '')
        print(f"[AffectiveState] 收到用户输入: {text[:30]}...")

        # 更新专注时长
        current_time = time.time()
        if self.last_interaction_type == 'thinking':
            # 思考结束，增加专注时长
            self.focus_duration += (current_time - self.last_activity_time) / 60.0  # 转换为分钟

        self.last_activity_time = current_time
        self.last_interaction_type = 'user_input'

        # 用户互动增加少量舒适度
        self.comfort_level = min(100.0, self.comfort_level + 2.0)

        self._update_state()

    def _on_user_input_processed(self, event: Event):
        """处理用户输入处理完成事件"""
        # 处理完成，轻微情绪消耗
        self.emotion_drain += 0.5
        self._update_state()

    def _on_thinking_started(self, event: Event):
        """处理思考开始事件"""
        print("[AffectiveState] 思考开始")
        self.last_activity_time = time.time()
        self.last_interaction_type = 'thinking'

    def _on_thinking_completed(self, event: Event):
        """处理思考完成事件"""
        reply_count = event.data.get('reply_count', 1)
        print(f"[AffectiveState] 思考完成，回复数: {reply_count}")

        # 根据思考复杂度和回复数增加情绪消耗
        self.emotion_drain += reply_count * 0.8

        self._update_state()

    def _on_tts_requested(self, event: Event):
        """处理TTS请求事件"""
        # TTS合成消耗少量资源
        self.emotion_drain += 0.1

    def _on_tts_completed(self, event: Event):
        """处理TTS完成事件"""
        # 完成表达，轻微舒适度恢复
        self.comfort_level = min(100.0, self.comfort_level + 0.5)
        self._update_state()

    def _on_idle_monologue(self, event: Event):
        """处理空闲独白事件"""
        event_type = event.data.get('type', 'text')
        print(f"[AffectiveState] 空闲独白触发: {event_type}")

        # 空闲独白减少重复感
        self.repetition_boredom = max(0.0, self.repetition_boredom - 1.0)

        # 发呆恢复舒适度
        self.comfort_level = min(100.0, self.comfort_level + 3.0)

        self._update_state()

    def _update_state(self):
        """更新内在状态"""
        # 计算总舒适度影响
        comfort_impact = 0.0

        # 专注时长消耗舒适度（每10分钟消耗5点）
        comfort_impact -= (self.focus_duration / 10.0) * 5.0

        # 情绪消耗直接影响舒适度
        comfort_impact -= self.emotion_drain * 2.0

        # 重复感降低舒适度
        comfort_impact -= self.repetition_boredom * 1.5

        # 随时间轻微恢复（每分钟恢复0.1点）
        current_time = time.time()
        idle_time = (current_time - self.last_activity_time) / 60.0  # 分钟
        comfort_impact += idle_time * 0.1

        # 随机小扰动（±0.5）
        import random
        comfort_impact += random.uniform(-0.5, 0.5)

        # 更新舒适度
        old_comfort = self.comfort_level
        self.comfort_level = max(0.0, min(100.0, self.comfort_level + comfort_impact))

        # 检查阈值触发
        if old_comfort >= self.comfort_threshold_low and self.comfort_level < self.comfort_threshold_low:
            self._on_comfort_low()
        elif old_comfort <= self.comfort_threshold_high and self.comfort_level > self.comfort_threshold_high:
            self._on_comfort_high()

        # 逐渐衰减状态
        self.emotion_drain *= 0.95  # 情绪消耗逐渐衰减
        self.repetition_boredom = max(0.0, self.repetition_boredom - 0.1)  # 重复感逐渐减少

        # 打印状态更新
        if abs(old_comfort - self.comfort_level) > 1.0:
            print(f"[AffectiveState] 舒适度: {old_comfort:.1f} → {self.comfort_level:.1f} "
                  f"(专注: {self.focus_duration:.1f}min, 情绪消耗: {self.emotion_drain:.1f}, "
                  f"重复感: {self.repetition_boredom:.1f})")

    def _on_comfort_low(self):
        """舒适度过低触发"""
        print(f"⚠️ [AffectiveState] 舒适度过低 ({self.comfort_level:.1f})，触发逃离当前状态的本能")

        # 发布舒适度过低事件
        event_bus.publish(
            EventType.INSTINCT_TRIGGERED,
            source="AffectiveStateExample._on_comfort_low",
            instinct_type="escape_current_state",
            comfort_level=self.comfort_level,
            timestamp=time.time()
        )

    def _on_comfort_high(self):
        """舒适度过高触发"""
        print(f"🎉 [AffectiveState] 舒适度过高 ({self.comfort_level:.1f})，触发主动做事的本能")

        # 发布舒适度过高事件
        event_bus.publish(
            EventType.INSTINCT_TRIGGERED,
            source="AffectiveStateExample._on_comfort_high",
            instinct_type="initiate_activity",
            comfort_level=self.comfort_level,
            timestamp=time.time()
        )

    def get_state(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            "comfort_level": self.comfort_level,
            "focus_duration": self.focus_duration,
            "emotion_drain": self.emotion_drain,
            "repetition_boredom": self.repetition_boredom,
            "last_interaction_type": self.last_interaction_type,
            "time_since_last_activity": time.time() - self.last_activity_time
        }


# 使用装饰器的事件处理器示例
@event_handler([
    EventType.ACTIVITY_STARTED,
    EventType.ACTIVITY_ENDED,
    EventType.COMFORT_UPDATED
])
def log_affective_events(event: Event):
    """记录情感相关事件（示例）"""
    print(f"📊 [AffectiveEvent] {event.event_type.value}: {event.data}")


def create_affective_state() -> AffectiveStateExample:
    """
    创建舒适度模型实例

    使用示例：
        affective_state = create_affective_state()
        # 舒适度模型会自动订阅事件并更新状态
    """
    return AffectiveStateExample()


if __name__ == "__main__":
    # 示例：创建舒适度模型并演示事件处理
    print("=== 舒适度模型集成示例 ===")

    # 创建舒适度模型
    affective_state = AffectiveStateExample()

    # 模拟一些事件
    print("\n=== 模拟事件流 ===")

    # 模拟用户输入
    from event_bus import create_event
    user_input_event = create_event(
        EventType.USER_INPUT_RECEIVED,
        source="test",
        text="你好，今天天气怎么样？"
    )
    event_bus.publish_event(user_input_event)

    # 模拟思考完成
    thinking_complete_event = create_event(
        EventType.THINKING_COMPLETED,
        source="test",
        reply_count=3
    )
    event_bus.publish_event(thinking_complete_event)

    # 模拟TTS完成
    tts_complete_event = create_event(
        EventType.TTS_COMPLETED,
        source="test",
        text="今天天气很好",
        emotion="happy"
    )
    event_bus.publish_event(tts_complete_event)

    # 显示最终状态
    print(f"\n=== 最终状态 ===")
    state = affective_state.get_state()
    for key, value in state.items():
        print(f"{key}: {value}")