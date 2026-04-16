#!/usr/bin/env python3
"""
Step 3 阻断验证测试
验证 WebSocket 消息路由器和兜底逻辑是否生效
"""

import sys
import os

# 添加 my_agent 目录到路径，以便导入模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'my-react-app', 'my_agent'))

from unittest.mock import Mock, MagicMock
from netwebsocket.message_router import MessageRouter


class MockWSServer:
    """模拟 WebSocket 服务器"""
    def __init__(self):
        self.driver = None
        self.tts = None
        self.send_queue = Mock()
        self.send_queue.put = Mock()


def test_parse_jsonrpc_standard():
    """测试标准 JSON-RPC 2.0 消息解析"""
    print("=== 测试 1: 标准 JSON-RPC 2.0 消息解析 ===")

    router = MessageRouter(MockWSServer())

    # 标准 JSON-RPC 2.0 请求
    message = '{"jsonrpc": "2.0", "method": "message", "params": {"channel": "animation", "type": "PARAMS", "data": {"ParamAngleX": 10}}, "id": 1}'
    parsed = router.parse_jsonrpc_message(message)

    if parsed is None:
        print("[FAIL] 标准 JSON-RPC 消息解析失败")
        return False

    expected_fields = ["jsonrpc", "method", "params", "id", "raw_data"]
    missing = [f for f in expected_fields if f not in parsed]
    if missing:
        print(f"[FAIL] 缺少字段: {missing}")
        print(f"  解析结果: {parsed}")
        return False

    if parsed["jsonrpc"] != "2.0":
        print(f"[FAIL] jsonrpc 字段错误: {parsed['jsonrpc']}")
        return False

    if parsed["method"] != "message":
        print(f"[FAIL] method 字段错误: {parsed['method']}")
        return False

    if parsed["params"].get("channel") != "animation":
        print(f"[FAIL] params.channel 字段错误: {parsed['params'].get('channel')}")
        return False

    print("[PASS] 标准 JSON-RPC 2.0 消息解析通过")
    return True


def test_parse_jsonrpc_wrapped():
    """测试包装消息解析（非标准但包含 channel 字段）"""
    print("\n=== 测试 2: 包装消息解析（非标准但包含 channel 字段） ===")

    router = MessageRouter(MockWSServer())

    # 非标准但包含 channel 字段的消息
    message = '{"channel": "control", "text": "你好", "signal": null}'
    parsed = router.parse_jsonrpc_message(message)

    if parsed is None:
        print("[FAIL] 包装消息解析失败")
        return False

    if not parsed.get("is_wrapped"):
        print("[FAIL] 包装消息未标记 is_wrapped")
        return False

    if parsed["jsonrpc"] != "2.0":
        print(f"[FAIL] 包装消息 jsonrpc 字段错误: {parsed['jsonrpc']}")
        return False

    if parsed["method"] != "message":
        print(f"[FAIL] 包装消息 method 字段错误: {parsed['method']}")
        return False

    if parsed["params"].get("channel") != "control":
        print(f"[FAIL] 包装消息 params.channel 字段错误: {parsed['params'].get('channel')}")
        return False

    print("[PASS] 包装消息解析通过")
    return True


def test_parse_jsonrpc_invalid():
    """测试无效消息解析"""
    print("\n=== 测试 3: 无效消息解析 ===")

    router = MessageRouter(MockWSServer())

    # 无效 JSON
    message = '{invalid json}'
    parsed = router.parse_jsonrpc_message(message)
    if parsed is not None:
        print("[FAIL] 无效 JSON 应返回 None")
        return False

    # 有效 JSON 但既不是 JSON-RPC 也不包含 channel
    message = '{"some": "data", "no_channel": true}'
    parsed = router.parse_jsonrpc_message(message)
    if parsed is not None:
        print("[FAIL] 无 channel 字段的非 JSON-RPC 消息应返回 None")
        return False

    print("[PASS] 无效消息解析通过（正确返回 None）")
    return True


def test_route_message_animation_channel():
    """测试动画通道消息路由"""
    print("\n=== 测试 4: 动画通道消息路由 ===")

    mock_server = MockWSServer()
    router = MessageRouter(mock_server)
    mock_websocket = Mock()

    # 标准 JSON-RPC 动画消息
    message = '{"jsonrpc": "2.0", "method": "message", "params": {"channel": "animation", "type": "PARAMS", "data": {"ParamAngleX": 15}}, "id": 1}'

    result = router.route_message(message, mock_websocket)

    if not result:
        print("[FAIL] 动画通道消息路由失败")
        return False

    # 检查 send_queue.put 是否被调用
    if mock_server.send_queue.put.called:
        print("[PASS] 动画通道消息路由成功，参数已放入队列")
        return True
    else:
        print("[FAIL] 动画通道消息路由成功，但参数未放入队列")
        return False


def test_route_message_control_channel():
    """测试控制通道消息路由"""
    print("\n=== 测试 5: 控制通道消息路由 ===")

    mock_server = MockWSServer()
    # 模拟 driver 存在
    mock_server.driver = Mock()
    mock_server.driver.handle_user_input = Mock()

    router = MessageRouter(mock_server)
    mock_websocket = Mock()

    # 包装格式的控制消息（用户输入）
    message = '{"channel": "control", "text": "你好世界"}'

    result = router.route_message(message, mock_websocket)

    if not result:
        print("[FAIL] 控制通道消息路由失败")
        return False

    # 检查 handle_user_input 是否被调用
    if mock_server.driver.handle_user_input.called:
        print("[PASS] 控制通道消息路由成功，用户输入已处理")
        return True
    else:
        print("[FAIL] 控制通道消息路由成功，但用户输入未处理")
        return False


def test_route_message_fallback():
    """测试兜底逻辑触发（未知通道或解析失败）"""
    print("\n=== 测试 6: 兜底逻辑触发 ===")

    mock_server = MockWSServer()
    router = MessageRouter(mock_server)
    mock_websocket = Mock()

    # 1. 未知通道消息
    message = '{"jsonrpc": "2.0", "method": "message", "params": {"channel": "unknown_channel", "data": {}}, "id": 1}'
    result = router.route_message(message, mock_websocket)

    if result:
        print("[FAIL] 未知通道消息应返回 False 触发兜底")
        return False

    # 2. 无法解析为 JSON-RPC 的消息
    message = '{invalid json}'
    result = router.route_message(message, mock_websocket)

    if result:
        print("[FAIL] 无效 JSON 消息应返回 False 触发兜底")
        return False

    print("[PASS] 兜底逻辑触发测试通过（未知通道和无效消息返回 False）")
    return True


def test_ws_server_integration_logic():
    """验证 ws_server.py 中的兜底逻辑设计"""
    print("\n=== 测试 7: ws_server.py 兜底逻辑设计验证 ===")

    # 读取 ws_server.py 文件内容
    ws_server_path = os.path.join(os.path.dirname(__file__), '..', 'my-react-app', 'my_agent', 'netwebsocket', 'ws_server.py')
    with open(ws_server_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查关键设计要素
    checks = []

    # 1. 路由器是否被导入
    if "from .message_router import create_router" in content:
        checks.append(("路由器导入", True))
    else:
        checks.append(("路由器导入", False))

    # 2. 路由器是否在 _handle_client 中创建
    if "router = create_router(self)" in content:
        checks.append(("路由器创建", True))
    else:
        checks.append(("路由器创建", False))

    # 3. 是否先尝试路由器处理
    if "if router.route_message(message, websocket):" in content:
        checks.append(("先尝试路由器", True))
    else:
        checks.append(("先尝试路由器", False))

    # 4. 是否有路由器异常捕获
    if "except Exception as router_error:" in content:
        checks.append(("路由器异常捕获", True))
    else:
        checks.append(("路由器异常捕获", False))

    # 5. 是否有降级逻辑注释
    if "降级逻辑：原有的消息处理代码" in content:
        checks.append(("降级逻辑标记", True))
    else:
        checks.append(("降级逻辑标记", False))

    # 6. 降级逻辑是否包含原有的四种分支处理
    required_branches = [
        "分支1: 心跳/信号",
        "分支2: TTS 测试",
        "分支3: 用户正常输入",
        "分支4: Live2D参数控制"
    ]

    branch_checks = []
    for branch in required_branches:
        if branch in content:
            branch_checks.append((f"分支检查: {branch}", True))
        else:
            branch_checks.append((f"分支检查: {branch}", False))

    all_passed = True
    print("ws_server.py 设计验证:")

    for check_name, passed in checks:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {check_name}")
        if not passed:
            all_passed = False

    for check_name, passed in branch_checks:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {check_name}")
        if not passed:
            all_passed = False

    if all_passed:
        print("[PASS] ws_server.py 兜底逻辑设计完整")
        return True
    else:
        print("[FAIL] ws_server.py 兜底逻辑设计不完整")
        return False


def main():
    """运行所有测试"""
    print("=" * 70)
    print("Step 3 WebSocket 消息路由阻断验证测试")
    print("验证消息路由器和兜底逻辑是否生效")
    print("=" * 70)

    results = []

    # 运行单元测试
    results.append(("标准 JSON-RPC 解析", test_parse_jsonrpc_standard()))
    results.append(("包装消息解析", test_parse_jsonrpc_wrapped()))
    results.append(("无效消息解析", test_parse_jsonrpc_invalid()))
    results.append(("动画通道路由", test_route_message_animation_channel()))
    results.append(("控制通道路由", test_route_message_control_channel()))
    results.append(("兜底逻辑触发", test_route_message_fallback()))
    results.append(("ws_server 设计验证", test_ws_server_integration_logic()))

    # 汇总结果
    print("\n" + "=" * 70)
    print("测试结果汇总:")
    print("=" * 70)

    all_passed = True
    for test_name, passed in results:
        status = "[PASS] 通过" if passed else "[FAIL] 失败"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("[PASS] 所有测试通过！Step 3 验证完成，可以开始 Step 4。")
        return 0
    else:
        print("[FAIL] 测试失败！请修复问题后再继续 Step 4。")
        return 1


if __name__ == "__main__":
    sys.exit(main())