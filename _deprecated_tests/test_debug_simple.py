#!/usr/bin/env python3
"""
简单的Live2D参数测试
验证Animator控制接口是否正常工作
"""

import time
import asyncio
import json
from datetime import datetime
from live2d.live2d_manager import Live2DManager

# 尝试导入WebSocket客户端
try:
    import websockets
    WEBSOCKET_AVAILABLE = True
except ImportError:
    print("[警告] websockets库未安装，WebSocket测试不可用")
    WEBSOCKET_AVAILABLE = False

def test_basic_control():
    """测试基本控制功能"""
    print("=" * 60)
    print("Live2D 参数控制接口测试")
    print("=" * 60)

    # 创建Live2D管理器
    live2d = Live2DManager()
    print(f"Live2D管理器创建成功: {live2d}")

    # 启动管理器
    live2d.start()
    print("Live2D管理器已启动")

    # 等待初始化
    time.sleep(0.5)

    try:
        # 测试1: 获取当前参数
        print("\n[测试1] 获取当前参数...")
        t = time.time()
        params = live2d.animator.compute_params(t)
        print(f"获取到 {len(params)} 个参数:")
        for key, value in params.items():
            print(f"  {key}: {value:.3f}")

        # 测试2: 设置头部参数
        print("\n[测试2] 设置头部参数...")
        print("设置 headX = 0.5, headY = -0.3")
        live2d.set_head(x=0.5, y=-0.3)

        time.sleep(0.5)  # 等待参数生效

        t = time.time()
        params = live2d.animator.compute_params(t)
        print(f"头部参数: headX={params.get('headX', 0):.3f}, headY={params.get('headY', 0):.3f}")

        # 测试3: 设置嘴巴
        print("\n[测试3] 设置嘴巴参数...")
        print("设置 mouth = 0.7 (70%张开)")
        live2d.set_mouth(0.7)

        time.sleep(0.5)

        t = time.time()
        params = live2d.animator.compute_params(t)
        print(f"嘴巴参数: mouth={params.get('mouth', 0):.3f}")

        # 测试4: 设置身体
        print("\n[测试4] 设置身体参数...")
        print("设置 bodyX = 0.3, bodyY = 0.1")
        live2d.set_body(x=0.3, y=0.1)

        time.sleep(0.5)

        t = time.time()
        params = live2d.animator.compute_params(t)
        print(f"身体参数: bodyX={params.get('bodyX', 0):.3f}, bodyY={params.get('bodyY', 0):.3f}")

        # 测试5: 设置活动度
        print("\n[测试5] 设置活动度...")
        print("设置 activity = 0.8 (高活动)")
        live2d.set_activity(0.8)

        time.sleep(0.5)

        t = time.time()
        params = live2d.animator.compute_params(t)
        print(f"活动度: {live2d.animator.activity_smooth:.3f}")

        # 测试6: 重置控制
        print("\n[测试6] 重置控制...")
        live2d.reset_control()
        print("控制已重置，恢复算法生成")

        time.sleep(1.0)

        # 测试7: 检查重置效果
        t = time.time()
        params = live2d.animator.compute_params(t)
        print("\n重置后参数:")
        print(f"  headX: {params.get('headX', 0):.3f}")
        print(f"  mouth: {params.get('mouth', 0):.3f}")
        print(f"  bodyX: {params.get('bodyX', 0):.3f}")
        print(f"  活动度: {live2d.animator.activity_smooth:.3f}")

        # 测试8: 模式切换
        print("\n[测试8] 测试模式切换...")
        print("设置为 thinking 模式")
        live2d.set_emotion_mode("thinking")

        time.sleep(1.0)

        print(f"当前模式: {live2d.animator.mode}")
        print(f"目标活动度: {live2d.animator.get_activity_target()}")

        # 测试9: 直接发送参数
        print("\n[测试9] 直接发送自定义参数...")
        custom_params = {
            "eyeLeft": 0.8,
            "eyeRight": 0.8,
            "mouth": 0.5,
            "headX": 0.3,
            "headY": 0.2
        }
        live2d.send_custom_params(custom_params)
        print(f"发送自定义参数: {custom_params}")

        print("\n" + "=" * 60)
        print("所有测试完成!")
        print("=" * 60)

        # 显示最终状态
        print("\n最终状态检查:")
        print(f"模式: {live2d.animator.mode}")
        print(f"活动度: {live2d.animator.activity_smooth:.3f}")

        # 检查目标值状态
        targets = [
            ("_target_head_x", live2d.animator._target_head_x),
            ("_target_mouth", live2d.animator._target_mouth),
            ("_target_body_x", live2d.animator._target_body_x),
            ("_target_activity", live2d.animator._target_activity),
        ]

        print("\n目标值状态:")
        for name, value in targets:
            status = "已设置" if value is not None else "未设置"
            val_str = f"{value:.3f}" if value is not None else "None"
            print(f"  {name}: {val_str} ({status})")

    except Exception as e:
        print(f"\n测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("\n清理资源...")
        # 注意：这里不应该停止live2d，因为它可能在主系统中使用
        print("测试完成!")

def test_parameter_ranges():
    """测试参数范围限制"""
    print("\n" + "=" * 60)
    print("参数范围测试")
    print("=" * 60)

    live2d = Live2DManager()

    # 测试超出范围的参数
    test_cases = [
        ("headX", 15.0, 10.0),    # 超出上限 -> 应限制为10.0
        ("headX", -15.0, -10.0),  # 超出下限 -> 应限制为-10.0
        ("mouth", 1.5, 1.0),      # 超出上限 -> 应限制为1.0
        ("mouth", -0.5, 0.0),     # 超出下限 -> 应限制为0.0
        ("bodyX", 2.0, 1.0),      # 超出上限 -> 应限制为1.0
        ("bodyY", -1.0, -0.5),    # 超出下限 -> 应限制为-0.5
    ]

    for param_name, test_value, expected in test_cases:
        # 设置参数
        if param_name == "headX":
            live2d.set_head(x=test_value)
            actual = live2d.animator._target_head_x
        elif param_name == "mouth":
            live2d.set_mouth(test_value)
            actual = live2d.animator._target_mouth
        elif param_name == "bodyX":
            live2d.set_body(x=test_value)
            actual = live2d.animator._target_body_x
        elif param_name == "bodyY":
            live2d.set_body(y=test_value)
            actual = live2d.animator._target_body_y
        else:
            continue

        # 验证结果
        if actual is not None and abs(actual - expected) < 0.001:
            print(f"✓ {param_name}: {test_value} -> {actual:.1f} (正确)")
        else:
            print(f"✗ {param_name}: {test_value} -> {actual} (期望: {expected})")

    live2d.reset_control()

def test_websocket_direct_control():
    """测试直接通过WebSocket发送参数到前端"""
    if not WEBSOCKET_AVAILABLE:
        print("\n[跳过] WebSocket测试，库未安装")
        return

    print("\n" + "=" * 60)
    print("WebSocket直接控制测试")
    print("=" * 60)
    print("注意: 此测试需要主系统已运行 (python main.py)")
    print("      或WebSocket服务器在 ws://localhost:8765 监听")
    print("=" * 60)

    async def run_test():
        try:
            print("连接到 ws://localhost:8765 ...")
            websocket = await websockets.connect("ws://localhost:8765")
            print("✅ WebSocket连接成功!")

            # 测试1: 发送单个参数
            print("\n[测试1] 发送头部参数...")
            params = {"headX": 0.5, "headY": -0.3}
            data = {
                "type": "PARAMS",
                "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "data": params
            }
            await websocket.send(json.dumps(data))
            print(f"发送: {params}")

            # 等待前端响应
            await asyncio.sleep(1.0)

            # 测试2: 发送嘴巴参数
            print("\n[测试2] 发送嘴巴参数...")
            params = {"mouth": 0.7}
            data["data"] = params
            data["timestamp"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            await websocket.send(json.dumps(data))
            print(f"发送: {params}")

            await asyncio.sleep(1.0)

            # 测试3: 发送重置参数
            print("\n[测试3] 发送重置参数...")
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
            data["data"] = reset_params
            data["timestamp"] = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            await websocket.send(json.dumps(data))
            print("发送重置参数")

            await asyncio.sleep(0.5)

            # 关闭连接
            await websocket.close()
            print("✅ WebSocket直接控制测试完成!")
            print("请观察前端Live2D模型是否响应")

        except ConnectionRefusedError:
            print("❌ 连接被拒绝，请确保主系统已运行: python main.py")
        except Exception as e:
            print(f"❌ WebSocket测试失败: {e}")

    # 运行异步测试
    asyncio.run(run_test())

if __name__ == "__main__":
    print("开始测试Live2D参数控制接口...")

    test_basic_control()
    test_parameter_ranges()

    # 询问是否进行WebSocket测试
    if WEBSOCKET_AVAILABLE:
        print("\n" + "=" * 60)
        choice = input("是否进行WebSocket直接控制测试? (y/n): ").strip().lower()
        if choice == 'y' or choice == 'yes':
            test_websocket_direct_control()
        else:
            print("跳过WebSocket测试")
    else:
        print("\n[提示] 安装websockets库后可进行WebSocket测试: pip install websockets")

    print("\n所有测试完成!")
    print("现在可以运行 live2d_debug.py 进行交互式调试")