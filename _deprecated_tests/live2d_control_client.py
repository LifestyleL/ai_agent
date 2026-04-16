#!/usr/bin/env python3
"""
Live2D 参数控制客户端
通过WebSocket直接发送参数到前端Live2D模型
运行前请确保主系统已启动: python main.py
"""

import asyncio
import json
import websockets
import time
from datetime import datetime

class Live2DControlClient:
    def __init__(self, host="localhost", port=8765):
        self.host = host
        self.port = port
        self.websocket = None
        self.connected = False

    async def connect(self):
        """连接到WebSocket服务器"""
        try:
            print(f"正在连接到 ws://{self.host}:{self.port} ...")
            self.websocket = await websockets.connect(f"ws://{self.host}:{self.port}")
            self.connected = True
            print("✅ 连接成功!")
            return True
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            print("请确保主系统已运行: python main.py")
            return False

    async def send_params(self, params_dict):
        """发送参数到前端"""
        if not self.connected or not self.websocket:
            print("未连接到服务器")
            return False

        try:
            # 添加时间戳
            data = {
                "type": "PARAMS",
                "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "data": params_dict
            }

            await self.websocket.send(json.dumps(data))
            print(f"[send] 发送参数: {json.dumps(params_dict, indent=2)}")
            return True
        except Exception as e:
            print(f"[ERROR] 发送失败: {e}")
            return False

    async def close(self):
        """关闭连接"""
        if self.websocket:
            await self.websocket.close()
            self.connected = False
            print("连接已关闭")

async def test_basic_controls(client):
    """测试基本控制"""
    print("\n" + "=" * 60)
    print("测试基本控制")
    print("=" * 60)

    # 测试头部控制
    print("\n1. 测试头部控制:")
    await client.send_params({"eyeLeft": 1.0, "eyeRight": 1.0, "headX": 0.5})
    await asyncio.sleep(1)

    await client.send_params({"headX": -0.5})
    await asyncio.sleep(1)

    await client.send_params({"headY": 0.3})
    await asyncio.sleep(1)

    await client.send_params({"headY": -0.3})
    await asyncio.sleep(1)

    # 测试嘴巴
    print("\n2. 测试嘴巴控制:")
    for i in range(5):
        mouth_val = 0.2 + i * 0.15
        await client.send_params({"mouth": mouth_val})
        await asyncio.sleep(0.3)

    # 测试身体
    print("\n3. 测试身体控制:")
    await client.send_params({"bodyX": 0.3, "bodyY": 0.1})
    await asyncio.sleep(1)

    await client.send_params({"bodyX": -0.3, "bodyY": -0.1})
    await asyncio.sleep(1)

    # 测试头发
    print("\n4. 测试头发控制:")
    await client.send_params({"hair": 0.5})
    await asyncio.sleep(1)

    await client.send_params({"hair": -0.5})
    await asyncio.sleep(1)

    # 重置
    print("\n5. 重置到默认值:")
    await client.send_params({
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
    })

async def test_expressions(client):
    """测试表情"""
    print("\n" + "=" * 60)
    print("测试表情")
    print("=" * 60)

    expressions = {
        "neutral": {"eyeLeft": 1.0, "eyeRight": 1.0, "mouth": 0.2, "headX": 0.0, "headY": 0.0},
        "happy": {"eyeLeft": 1.0, "eyeRight": 1.0, "mouth": 0.8, "headY": 0.3, "hair": 0.2},
        "sad": {"eyeLeft": 0.7, "eyeRight": 0.7, "mouth": 0.1, "headY": -0.3, "headZ": 0.2},
        "surprised": {"eyeLeft": 1.0, "eyeRight": 1.0, "mouth": 0.7, "headY": 0.5},
        "angry": {"eyeLeft": 0.8, "eyeRight": 0.8, "mouth": 0.3, "headX": 0.3, "bodyX": 0.2},
    }

    for name, params in expressions.items():
        print(f"\n{name}:")
        await client.send_params(params)
        await asyncio.sleep(1.5)

async def interactive_control(client):
    """交互式控制"""
    print("\n" + "=" * 60)
    print("交互式控制模式")
    print("=" * 60)
    print("命令格式:")
    print("  set <参数> <值>    - 设置单个参数 (如: set headX 0.5)")
    print("  show               - 显示当前参数")
    print("  reset              - 重置所有参数")
    print("  test <名称>        - 测试预设 (neutral/happy/sad/surprised/angry)")
    print("  help               - 显示帮助")
    print("  exit               - 退出")
    print("=" * 60)

    current_params = {
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

    valid_params = set(current_params.keys())

    while True:
        try:
            cmd = input("\ncontrol> ").strip()
            if not cmd:
                continue

            parts = cmd.split()
            command = parts[0].lower()

            if command == "exit" or command == "quit":
                break

            elif command == "help":
                print("\n可用命令:")
                print("  set <参数> <值>    - 设置参数")
                print("  show               - 显示当前参数")
                print("  reset              - 重置所有参数")
                print("  test <名称>        - 测试预设表情")
                print("  help               - 显示帮助")
                print("  exit               - 退出")
                print("\n可用参数:", ", ".join(sorted(valid_params)))

            elif command == "show":
                print("\n当前参数:")
                for key, value in sorted(current_params.items()):
                    print(f"  {key}: {value:.3f}")

            elif command == "reset":
                for key in current_params:
                    current_params[key] = 0.0
                current_params["eyeLeft"] = 1.0
                current_params["eyeRight"] = 1.0
                current_params["PartArmA"] = 1.0
                await client.send_params(current_params)
                print("已重置所有参数")

            elif command == "set" and len(parts) >= 3:
                param = parts[1]
                value_str = parts[2]

                if param not in valid_params:
                    print(f"无效参数: {param}")
                    print(f"可用参数: {', '.join(sorted(valid_params))}")
                    continue

                try:
                    value = float(value_str)
                    # 简单范围检查
                    if param in ["mouth", "PartArmA", "PartArmB"] and not (0 <= value <= 1):
                        print(f"警告: {param} 范围应为 0~1")
                    elif param == "hair" and not (-1 <= value <= 1):
                        print(f"警告: hair 范围应为 -1~1")

                    current_params[param] = value
                    await client.send_params({param: value})
                    print(f"设置 {param} = {value}")

                except ValueError:
                    print(f"无效数值: {value_str}")

            elif command == "test" and len(parts) >= 2:
                test_name = parts[1].lower()
                presets = {
                    "neutral": {"eyeLeft": 1.0, "eyeRight": 1.0, "mouth": 0.2},
                    "happy": {"eyeLeft": 1.0, "eyeRight": 1.0, "mouth": 0.8, "headY": 0.3},
                    "sad": {"eyeLeft": 0.7, "eyeRight": 0.7, "mouth": 0.1, "headY": -0.3},
                    "surprised": {"eyeLeft": 1.0, "eyeRight": 1.0, "mouth": 0.7, "headY": 0.5},
                    "angry": {"eyeLeft": 0.8, "eyeRight": 0.8, "mouth": 0.3, "headX": 0.3},
                }

                if test_name in presets:
                    await client.send_params(presets[test_name])
                    print(f"测试: {test_name}")
                    # 更新当前参数
                    for key, value in presets[test_name].items():
                        current_params[key] = value
                else:
                    print(f"未知测试: {test_name}")
                    print(f"可用测试: {', '.join(presets.keys())}")

            else:
                print(f"未知命令: {command}")
                print("输入 'help' 查看帮助")

        except KeyboardInterrupt:
            print("\n退出交互模式")
            break
        except Exception as e:
            print(f"错误: {e}")

async def main():
    """主函数"""
    print("=" * 60)
    print("Live2D 参数控制客户端")
    print("=" * 60)
    print("请确保主系统已启动: python main.py")
    print("前端Live2D模型已连接")
    print("=" * 60)

    client = Live2DControlClient()

    # 连接到服务器
    if not await client.connect():
        return

    try:
        # 询问测试模式
        print("\n选择模式:")
        print("1. 自动测试基本控制")
        print("2. 自动测试表情")
        print("3. 交互式控制")
        print("4. 直接退出")

        choice = input("\n请输入选择 (1-4): ").strip()

        if choice == "1":
            await test_basic_controls(client)
        elif choice == "2":
            await test_expressions(client)
        elif choice == "3":
            await interactive_control(client)
        else:
            print("退出")

    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"运行错误: {e}")
    finally:
        await client.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n程序已退出")
    except Exception as e:
        print(f"程序错误: {e}")
        import traceback
        traceback.print_exc()