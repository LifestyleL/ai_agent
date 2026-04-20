import asyncio
import logging
from backend.core.state_machine.state_machine import StateMachine, State, Event

logger = logging.getLogger(__name__)

def create_think_action(driver_instance: any, state_machine: StateMachine):
    """
    工厂函数：生成 THINK 状态的 Action。
    传入原有的 driver 实例和状态机实例，形成闭包。
    """
    async def action_think(context: dict):
        user_input = context.get("user_input", "")
        logger.info(f"[Action] 进入 THINK 状态，准备执行原有逻辑，输入: {user_input[:20]}...")
        logger.info(f"[FSM Action] Enter THINK state, will execute original logic, input: {user_input[:20]}...")

        try:
            # 【关键点】使用 asyncio.to_thread 在后台线程执行同步的 handle_user_input
            # 这样既不改动原函数，又不会阻塞 WebSocket 的异步事件循环
            if hasattr(driver_instance, 'handle_user_input'):
                logger.info(f"[FSM Action] Calling driver.handle_user_input via asyncio.to_thread")
                await asyncio.to_thread(driver_instance.handle_user_input, user_input)
                logger.info(f"[FSM Action] driver.handle_user_input completed")
            else:
                logger.error(f"[Action] driver_instance 缺少 handle_user_input 方法！")
                logger.error(f"[FSM Action] driver_instance missing handle_user_input method!")

            logger.info("[Action] 原有逻辑执行完毕，触发 TASK_COMPLETE 回到 IDLE")
            logger.info("[FSM Action] Original logic completed, triggering TASK_COMPLETE to return to IDLE")
            await state_machine.trigger(Event.TASK_COMPLETE)

        except Exception as e:
            logger.error(f"[Action] 原有逻辑执行报错: {e}", exc_info=True)
            logger.error(f"[FSM Action] Original logic error: {e}", exc_info=True)
            await state_machine.trigger(Event.ERROR, {"error": str(e)})

    return action_think