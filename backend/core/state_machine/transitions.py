from core.state_machine.state_machine import StateMachine, State, Event

def setup_base_transitions(sm: StateMachine):
    """配置基础的状态转移规则表"""
    print(f"[FSM Transitions] 开始配置状态机转移规则，状态机ID: {id(sm)}")
    # 用户输入时：无论在哪个状态，都进入思考
    sm.register_transition(State.IDLE, Event.USER_INPUT, State.THINK)
    sm.register_transition(State.FINISH, Event.USER_INPUT, State.THINK)
    sm.register_transition(State.ASK_USER, Event.USER_INPUT, State.THINK)

    # 工具执行完毕，回到思考（让主脑决定下一步）
    sm.register_transition(State.DO_TOOL, Event.TOOL_RETURN, State.THINK)

    # 主脑思考后，认为需要工具，跳转到 DO_TOOL
    sm.register_transition(State.THINK, Event.NEED_TOOL, State.DO_TOOL)

    # 错误处理：工具出错直接回到空闲（避免死循环）
    sm.register_transition(State.DO_TOOL, Event.ERROR, State.IDLE)

    # 超时处理
    sm.register_transition(State.ASK_USER, Event.TIMEOUT, State.IDLE)
    sm.register_transition(State.WAIT_CONFIRM, Event.TIMEOUT, State.IDLE)

    # 原有逻辑整体执行完毕（无论成功失败），回到空闲
    sm.register_transition(State.THINK, Event.TASK_COMPLETE, State.IDLE)

    # 如果执行出错，也回到空闲（兜底）
    sm.register_transition(State.THINK, Event.ERROR, State.IDLE)

    # 自驱动引擎触发主动发言：从空闲直接进入思考
    sm.register_transition(State.IDLE, Event.SPONTANEOUS_TRIGGER, State.THINK)
    # 思考中遇到自发发言：自环，不改变状态（TTS 已直接入队）
    sm.register_transition(State.THINK, Event.SPONTANEOUS_TRIGGER, State.THINK)
    # 思考中遇到用户输入：自环，处理中的输入自然结束
    sm.register_transition(State.THINK, Event.USER_INPUT, State.THINK)

    # 任务完成从 IDLE/FINISH：自环/回 IDLE（自发发言等异步路径可能触发）
    sm.register_transition(State.IDLE, Event.TASK_COMPLETE, State.IDLE)
    sm.register_transition(State.FINISH, Event.TASK_COMPLETE, State.IDLE)

    # 自驱动从 FINISH 触发
    sm.register_transition(State.FINISH, Event.SPONTANEOUS_TRIGGER, State.THINK)