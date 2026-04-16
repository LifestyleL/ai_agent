#!/usr/bin/env python3
"""
JSON-RPC 多通道通信验证脚本

本脚本用于验证后端是否正确地使用 JSON-RPC 协议将数据分发到不同通道：
- animation 通道：Live2D 参数（嘴型、头部转动等）
- audio 通道：TTS 音频数据
- control 通道：控制命令和其他数据

验证步骤：
1. 连接 WebSocket 服务器 (ws://localhost:{WS_PORT})
2. 发送测试消息
3. 接收并分析返回的 JSON-RPC 格式消息
4. 打印通道分离结果
"""

import asyncio
import json
import websockets
import sys
from datetime import datetime
from config import WS_PORT

# ANSI 颜色代码（用于醒目打印）
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

def print_channel_info(channel, data):
    """按通道类型醒目打印信息"""
    channel_colors = {
        "animation": Colors.GREEN,
        "audio": Colors.BLUE,
        "control": Colors.YELLOW,
        "error": Colors.RED
    }

    color = channel_colors.get(channel, Colors.WHITE)
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

    # 简化数据展示，避免过长
    data_str = json.dumps(data, ensure_ascii=False)
    if len(data_str) > 200:
        data_str = data_str[:197] + "..."

    print(f"{Colors.BOLD}[{timestamp}] {color}[通道: {channel}]{Colors.END} -> 数据内容: {data_str}")

def print_raw_message(msg_type, data):
    """打印原始消息（非JSON-RPC格式）"""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    data_str = json.dumps(data, ensure_ascii=False)
    if len(data_str) > 200:
        data_str = data_str[:197] + "..."

    print(f"{Colors.BOLD}[{timestamp}] {Colors.MAGENTA}[原始消息: {msg_type}]{Colors.END} -> {data_str}")

async def test_jsonrpc_channels():
    """主测试函数"""
    uri = f"ws://localhost:{WS_PORT}"
    timeout = 10  # 秒

    print(f"{Colors.BOLD}{Colors.CYAN}=== JSON-RPC 多通道通信验证开始 ==={Colors.END}")
    print(f"连接地址: {uri}")
    print(f"超时设置: {timeout}秒")
    print(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    try:
        # 连接 WebSocket 服务器
        print(f"{Colors.YELLOW}[连接] 正在连接 WebSocket 服务器...{Colors.END}")
        async with websockets.connect(uri, ping_timeout=None) as websocket:
            print(f"{Colors.GREEN}[连接] 连接成功！{Colors.END}")

            # 发送测试消息
            test_message = {"type": "user_input", "text": "测试通道分离"}
            print(f"{Colors.YELLOW}[发送] 发送测试消息: {json.dumps(test_message, ensure_ascii=False)}{Colors.END}")
            await websocket.send(json.dumps(test_message))

            # 设置超时
            print(f"{Colors.YELLOW}[接收] 开始接收消息（超时: {timeout}秒）...{Colors.END}")
            print(f"{Colors.CYAN}{'='*60}{Colors.END}")

            messages_received = 0
            start_time = asyncio.get_event_loop().time()

            # 接收消息直到超时
            while (asyncio.get_event_loop().time() - start_time) < timeout:
                try:
                    # 设置单次接收超时
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                    except asyncio.TimeoutError:
                        continue  # 继续检查总超时

                    messages_received += 1

                    try:
                        data = json.loads(message)

                        # 检查是否为 JSON-RPC 格式
                        if isinstance(data, dict) and "jsonrpc" in data:
                            # JSON-RPC 格式消息
                            method = data.get("method", "未知方法")
                            params = data.get("params", {})
                            channel = params.get("channel", "未知通道")

                            # 根据通道类型处理
                            if channel == "animation":
                                print_channel_info("animation", params.get("data", {}))
                            elif channel == "audio":
                                # 音频数据通常较大，简化显示
                                audio_data = params.get("data", {})
                                if "audio_base64" in audio_data:
                                    audio_data = {"type": audio_data.get("type"),
                                                  "audio_length": len(audio_data.get("audio_base64", "")),
                                                  "visemes": audio_data.get("visemes", [])[:3]}
                                print_channel_info("audio", audio_data)
                            elif channel == "control":
                                print_channel_info("control", params.get("data", {}))
                            else:
                                print_channel_info(channel, params.get("data", {}))

                        # 检查是否为错误响应
                        elif isinstance(data, dict) and "error" in data:
                            print_channel_info("error", data)

                        # 旧格式消息（非JSON-RPC）
                        else:
                            msg_type = data.get("type", "未知类型")
                            print_raw_message(msg_type, data)

                    except json.JSONDecodeError:
                        print(f"{Colors.RED}[错误] 无法解析JSON: {message[:100]}...{Colors.END}")

                except websockets.exceptions.ConnectionClosed:
                    print(f"{Colors.RED}[连接] WebSocket 连接已关闭{Colors.END}")
                    break
                except Exception as e:
                    print(f"{Colors.RED}[错误] 接收消息时出错: {e}{Colors.END}")

            print(f"{Colors.CYAN}{'='*60}{Colors.END}")
            print(f"{Colors.BOLD}测试完成统计:{Colors.END}")
            print(f"  总接收消息数: {messages_received}")
            print(f"  测试持续时间: {asyncio.get_event_loop().time() - start_time:.2f}秒")

            if messages_received == 0:
                print(f"{Colors.YELLOW}[警告] 未收到任何消息，请检查后端服务是否正常运行{Colors.END}")

    except ConnectionRefusedError:
        print(f"{Colors.RED}[错误] 连接被拒绝，请确保后端服务正在运行 (python main.py){Colors.END}")
        return False
    except asyncio.TimeoutError:
        print(f"{Colors.RED}[错误] 连接超时{Colors.END}")
        return False
    except Exception as e:
        print(f"{Colors.RED}[错误] 连接失败: {e}{Colors.END}")
        return False

    return True

async def main():
    """主入口函数"""
    try:
        success = await test_jsonrpc_channels()
        if success:
            print(f"{Colors.BOLD}{Colors.GREEN}=== 验证完成 ==={Colors.END}")
            print(f"{Colors.GREEN}请检查上面的输出，确认是否看到不同的通道数据（animation, audio, control）{Colors.END}")
        else:
            print(f"{Colors.BOLD}{Colors.RED}=== 验证失败 ==={Colors.END}")
            sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}[中断] 用户中断测试{Colors.END}")
        sys.exit(0)

if __name__ == "__main__":
    # 检查必要的库
    try:
        import websockets
    except ImportError:
        print(f"{Colors.RED}[错误] 缺少 websockets 库，请运行: pip install websockets{Colors.END}")
        sys.exit(1)

    # 运行测试
    asyncio.run(main())