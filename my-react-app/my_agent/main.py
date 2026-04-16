# main.py
import asyncio
import sys
import threading
from netwebsocket.ws_server import WSServer

ws_instance = WSServer()

async def main():
    print("="*50)
    print("[1] [主线程] 准备拉起 Agent 后台线程...")
    print("="*50)
    try:
        from agent.agent_driver import YumeDriver
        driver = YumeDriver()
        ws_instance.driver = driver
        print("="*50)
        print("[2] [主线程] 启动 Agent 独白守护...")
        print("="*50)
        driver.start()
    except Exception as e:
        print(f"[ERROR] Agent 启动失败: {e}")
        sys.exit(1)

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
                    driver.handle_user_input(text.strip())
            except EOFError:
                break
            except Exception as e:
                print(f"[ERROR] 输入异常: {e}")

    threading.Thread(target=stdin_loop, daemon=True).start()

    print("="*50)
    print("[3] [主线程] 准备开启 WebSocket 8765 端口...")
    print("="*50)
    try:
        server = await ws_instance.start_server()
        print("\n[OK] 系统就绪！前端连接 ws://localhost:8765 | 终端直接打字对话\n")
    except Exception as e:
        print(f"[ERROR] WebSocket 启动失败: {e}")
        sys.exit(1)


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
