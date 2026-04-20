import asyncio
import logging
from backend.core.state_machine.state_machine import StateMachine, State, Event

logger = logging.getLogger(__name__)

def create_think_action(driver_instance: any, state_machine: StateMachine):
    """
    工厂函数：生成 THINK 状态的 Action。
    传入原有的 driver 实例和状态机实例，形成闭包。
    """
    print(f"[FSM Action Factory] 创建 THINK Action, driver_instance: {driver_instance}, state_machine: {state_machine}")

    async def action_think(context: dict):
        user_input = context.get("user_input", "")
        print(f"[FSM Action] 进入 THINK 状态，准备执行原有逻辑，输入: {user_input[:20]}...")

        try:
            # 【关键点】使用 asyncio.to_thread 在后台线程执行同步的 handle_user_input
            # 这样既不改动原函数，又不会阻塞 WebSocket 的异步事件循环
            if hasattr(driver_instance, 'handle_user_input'):
                print(f"[FSM Action] 通过 asyncio.to_thread 调用 driver.handle_user_input")
                await asyncio.to_thread(driver_instance.handle_user_input, user_input)
                print(f"[FSM Action] driver.handle_user_input 执行完成")
            else:
                print(f"[FSM Action] 错误: driver_instance 缺少 handle_user_input 方法！")

            print("[FSM Action] 原有逻辑执行完毕，触发 TASK_COMPLETE 回到 IDLE")
            await state_machine.trigger(Event.TASK_COMPLETE)

        except Exception as e:
            print(f"[FSM Action] 错误: 原有逻辑执行报错: {e}")
            await state_machine.trigger(Event.ERROR, {"error": str(e)})

    print(f"[FSM Action Factory] Action 函数创建完成: {action_think}")
    return action_think