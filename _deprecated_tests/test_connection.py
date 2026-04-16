#!/usr/bin/env python3
"""
测试WebSocket连接和参数传递
"""

import asyncio
import json
import websockets
from datetime import datetime

async def test_connection():
    """测试连接和参数传递"""
    print("=" * 60)
    print("测试WebSocket连接")
    print("=" * 60)
    print("请确保:")
    print("1. 主系统已运行: python main.py")
    print("2. 前端Live2D页面已打开并显示模型")
    print("=" * 60)

    try:
        # 连接到WebSocket服务器
        print("连接到 ws://localhost:8765 ...")
        websocket = await websockets.connect("ws://localhost:8765")
        print("[OK] WebSocket连接成功!")

        # 测试发送简单参数
        print("\n[测试] 发送简单参数...")
        params = {"headX": 5.0, "eyeLeft": 0.2, "eyeRight": 0.2, "mouth": 0.8}  # 更明显的值
        data = {
            "type": "PARAMS",
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "data": params
        }

        # 发送完整消息
        await websocket.send(json.dumps(data))
        print(f"发送完整消息: {json.dumps(data, indent=2)}")

        await asyncio.sleep(2)  # 更长的等待时间

        # 发送直接参数（不带type包装）
        print("\n[测试] 发送直接参数...")
        direct_params = {"headX": -5.0, "eyeLeft": 1.0, "eyeRight": 1.0, "mouth": 0.1}
        await websocket.send(json.dumps(direct_params))
        print(f"发送直接参数: {json.dumps(direct_params, indent=2)}")

        await asyncio.sleep(2)

        # 测试重置参数
        print("\n[测试] 发送重置参数...")
        reset_params = {
            "eyeLeft": 1.0,
            "eyeRight": 1.0,
            "mouth": 0.0,
            "headX": 0.0,
            "headY": 0.0,
            "headZ": 0.0,
            "bodyX": 0.0,
            "bodyY": 0.0,
            "bodyZ": 0.0,
            "hair": 0.0,
            "PartArmA": 1.0,
            "PartArmB": 0.0
        }
        await websocket.send(json.dumps(reset_params))
        print(f"发送重置参数")

        await asyncio.sleep(1)

        # 关闭连接
        await websocket.close()
        print("\n[OK] 测试完成!")
        print("\n请检查:")
        print("1. 前端浏览器控制台是否有收到消息的日志")
        print("2. Live2D模型是否响应参数变化")

        return True

    except ConnectionRefusedError:
        print("[ERROR] 连接被拒绝，请确保主系统已运行: python main.py")
        return False
    except Exception as e:
        print(f"[ERROR] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(test_connection())