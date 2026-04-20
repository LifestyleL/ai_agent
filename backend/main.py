# main.py
import asyncio
import sys
import os
import threading

# 确保项目根目录在sys.path中，以便使用绝对导入
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from api.netwebsocket.ws_server import WSServer
from config import WS_PORT
from core.state_machine.state_machine import get_state_machine, State, Event
from core.state_machine.transitions import setup_base_transitions
from core.state_machine.actions import create_real_think_action, create_real_do_tool_action
from backend.plugins.registry import get_global_registry
from backend.plugins.builtin.adapters import SearchMemoryAdapter, WriteFileAdapter

ws_instance = WSServer()

async def main():
    print("="*50)
    print("[1] [主线程] 准备拉起 Agent 后台线程...")
    print("="*50)
    try:
        from core.agent.agent_driver import YumeDriver
        driver = YumeDriver()
        ws_instance.driver = driver
        # 将driver的live2d实例挂载到ws_instance，确保引用一致
        ws_instance.live2d = driver.live2d
        print(f"[Main] Live2D管理器已挂载到ws_instance")
        # 启动Live2D管理器
        if ws_instance.live2d:
            ws_instance.live2d.start()
            print(f"[Main] Live2D管理器已启动")

        # 配置状态机转移规则和Action（真实引擎模式）
        print("[Main] 配置状态机（真实引擎模式）...")
        sm = get_state_machine()
        setup_base_transitions(sm)

        # 工具系统插件化注册
        print("[Main] 工具系统插件化注册...")
        reg = get_global_registry()
        reg.register(SearchMemoryAdapter())
        reg.register(WriteFileAdapter())
        # 将注册中心实例挂载到 driver 上（备用）
        driver.tool_registry = reg
        print(f"[Main] 工具注册完成，已注册 {len(reg.get_all_tools())} 个工具")

        # 绑定真实 Action 引擎
        print("[Main] 绑定真实 Action 引擎...")
        real_think = create_real_think_action(state_machine=sm, registry=reg, driver_instance=driver)
        real_do_tool = create_real_do_tool_action(state_machine=sm, registry=reg)
        sm.register_action(State.THINK, real_think)
        sm.register_action(State.DO_TOOL, real_do_tool)
        print("[Main] 真实 Action 绑定完成")

        # 将状态机挂载到driver实例
        driver.state_machine = sm
        print("[Main] 状态机配置完成")

        # 调试：打印状态机转移规则
        print(f"[Main] 状态机ID: {id(sm)}")
        print(f"[Main] 状态机transitions数量: {len(sm._transitions)}")
        for key, to_state in sm._transitions.items():
            # 解析字符串键: "IDLE:USER_INPUT"
            from_state_value, event_value = key.split(':')
            # 需要从值映射回枚举，简单起见直接打印原始值
            print(f"[Main] 转移: {from_state_value} + {event_value} -> {to_state.name}")

        print("="*50)
        print("[2] [主线程] 启动 Agent 独白守护...")
        print("="*50)
        driver.start()
    except Exception as e:
        print(f"[ERROR] Agent 启动失败: {e}")
        sys.exit(1)

    # 获取事件循环用于状态机触发
    loop = asyncio.get_running_loop()

    # [FIX] 终端输入线程
    def stdin_loop():
        print()
        print("[CHAT] ================================")
        print("[CHAT]   在这里直接打字按回车即可对话")
        print("[CHAT] ================================")
        print()
        while True:
            try:
                text = input("user：")
                if text.strip():
                    # 使用状态机触发用户输入事件
                    if hasattr(driver, 'state_machine'):
                        print(f"[DEBUG] driver.state_machine ID: {id(driver.state_machine)}")
                        print(f"[DEBUG] 触发事件: USER_INPUT, 当前状态: {driver.state_machine.current_state}")
                        print(f"[DEBUG] 事件循环ID: {id(loop)}")
                        coro = driver.state_machine.trigger(Event.USER_INPUT, {"user_input": text.strip()})
                        print(f"[DEBUG] 创建协程: {coro}")
                        future = asyncio.run_coroutine_threadsafe(coro, loop)
                        print(f"[DEBUG] 已调度Future: {future}")
                    else:
                        # 降级：直接调用原有逻辑（不应发生）
                        print("[DEBUG] driver没有state_machine属性，降级到原有逻辑")
                        driver.handle_user_input(text.strip())
            except EOFError:
                break
            except Exception as e:
                print(f"[ERROR] 输入异常: {e}")

    print("="*50)
    print(f"[3] [主线程] 准备开启 WebSocket {WS_PORT} 端口...")
    print("="*50)
    try:
        server = await ws_instance.start_server()
        print(f"\n[OK] 系统就绪！前端连接 ws://localhost:{WS_PORT} | 终端直接打字对话\n")
    except Exception as e:
        print(f"[ERROR] WebSocket 启动失败: {e}")
        sys.exit(1)

    threading.Thread(target=stdin_loop, daemon=True).start()


    await server.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[STOP] 系统已关闭")







# 想改思考逻辑？ → 只动 agent_brain.py
# 想改独白语气？ → 只动 agent_voice.py
# 想改几秒触发？ → 只动 agent_driver.py 里的 IDLE_TIMEOUT
# 看入口在哪？   → 打开 main.py 一眼就看到
