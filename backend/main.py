# main.py
import asyncio
import sys
import os
import signal
import threading
import time

# 确保项目根目录在sys.path中，以便使用绝对导入
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from api.netwebsocket.ws_server import WSServer
from config import WS_PORT, validate_config, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from core.state_machine.state_machine import get_state_machine, State, Event
from core.state_machine.transitions import setup_base_transitions
from core.state_machine.actions import create_real_think_action, create_real_do_tool_action
from backend.plugins.registry import get_global_registry
from core.llm.llm_api import LLMAPI
from backend.plugins.builtin.adapters import SearchMemoryAdapter, WriteFileAdapter, ReadFileAdapter, SummarizeArchiveAdapter, WriteDiaryAdapter

ws_instance = WSServer()
_shutdown_requested = False

async def main():
    global _shutdown_requested

    # 启动时验证配置
    validate_config()

    # 统一创建 LLM API 实例（单模型 DeepSeek，状态机 Action 注入使用）
    llm_deepseek = LLMAPI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL, model=DEEPSEEK_MODEL)

    print("="*50)
    print("[1] [主线程] 准备拉起 Agent 后台线程...")
    print("="*50)
    try:
        from core.agent.agent_driver import YumeDriver
        driver = YumeDriver()
        ws_instance.driver = driver

        # 配置状态机转移规则和Action（真实引擎模式）
        print("[Main] 配置状态机（真实引擎模式）...")
        sm = get_state_machine()
        setup_base_transitions(sm)

        # 工具系统插件化注册
        print("[Main] 工具系统插件化注册...")
        reg = get_global_registry()
        reg.register(SearchMemoryAdapter())
        reg.register(WriteFileAdapter())
        reg.register(ReadFileAdapter())
        reg.register(SummarizeArchiveAdapter())
        reg.register(WriteDiaryAdapter())
        # 将注册中心实例挂载到 driver 上（备用）
        driver.tool_registry = reg
        print(f"[Main] 工具注册完成，已注册 {len(reg.get_all_tools())} 个工具")

        # 绑定真实 Action 引擎
        print("[Main] 绑定真实 Action 引擎...")
        real_think = create_real_think_action(state_machine=sm, registry=reg, driver_instance=driver, llm_deepseek=llm_deepseek)
        real_do_tool = create_real_do_tool_action(state_machine=sm, registry=reg, llm_deepseek=llm_deepseek)
        sm.register_action(State.THINK, real_think)
        sm.register_action(State.DO_TOOL, real_do_tool)
        print("[Main] 真实 Action 绑定完成")

        # 将状态机挂载到driver实例
        driver.state_machine = sm
        print("[Main] 状态机配置完成")

        # 调试：打印状态机转移规则
        print(f"[Main] 状态机ID: {id(sm)}")
        print(f"[Main] 状态机transitions数量: {len(sm._transitions)}")
        for (from_sv, ev), to_state in sm._transitions.items():
            print(f"[Main] 转移: {from_sv} + {ev} -> {to_state.name}")

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
    stdin_stop = threading.Event()

    def stdin_loop():
        print()
        print("[CHAT] ================================")
        print("[CHAT]   在这里直接打字按回车即可对话")
        print("[CHAT] ================================")
        print()
        while not stdin_stop.is_set():
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

    # ─── 信号处理：一次 Ctrl+C 优雅退出 ───
    shutdown_event = asyncio.Event()

    def _on_signal(signum, frame):
        global _shutdown_requested
        if _shutdown_requested:
            return
        _shutdown_requested = True
        print("\n[STOP] 收到退出信号，正在优雅关闭...")
        loop.call_soon_threadsafe(shutdown_event.set)

    # 注册信号（TTS 的 signal handler 已在子线程中注册，这里只在主线程生效）
    try:
        signal.signal(signal.SIGINT, _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)
    except ValueError:
        pass  # 非主线程时忽略

    # 等待关闭信号或服务结束
    await shutdown_event.wait()

    # ─── 优雅关闭流程（每步带超时，防止卡死） ───
    print("[STOP] 正在关闭 WebSocket 服务...")
    try:
        server.close()
        await asyncio.wait_for(server.wait_closed(), timeout=3)
    except (asyncio.TimeoutError, Exception) as e:
        print(f"[STOP] WebSocket 关闭: {e}")

    print("[STOP] 正在停止终端输入...")
    stdin_stop.set()

    print("[STOP] 正在停止 Agent...")
    try:
        await asyncio.wait_for(asyncio.to_thread(driver.shutdown), timeout=8)
    except (asyncio.TimeoutError, Exception) as e:
        print(f"[STOP] Agent 停止: {e}")

    # 取消所有待处理任务（不带 gather，直接 cancel）
    tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task()]
    for t in tasks:
        t.cancel()
    # 不 await gather：被 cancel 的 task 可能挂，直接放过

    print("[OK] 系统已关闭")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[STOP] 系统已关闭")







# 想改思考逻辑？ → 只动 agent_brain.py
# 想改独白语气？ → 只动 agent_voice.py
# 想改几秒触发？ → 只动 agent_driver.py 里的 IDLE_TIMEOUT
# 看入口在哪？   → 打开 main.py 一眼就看到
