import asyncio
import websockets
import json

async def control_live2d():
    uri = "ws://localhost:5001"
    try:
        async with websockets.connect(uri) as websocket:
            print("✅ Connected to bridge server")
            
            # 注册为 Python 客户端
            await websocket.send(json.dumps({
                "type": "register",
                "client": "python"
            }))
            
            # 等待注册确认
            response = await websocket.recv()
            print(f"📨 Bridge response: {response}")
            
            # 测试1：让模型说话
            print("\n📢 Test 1: Make model talk (3 seconds)")
            await websocket.send(json.dumps({
                "type": "talk",
                "isTalking": True
            }))
            await asyncio.sleep(3)
            
            await websocket.send(json.dumps({
                "type": "talk",
                "isTalking": False
            }))
            await asyncio.sleep(1)
            
            # 测试2：随机表情
            print("\n😊 Test 2: Random expression")
            await websocket.send(json.dumps({
                "type": "expression"
            }))
            await asyncio.sleep(1.5)
            
            # 测试3：播放动作
            print("\n🎬 Test 3: Play motion from TapBody group")
            await websocket.send(json.dumps({
                "type": "randomMotion",
                "group": "TapBody",
                "priority": 1
            }))
            await asyncio.sleep(2)
            
            print("\n✅ All tests completed")
            
    except Exception as e:
        print(f"❌ Connection error: {e}")
        print("Make sure the bridge server is running: node bridge_server.js")

if __name__ == "__main__":
    asyncio.run(control_live2d())