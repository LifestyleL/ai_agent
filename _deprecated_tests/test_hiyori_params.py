#!/usr/bin/env python3
"""
测试Hiyori模型的直接参数控制
使用实际参数ID和极端值进行测试
"""

import asyncio
import json
import websockets
from datetime import datetime

async def test_hiyori_direct():
    """测试Hiyori模型直接参数控制"""
    print("=" * 80)
    print("测试Hiyori模型直接参数控制")
    print("=" * 80)
    print("请确保:")
    print("1. 主系统已运行: python main.py")
    print("2. 前端Live2D页面已打开并显示Hiyori模型")
    print("=" * 80)

    try:
        # 连接到WebSocket服务器
        print("连接到 ws://localhost:8765 ...")
        websocket = await websockets.connect("ws://localhost:8765")
        print("[OK] WebSocket连接成功!")

        # ============================================================================
        # 测试1：使用实际参数ID进行测试（根据Hiyori.cdi3.json）
        # ============================================================================
        print("\n[测试1] 发送实际参数ID（大幅值）...")

        # 头部参数（大幅值）
        params_1 = {
            # 头部转动
            "headX": 15.0,      # 大幅右转
            "headY": 8.0,       # 大幅上仰
            "headZ": 10.0,      # 大幅歪头

            # 眼睛
            "eyeLeft": 0.2,     # 明显眯眼
            "eyeRight": 0.2,

            # 嘴巴
            "mouth": 0.9,       # 大张嘴

            # 身体
            "bodyX": 0.8,       # 大幅侧身
            "bodyY": 0.5,       # 大幅俯仰
            "bodyZ": 0.3,       # 大幅歪转

            # 头发
            "hair": 1.0,        # 最大头发飘动

            # 手臂（使用实际参数名）
            "ParamArmLA": 0.0,  # 左臂A隐藏
            "ParamArmRA": 1.0,  # 右臂A显示
            "ParamArmLB": 0.0,  # 左臂B隐藏
            "ParamArmRB": 1.0,  # 右臂B显示
        }

        # 发送带type包装的消息
        data_1 = {
            "type": "PARAMS",
            "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "data": params_1
        }

        await websocket.send(json.dumps(data_1))
        print(f"发送大幅参数:")
        for key, value in params_1.items():
            print(f"  {key}: {value}")

        await asyncio.sleep(3)  # 等待3秒观察效果

        # ============================================================================
        # 测试2：相反方向的大幅参数
        # ============================================================================
        print("\n[测试2] 发送相反方向大幅参数...")

        params_2 = {
            "headX": -15.0,     # 大幅左转
            "headY": -8.0,      # 大幅低头
            "headZ": -10.0,     # 大幅歪头（另一侧）

            "eyeLeft": 1.0,     # 睁大眼睛
            "eyeRight": 1.0,

            "mouth": 0.1,       # 微微张嘴

            "bodyX": -0.8,      # 大幅侧身（另一侧）
            "bodyY": -0.5,      # 大幅后仰
            "bodyZ": -0.3,      # 大幅歪转（另一侧）

            "hair": -1.0,       # 最大头发飘动（反向）

            "ParamArmLA": 1.0,  # 左臂A显示
            "ParamArmRA": 0.0,  # 右臂A隐藏
            "ParamArmLB": 1.0,  # 左臂B显示
            "ParamArmRB": 0.0,  # 右臂B隐藏
        }

        await websocket.send(json.dumps(params_2))  # 直接发送参数
        print(f"发送相反参数:")
        for key, value in params_2.items():
            print(f"  {key}: {value}")

        await asyncio.sleep(3)

        # ============================================================================
        # 测试3：特定组合（表情测试）
        # ============================================================================
        print("\n[测试3] 测试表情组合...")

        # 测试3.1：惊讶表情
        params_surprised = {
            "eyeLeft": 1.0,
            "eyeRight": 1.0,
            "mouth": 0.7,
            "headY": 5.0,      # 抬头
            "hair": 0.5,
        }
        await websocket.send(json.dumps(params_surprised))
        print(f"发送惊讶表情")
        await asyncio.sleep(2)

        # 测试3.2：悲伤表情
        params_sad = {
            "eyeLeft": 0.6,
            "eyeRight": 0.6,
            "mouth": 0.2,
            "headY": -4.0,     # 低头
            "headZ": 3.0,      # 歪头
        }
        await websocket.send(json.dumps(params_sad))
        print(f"发送悲伤表情")
        await asyncio.sleep(2)

        # 测试3.3：高兴表情
        params_happy = {
            "eyeLeft": 1.0,
            "eyeRight": 1.0,
            "mouth": 0.8,
            "headY": 3.0,      # 微微抬头
            "hair": 0.3,
        }
        await websocket.send(json.dumps(params_happy))
        print(f"发送高兴表情")
        await asyncio.sleep(2)

        # ============================================================================
        # 测试4：重置参数
        # ============================================================================
        print("\n[测试4] 重置参数到默认值...")

        params_reset = {
            "headX": 0.0,
            "headY": 0.0,
            "headZ": 0.0,
            "eyeLeft": 1.0,
            "eyeRight": 1.0,
            "mouth": 0.0,
            "bodyX": 0.0,
            "bodyY": 0.0,
            "bodyZ": 0.0,
            "hair": 0.0,
            "ParamArmLA": 1.0,
            "ParamArmRA": 1.0,
            "ParamArmLB": 1.0,
            "ParamArmRB": 1.0,
        }

        await websocket.send(json.dumps(params_reset))
        print("已重置参数")

        await asyncio.sleep(1)

        # ============================================================================
        # 测试完成
        # ============================================================================
        await websocket.close()
        print("\n" + "=" * 80)
        print("[OK] 测试完成!")
        print("\n请检查前端控制台:")
        print("1. 是否有[MODEL-DEBUG]日志显示所有参数?")
        print("2. 是否有[MODEL]应用AI参数到模型的日志?")
        print("3. 是否有参数ID无效的警告?")
        print("4. Live2D模型是否响应参数变化?")
        print("=" * 80)

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
    asyncio.run(test_hiyori_direct())