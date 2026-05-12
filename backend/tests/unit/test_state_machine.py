"""状态转移完整性测试"""

import pytest
import asyncio
from backend.core.state_machine.state_machine import (
    StateMachine, State, Event,
)


class TestStateMachine:
    """StateMachine 核心功能"""

    def test_initial_state_is_idle(self):
        sm = StateMachine()
        assert sm.current_state == State.IDLE

    def test_register_transition_and_trigger(self):
        sm = StateMachine()
        sm.register_transition(State.IDLE, Event.USER_INPUT, State.THINK)

        async def _trigger():
            await sm.trigger(Event.USER_INPUT, {})

        asyncio.run(_trigger())
        assert sm.current_state == State.THINK

    def test_no_transition_stays_in_state(self):
        sm = StateMachine()
        initial = sm.current_state

        async def _trigger():
            await sm.trigger(Event.USER_INPUT, {})

        asyncio.run(_trigger())
        assert sm.current_state == initial  # no transition defined

    def test_all_states_defined(self):
        expected = {"IDLE", "THINK", "ASK_USER", "DO_TOOL", "WAIT_CONFIRM", "FINISH"}
        for name in expected:
            assert hasattr(State, name), f"Missing state: {name}"

    def test_all_events_defined(self):
        expected = {
            "USER_INPUT", "TASK_COMPLETE", "TOOL_RETURN",
            "SPONTANEOUS_TRIGGER", "ERROR", "NEED_TOOL",
        }
        for name in expected:
            assert hasattr(Event, name), f"Missing event: {name}"

    def test_register_action(self):
        sm = StateMachine()
        called = []

        async def dummy_action(ctx):
            called.append(True)

        sm.register_action(State.THINK, dummy_action)
        assert State.THINK.value in sm._actions
        assert sm._actions[State.THINK.value] is dummy_action
