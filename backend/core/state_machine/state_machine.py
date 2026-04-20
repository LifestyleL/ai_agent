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

class StateMachine:
    """标准有限状态机 (FSM)"""

    def __init__(self):
        self.current_state: State = State.IDLE
        self._transitions: Dict[tuple, State] = {}  # (State, Event) -> State
        self._actions: Dict[State, Callable] = {}    # State -> Action Func
        self.logger = logging.getLogger(__name__)

        # --- 兼容旧代码的计数器（非核心逻辑，仅作属性挂载） ---
        self.tool_usage_count: Dict[str, int] = {}
        self.current_step: int = 0
        self.max_steps: int = 8

    def register_transition(self, from_state: State, event: Event, to_state: State):
        """注册状态转移规则"""
        self._transitions[(from_state, event)] = to_state

    def register_action(self, state: State, action: Callable):
        """注册进入某状态时执行的 Action"""
        self._actions[state] = action

    async def trigger(self, event: Event, context: Optional[Dict[str, Any]] = None):
        """触发事件，驱动状态机流转"""
        context = context or {}
        key = (self.current_state, event)

        if key not in self._transitions:
            self.logger.warning(f"[FSM] 未定义的转移: 当前[{self.current_state.name}] + 事件[{event.name}]")
            return

        next_state = self._transitions[key]
        self.logger.info(f"[FSM] 转移: {self.current_state.name} --[{event.name}]--> {next_state.name}")
        self.logger.info(f"[FSM] Transition: {self.current_state.name} --[{event.name}]--> {next_state.name}")

        # 执行目标状态的 Action
        if next_state in self._actions:
            try:
                await self._actions[next_state](context)
            except Exception as e:
                self.logger.error(f"[FSM] 执行 Action [{next_state.name}] 出错: {e}")

        # 更新状态
        self.current_state = next_state

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