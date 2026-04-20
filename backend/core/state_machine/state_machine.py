from enum import Enum
from typing import Callable, Any, Dict, Optional
import logging

class State(Enum):
    """Agent 核心状态"""
    IDLE = "IDLE"
    THINK = "THINK"
    ASK_USER = "ASK_USER"
    DO_TOOL = "DO_TOOL"
    WAIT_CONFIRM = "WAIT_CONFIRM"
    FINISH = "FINISH"

class Event(Enum):
    """触发状态转移的事件"""
    USER_INPUT = "USER_INPUT"
    TOOL_RETURN = "TOOL_RETURN"
    TIMEOUT = "TIMEOUT"
    ERROR = "ERROR"
    USER_CANCEL = "USER_CANCEL"
    TASK_COMPLETE = "TASK_COMPLETE"
    NEED_TOOL = "NEED_TOOL"

class StateMachine:
    """标准有限状态机 (FSM)"""

    def __init__(self):
        self.current_state: State = State.IDLE
        self._transitions: Dict[str, State] = {}  # 使用字符串键: f"{from_state.value}:{event.value}" -> State
        self._actions: Dict[State, Callable] = {}    # State -> Action Func
        self.logger = logging.getLogger(__name__)

        # --- 兼容旧代码的计数器（非核心逻辑，仅作属性挂载） ---
        self.tool_usage_count: Dict[str, int] = {}
        self.current_step: int = 0
        self.max_steps: int = 8

    def register_transition(self, from_state: State, event: Event, to_state: State):
        """注册状态转移规则"""
        # 使用字符串键避免枚举实例不一致问题
        key = f"{from_state.value}:{event.value}"
        self._transitions[key] = to_state
        self.logger.info(f"[FSM] 注册转移: {from_state.name} + {event.name} -> {to_state.name} (key: {key})")
        self.logger.info(f"[FSM] Register transition: {from_state.name} + {event.name} -> {to_state.name} (key: {key})")

    def register_action(self, state: State, action: Callable):
        """注册进入某状态时执行的 Action"""
        # 使用字符串键避免枚举实例不一致问题
        key = state.value
        print(f"[FSM] 注册 Action: 状态={state.name}(value:{key}), action={action}")
        print(f"[FSM] 当前_actions字典: {list(self._actions.keys())}")
        self._actions[key] = action

    async def trigger(self, event: Event, context: Optional[Dict[str, Any]] = None):
        """触发事件，驱动状态机流转"""
        context = context or {}
        # 使用字符串键避免枚举实例不一致问题
        key = f"{self.current_state.value}:{event.value}"

        # 强制打印日志，确保可见
        print(f"[FSM] 触发检查: current_state={self.current_state.name}(value:{self.current_state.value}), event={event.name}(value:{event.value})")
        print(f"[FSM] 检查键: {key}")

        if key not in self._transitions:
            print(f"[FSM] 错误: 未定义的转移: 当前[{self.current_state.name}] + 事件[{event.name}] (key: {key})")
            # 打印所有注册的转移
            transitions_list = [f"({k})" for k in self._transitions.keys()]
            transitions_str = ", ".join(transitions_list)
            print(f"[FSM] 已注册的转移: {transitions_str}")
            return

        next_state = self._transitions[key]
        print(f"[FSM] 转移: {self.current_state.name} --[{event.name}]--> {next_state.name}")

        # 先更新状态，再执行 Action（这样 Action 内部触发事件时，current_state 已经是新状态）
        old_state = self.current_state
        self.current_state = next_state
        print(f"[FSM] 状态更新为: {self.current_state.name}")

        # 执行目标状态的 Action
        action_key = next_state.value
        if action_key in self._actions:
            try:
                print(f"[FSM] 准备执行 Action: {next_state.name}")
                await self._actions[action_key](context)
            except Exception as e:
                print(f"[FSM] 错误: 执行 Action [{next_state.name}] 出错: {e}")
                # 可选：发生错误时回滚状态？
                # self.current_state = old_state
        else:
            print(f"[FSM] 警告: 状态 {next_state.name}(key:{action_key}) 没有注册 Action")
            print(f"[FSM] 当前_actions字典: {list(self._actions.keys())}")

    # --- 以下为兼容旧代码保留的方法 ---
    def reset_for_new_round(self):
        self.current_step = 0
        self.current_state = State.IDLE

    def increment_tool_usage(self, tool_name: str) -> int:
        self.tool_usage_count[tool_name] = self.tool_usage_count.get(tool_name, 0) + 1
        return self.tool_usage_count[tool_name]

    def increment_step(self) -> bool:
        self.current_step += 1
        return self.current_step >= self.max_steps

    def get_tool_usage(self, tool_name: str) -> int:
        """获取工具使用次数"""
        return self.tool_usage_count.get(tool_name, 0)

    def can_continue(self) -> bool:
        """检查是否可以继续执行步骤"""
        return self.current_step < self.max_steps

    def set_thinking(self, thinking: bool):
        """设置思考状态"""
        # 兼容旧方法，实际应通过状态机管理
        pass

    def set_executing_tool(self, executing: bool):
        """设置工具执行状态"""
        # 兼容旧方法，实际应通过状态机管理
        pass

    def get_state_summary(self) -> Dict[str, Any]:
        """获取状态摘要"""
        return {
            "current_state": self.current_state.value,
            "current_step": self.current_step,
            "max_steps": self.max_steps,
            "tool_usage_total": sum(self.tool_usage_count.values()),
            "tool_usage_detail": self.tool_usage_count.copy()
        }

# 全局状态机实例（单例模式）
_global_state_machine: Optional[StateMachine] = None

def get_state_machine() -> StateMachine:
    """获取全局状态机实例（单例）"""
    global _global_state_machine
    if _global_state_machine is None:
        _global_state_machine = StateMachine()
    return _global_state_machine

def reset_global_state_machine():
    """重置全局状态机（用于测试或重启）"""
    global _global_state_machine
    _global_state_machine = None