#!/usr/bin/env python3
"""
状态机核心：管理Agent的内部状态

将原有的 agent_brain.py 中的状态逻辑（如 tool_usage_count、步骤计数等）
提取到独立模块，实现记忆操作与状态解耦。
"""

from typing import Dict, Any, Optional
import config


class StateMachine:
    """Agent状态机"""

    def __init__(self):
        # 工具使用计数
        self.tool_usage_count: Dict[str, int] = {}

        # 当前步骤计数
        self.current_step: int = 0

        # 最大步骤数（从配置读取）
        self.max_steps: int = config.MAX_STEPS

        # 状态标志
        self.is_thinking: bool = False
        self.is_executing_tool: bool = False

        # 其他状态可以在此扩展
        self._state_history: list = []

    def reset_for_new_round(self):
        """为新的一轮对话重置状态"""
        self.current_step = 0
        self.is_thinking = False
        self.is_executing_tool = False
        # 不清除 tool_usage_count，保持全局计数

    def increment_tool_usage(self, tool_name: str) -> int:
        """增加工具使用计数，返回当前使用次数"""
        current = self.tool_usage_count.get(tool_name, 0)
        current += 1
        self.tool_usage_count[tool_name] = current
        return current

    def get_tool_usage(self, tool_name: str) -> int:
        """获取工具使用次数"""
        return self.tool_usage_count.get(tool_name, 0)

    def increment_step(self) -> bool:
        """增加步骤计数，返回是否超过最大步骤"""
        self.current_step += 1
        return self.current_step >= self.max_steps

    def can_continue(self) -> bool:
        """检查是否可以继续执行步骤"""
        return self.current_step < self.max_steps

    def set_thinking(self, thinking: bool):
        """设置思考状态"""
        self.is_thinking = thinking

    def set_executing_tool(self, executing: bool):
        """设置工具执行状态"""
        self.is_executing_tool = executing

    def get_state_summary(self) -> Dict[str, Any]:
        """获取状态摘要"""
        return {
            "current_step": self.current_step,
            "max_steps": self.max_steps,
            "is_thinking": self.is_thinking,
            "is_executing_tool": self.is_executing_tool,
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