import asyncio
import websockets
import json
import time
import random
from datetime import datetime

connection_start_time = None


# 🧠 Live2D决策核心（唯一控制入口）
def live2d_decide(text: str):
    data = {
        "text": text,
        "expression": "Neutral",
        "motion": None
    }

    # 情绪判断
    if any(k in text for k in ["哈哈", "开心", "笑"]):
        data["expression"] = "Smile"
        data["motion"] = {
            "group": "TapBody",
            "index": random.randint(0, 1)
        }

    elif any(k in text for k in ["生气", "烦", "不爽"]):
        data["expression"] = "Angry"
        data["motion"] = {
            "group": "TapBody",
            "index": 0
        }

    elif any(k in text for k in ["难过", "伤心", "哭"]):
        data["expression"] = "Sad"

    else:
        data["expression"] = "Neutral"

    return data


def get_timestamp():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


# 🧠 Agent（只负责“思考”）
async def agent_logic(user_input):
    print(f"   ⏳ [{get_timestamp()}] Agent 正在思考...")

    think_time = random.uniform(0.5, 2.0)
    await asyncio.sleep(think_time)

    print(f"   ✅ [{get_timestamp()}] Agent 思考完毕 (耗时: {think_time:.2f}s)")

    # 模拟AI回复文本
    ai_text = f"我收到了：'{user_input}'，让我想想该怎么回应你～"

    # 🔥 关键：统一走 live2d_decide
    result = live2d_decide(ai_text)

    return result


# 🔗 WebSocket处理
async def handle_client(websocket):
    global connection_start_time
    conn_id = id(websocket)
    connection_start_time = time.time()

    print("="*50)
    print(f"🔗 [{get_timestamp()}] 新客户端连接成功! (ID: {conn_id})")
    print("="*50)

    try:
        async for message in websocket:
            recv_time = time.time()

            data = json.loads(message)
            user_input = data.get("text", "")

            print(f"\n📥 [{get_timestamp()}] 收到消息: '{user_input}'")

            # 🧠 AI处理
            response_data = await agent_logic(user_input)

            send_time = time.time()
            process_duration = send_time - recv_time

            # 📤 发送给前端
            await websocket.send(json.dumps(response_data))

            print(f"📤 [{get_timestamp()}] 回复已发送 (耗时: {process_duration:.2f}s)")
            print(f"   📝 文本: {response_data['text']}")
            print(f"   🎭 表情: {response_data['expression']}")
            print(f"   🏃 动作: {response_data['motion']}")
            print("-" * 30)

    except websockets.exceptions.ConnectionClosed as e:
        duration = time.time() - connection_start_time
        print(f"\n❌ [{get_timestamp()}] 客户端断开连接 (原因: {e})")
        print(f"⏱️  会话时长: {duration:.2f} 秒")
        print("="*50)


# 🚀 启动服务
async def main():
    host = "localhost"
    port = 8765

    print(f"🚀 启动 WebSocket 服务")
    print(f"📡 ws://{host}:{port}")
    print(f"⏰ {get_timestamp()}")
    print("(Ctrl+C 退出)\n")

    try:
        async with websockets.serve(handle_client, host, port):
            await asyncio.Future()
    except KeyboardInterrupt:
        print("\n🛑 服务已停止")


if __name__ == "__main__":
    asyncio.run(main())