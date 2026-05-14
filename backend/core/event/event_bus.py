"""
事件总线系统：用于模块间解耦通信

提供简单、线程安全的事件发布/订阅机制，支持同步事件处理。
便于后续扩展舒适度模型、监控、日志等模块。
"""

import threading
import time
from enum import Enum
from typing import Dict, List, Callable, Any, Optional, Union
from dataclasses import dataclass, field
import uuid


# ==================== 事件类型枚举 ====================

class EventType(Enum):
    """系统事件类型枚举"""

    # 用户交互事件
    USER_INPUT_RECEIVED = "user_input_received"          # 收到用户输入
    USER_INPUT_PROCESSED = "user_input_processed"        # 用户输入处理完成

    # AI思考事件
    THINKING_STARTED = "thinking_started"                # 开始思考
    THINKING_INTERMEDIATE = "thinking_intermediate"      # 中间思考步骤
    THINKING_COMPLETED = "thinking_completed"            # 思考完成

    # 语音合成事件
    TTS_REQUESTED = "tts_requested"                      # 请求语音合成
    TTS_STARTED = "tts_started"                          # 语音合成开始
    TTS_COMPLETED = "tts_completed"                      # 语音合成完成
    TTS_FAILED = "tts_failed"                            # 语音合成失败

    # 记忆事件
    MEMORY_LOADED = "memory_loaded"                      # 记忆加载
    MEMORY_UPDATED = "memory_updated"                    # 记忆更新
    MEMORY_SEARCHED = "memory_searched"                  # 记忆搜索

    # 情感状态事件（为舒适度模型预留）
    COMFORT_UPDATED = "comfort_updated"                  # 舒适度更新
    ACTIVITY_STARTED = "activity_started"                # 活动开始
    ACTIVITY_ENDED = "activity_ended"                    # 活动结束
    INSTINCT_TRIGGERED = "instinct_triggered"            # 本能触发

    # 任务事件
    TASK_STARTED = "task_started"                        # 任务开始
    TASK_PROGRESS = "task_progress"                      # 任务进度
    TASK_COMPLETED = "task_completed"                    # 任务完成
    TASK_FAILED = "task_failed"                          # 任务失败

    # 系统状态事件
    AGENT_STARTED = "agent_started"                      # Agent启动
    AGENT_STOPPED = "agent_stopped"                      # Agent停止
    IDLE_MONOLOGUE_TRIGGERED = "idle_monologue_triggered"  # 空闲独白触发
    ERROR_OCCURRED = "error_occurred"                    # 错误发生

    # 工具调用事件
    TOOL_CALLED = "tool_called"                          # 工具调用
    TOOL_RESULT_RECEIVED = "tool_result_received"        # 工具结果返回

    # AI内在驱动事件（新增）
    SUBCONSCIOUS_ACTION = "subconscious_action"          # 潜意识嘟囔动作
    SPONTANEOUS_ACTION_TRIGGERED = "spontaneous_action_triggered"  # 自驱力触发动作
    DISCOVERY_MADE = "discovery_made"                    # 发现新知识
    SURFING_REVIEW_NEEDED = "surfing_review_needed"      # 冲浪回顾需求

    # TTS 打断 & ASR 事件
    TTS_INTERRUPTED = "tts_interrupted"                  # TTS 播报被打断
    ASR_RESULT = "asr_result"                            # ASR 识别到最终结果

    # 外部适配器事件（QQ / Telegram 等）
    RESPONSE_READY = "response_ready"                    # AI 回复就绪，携带 response_text + session_id


# ==================== 事件数据结构 ====================

@dataclass
class Event:
    """事件数据类"""
    event_type: EventType
    timestamp: float
    source: str
    data: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于日志/序列化）"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "source": self.source,
            "data": self.data
        }

    def __str__(self) -> str:
        return f"Event({self.event_type.value}, source={self.source}, time={time.strftime('%H:%M:%S', time.localtime(self.timestamp))})"


# ==================== 事件处理器 ====================

class EventHandler:
    """事件处理器基类"""

    def __init__(self, callback: Callable[[Event], None], priority: int = 0):
        """
        初始化事件处理器

        Args:
            callback: 事件处理回调函数
            priority: 处理优先级（数字越大，优先级越高）
        """
        self.callback = callback
        self.priority = priority
        self.handler_id = str(uuid.uuid4())

    def handle(self, event: Event) -> None:
        """处理事件"""
        try:
            self.callback(event)
        except Exception as e:
            print(f"[EventBus] 事件处理失败: {e}, handler_id={self.handler_id}, event={event}")


# ==================== 事件总线 ====================

class EventBus:
    """
    事件总线：单例模式，全局事件分发中心
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 防止重复初始化
        if hasattr(self, '_initialized') and self._initialized:
            return

        # 事件处理器映射：event_type -> List[EventHandler]
        self._handlers: Dict[EventType, List[EventHandler]] = {}

        # 事件历史记录（用于调试）
        self._event_history: List[Event] = []
        self._max_history = 1000

        # 线程锁
        self._lock = threading.RLock()

        # 统计信息
        self._stats = {
            "events_published": 0,
            "events_handled": 0,
            "handlers_registered": 0
        }

        self._initialized = True
        print("[EventBus] 事件总线初始化完成")

    # ==================== 公共接口 ====================

    def subscribe(
        self,
        event_type: Union[EventType, List[EventType]],
        callback: Callable[[Event], None],
        priority: int = 0
    ) -> str:
        """
        订阅事件

        Args:
            event_type: 事件类型或类型列表
            callback: 事件处理回调函数
            priority: 处理优先级（数字越大，优先级越高）

        Returns:
            处理器ID（用于取消订阅）
        """
        with self._lock:
            handler = EventHandler(callback, priority)

            # 处理单个或多个事件类型
            if isinstance(event_type, list):
                event_types = event_type
            else:
                event_types = [event_type]

            for et in event_types:
                if et not in self._handlers:
                    self._handlers[et] = []

                # 按优先级插入（优先级高的在前面）
                handlers = self._handlers[et]
                inserted = False
                for i, h in enumerate(handlers):
                    if priority > h.priority:
                        handlers.insert(i, handler)
                        inserted = True
                        break

                if not inserted:
                    handlers.append(handler)

                self._stats["handlers_registered"] += 1

            print(f"[EventBus] 订阅事件: {[et.value for et in event_types]}, handler_id={handler.handler_id}")
            return handler.handler_id

    def unsubscribe(self, handler_id: str) -> bool:
        """
        取消订阅

        Args:
            handler_id: 处理器ID

        Returns:
            是否成功取消
        """
        with self._lock:
            for event_type, handlers in self._handlers.items():
                for i, handler in enumerate(handlers):
                    if handler.handler_id == handler_id:
                        handlers.pop(i)
                        print(f"[EventBus] 取消订阅: {event_type.value}, handler_id={handler_id}")
                        return True
            return False

    def publish(self, event_type: EventType, source: str, **data) -> Event:
        """
        发布事件

        Args:
            event_type: 事件类型
            source: 事件源标识
            **data: 事件数据

        Returns:
            创建的事件对象
        """
        with self._lock:
            # 创建事件
            event = Event(
                event_type=event_type,
                timestamp=time.time(),
                source=source,
                data=data
            )

            # 添加到历史记录
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history.pop(0)

            # 更新统计
            self._stats["events_published"] += 1

            # 查找并调用处理器
            handlers = self._handlers.get(event_type, [])
            if not handlers:
                # 如果没有处理器，记录但跳过
                print(f"[EventBus] 事件发布但无处理器: {event}")
                return event

            print(f"[EventBus] 发布事件: {event}, 处理器数量: {len(handlers)}")

            # 调用所有处理器（按优先级顺序）
            for handler in handlers:
                try:
                    handler.handle(event)
                    self._stats["events_handled"] += 1
                except Exception as e:
                    print(f"[EventBus] 事件处理异常: {e}, handler_id={handler.handler_id}")

            return event

    def publish_event(self, event: Event) -> Event:
        """
        直接发布事件对象（高级用法）

        Args:
            event: 事件对象

        Returns:
            事件对象（与输入相同）
        """
        with self._lock:
            # 添加到历史记录
            self._event_history.append(event)
            if len(self._event_history) > self._max_history:
                self._event_history.pop(0)

            # 更新统计
            self._stats["events_published"] += 1

            # 查找并调用处理器
            handlers = self._handlers.get(event.event_type, [])
            if not handlers:
                return event

            print(f"[EventBus] 发布事件对象: {event}, 处理器数量: {len(handlers)}")

            # 调用所有处理器
            for handler in handlers:
                try:
                    handler.handle(event)
                    self._stats["events_handled"] += 1
                except Exception as e:
                    print(f"[EventBus] 事件处理异常: {e}")

            return event

    # ==================== 查询接口 ====================

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return self._stats.copy()

    def get_recent_events(self, limit: int = 20) -> List[Event]:
        """获取最近的事件"""
        with self._lock:
            return self._event_history[-limit:] if self._event_history else []

    def get_event_count(self, event_type: Optional[EventType] = None) -> int:
        """获取事件数量"""
        with self._lock:
            if event_type:
                return sum(1 for e in self._event_history if e.event_type == event_type)
            return len(self._event_history)

    def has_handlers(self, event_type: EventType) -> bool:
        """检查是否有事件处理器"""
        with self._lock:
            return len(self._handlers.get(event_type, [])) > 0

    def clear_handlers(self, event_type: Optional[EventType] = None):
        """清除事件处理器"""
        with self._lock:
            if event_type:
                if event_type in self._handlers:
                    count = len(self._handlers[event_type])
                    self._handlers[event_type] = []
                    print(f"[EventBus] 清除 {event_type.value} 的 {count} 个处理器")
            else:
                count = sum(len(h) for h in self._handlers.values())
                self._handlers = {}
                print(f"[EventBus] 清除所有 {count} 个处理器")

    # ==================== 工具函数 ====================

    def wait_for_event(
        self,
        event_type: EventType,
        timeout: float = 10.0,
        condition: Optional[Callable[[Event], bool]] = None
    ) -> Optional[Event]:
        """
        等待特定事件（同步阻塞）

        Args:
            event_type: 等待的事件类型
            timeout: 超时时间（秒）
            condition: 可选的条件函数，只有满足条件的事件才会返回

        Returns:
            事件对象（如果超时则返回None）
        """
        event_received = None
        event_received_lock = threading.Lock()
        event_received_cv = threading.Condition(event_received_lock)

        def handler(event: Event):
            nonlocal event_received
            if condition and not condition(event):
                return

            with event_received_cv:
                event_received = event
                event_received_cv.notify_all()

        # 临时订阅
        handler_id = self.subscribe(event_type, handler)

        try:
            with event_received_cv:
                if not event_received_cv.wait(timeout):
                    print(f"[EventBus] 等待事件超时: {event_type.value}")
                    return None
                return event_received
        finally:
            self.unsubscribe(handler_id)


# ==================== 全局事件总线实例 ====================

# 全局事件总线单例
event_bus = EventBus()


# ==================== 装饰器工具 ====================

def event_handler(event_type: Union[EventType, List[EventType]], priority: int = 0):
    """
    事件处理器装饰器

    示例:
        @event_handler(EventType.USER_INPUT_RECEIVED)
        def handle_user_input(event: Event):
            print(f"收到用户输入: {event.data.get('text')}")
    """
    def decorator(func: Callable[[Event], None]):
        # 自动注册到全局事件总线
        event_bus.subscribe(event_type, func, priority)
        return func
    return decorator


def event_publisher(source: str):
    """
    事件发布者装饰器（用于类方法）

    示例:
        class MyClass:
            @event_publisher("MyClass")
            def do_something(self, text: str):
                # 方法执行后会自动发布事件
                return {"result": "success"}
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # 提取事件类型（从方法名映射）
            method_name = func.__name__
            event_type_map = {
                "handle_user_input": EventType.USER_INPUT_PROCESSED,
                "speak": EventType.TTS_REQUESTED,
                "collaborate": EventType.THINKING_STARTED,
                # 可以根据需要添加更多映射
            }

            event_type = event_type_map.get(method_name)

            # 执行原方法
            result = func(*args, **kwargs)

            # 发布事件（如果有对应的事件类型）
            if event_type:
                # 确定source：如果args[0]有__class__，使用类名
                actual_source = source
                if args and hasattr(args[0], '__class__'):
                    actual_source = f"{args[0].__class__.__name__}.{method_name}"

                event_bus.publish(event_type, actual_source, result=result, args=args, kwargs=kwargs)

            return result
        return wrapper
    return decorator


# ==================== 工具函数 ====================

def create_event(
    event_type: EventType,
    source: str,
    **data
) -> Event:
    """快速创建事件"""
    return Event(
        event_type=event_type,
        timestamp=time.time(),
        source=source,
        data=data
    )


def print_event_summary(event: Event) -> None:
    """打印事件摘要（用于调试）"""
    print(f"[Event] {event.event_type.value} from {event.source}")
    if event.data:
        for key, value in event.data.items():
            if isinstance(value, str) and len(value) > 100:
                print(f"  {key}: {value[:100]}...")
            else:
                print(f"  {key}: {value}")


# ==================== 默认事件处理器 ====================

def setup_default_event_handlers():
    """设置默认事件处理器（用于调试和监控）"""

    @event_handler([
        EventType.ERROR_OCCURRED,
        EventType.TTS_FAILED,
        EventType.THINKING_COMPLETED
    ], priority=10)
    def log_important_events(event: Event):
        """记录重要事件"""
        print(f"[EventLog] {event.event_type.value}: {event.data.get('message', '')}")

    @event_handler(EventType.USER_INPUT_RECEIVED)
    def log_user_input(event: Event):
        """记录用户输入"""
        text = event.data.get('text', '')
        print(f"[UserInput] {text[:50]}{'...' if len(text) > 50 else ''}")

    print("[EventBus] 默认事件处理器已设置")


# 自动设置默认处理器
setup_default_event_handlers()