#!/usr/bin/env python3
"""
Step 4 阻断验证测试
验证 JSON-RPC 2.0 出口包装层与错误规范
"""

import sys
import os
import json
import asyncio
from unittest.mock import Mock, AsyncMock, patch

# 添加 my_agent 目录到路径，以便导入模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'my-react-app', 'my_agent'))

from netwebsocket.json_rpc_builder import JsonRpcBuilder
from netwebsocket.error_code import ErrorCode


def test_jsonrpc_builder_success_response():
    """测试 JSON-RPC 成功响应构造"""
    print("=== 测试 1: JSON-RPC 成功响应构造 ===")

    # 测试动画通道
    animation_data = {"ParamAngleX": 15, "ParamAngleY": -10}
    response = JsonRpcBuilder.build_success_response(
        method="animation.update",
        data=animation_data,
        request_id="123"
    )

    required_fields = ["jsonrpc", "method", "params", "id"]
    missing = [f for f in required_fields if f not in response]
    if missing:
        print(f"[FAIL] 缺少字段: {missing}")
        print(f"  响应: {response}")
        return False

    if response["jsonrpc"] != "2.0":
        print(f"[FAIL] jsonrpc 字段错误: {response['jsonrpc']}")
        return False

    if response["method"] != "animation.update":
        print(f"[FAIL] method 字段错误: {response['method']}")
        return False

    if response["id"] != "123":
        print(f"[FAIL] id 字段错误: {response['id']}")
        return False

    params = response["params"]
    if params.get("channel") != "animation":
        print(f"[FAIL] params.channel 字段错误: {params.get('channel')}")
        return False

    if params.get("version") != "1.0":
        print(f"[FAIL] params.version 字段错误: {params.get('version')}")
        return False

    if "timestamp" not in params:
        print(f"[FAIL] params.timestamp 字段缺失")
        return False

    if params.get("data") != animation_data:
        print(f"[FAIL] params.data 字段错误")
        return False

    print("[PASS] JSON-RPC 成功响应构造测试通过")
    print(f"  响应结构: {json.dumps(response, indent=2, ensure_ascii=False)[:300]}...")
    return True


def test_jsonrpc_builder_error_response():
    """测试 JSON-RPC 错误响应构造"""
    print("\n=== 测试 2: JSON-RPC 错误响应构造 ===")

    error_data = {"details": "参数超出范围", "param": "ParamAngleX", "value": 999}
    response = JsonRpcBuilder.build_error_response(
        code=ErrorCode.ANIMATION_PARAM_OUT_OF_RANGE,
        message="动画参数超出范围",
        request_id="456",
        data=error_data
    )

    required_fields = ["jsonrpc", "error"]
    missing = [f for f in required_fields if f not in response]
    if missing:
        print(f"[FAIL] 缺少字段: {missing}")
        print(f"  响应: {response}")
        return False

    if response["jsonrpc"] != "2.0":
        print(f"[FAIL] jsonrpc 字段错误: {response['jsonrpc']}")
        return False

    if response["id"] != "456":
        print(f"[FAIL] id 字段错误: {response['id']}")
        return False

    error_obj = response["error"]
    if error_obj.get("code") != ErrorCode.ANIMATION_PARAM_OUT_OF_RANGE:
        print(f"[FAIL] error.code 字段错误: {error_obj.get('code')}")
        return False

    if error_obj.get("message") != "动画参数超出范围":
        print(f"[FAIL] error.message 字段错误: {error_obj.get('message')}")
        return False

    if error_obj.get("data") != error_data:
        print(f"[FAIL] error.data 字段错误")
        return False

    print("[PASS] JSON-RPC 错误响应构造测试通过")
    print(f"  错误响应: {json.dumps(response, indent=2, ensure_ascii=False)[:300]}...")
    return True


def test_wrap_data_for_channel():
    """测试根据通道包装数据"""
    print("\n=== 测试 3: 根据通道包装数据 ===")

    test_cases = [
        ("animation", {"ParamAngleX": 10}, "animation.update"),
        ("audio", {"audio_base64": "AAAA...", "type": "TTS_AUDIO"}, "audio.stream"),
        ("control", {"command": "reset", "action": "restart"}, "control.command"),
    ]

    for channel, data, expected_method in test_cases:
        response = JsonRpcBuilder.wrap_data_for_channel(
            channel=channel,
            data=data,
            request_id="789"
        )

        if response["method"] != expected_method:
            print(f"[FAIL] 通道 {channel} 方法名错误: {response['method']} != {expected_method}")
            return False

        if response["params"]["channel"] != channel:
            print(f"[FAIL] 通道 {channel} 通道字段错误: {response['params']['channel']}")
            return False

        if response["params"]["data"] != data:
            print(f"[FAIL] 通道 {channel} 数据字段错误")
            return False

    print("[PASS] 根据通道包装数据测试通过")
    return True


def test_is_jsonrpc_enabled():
    """测试 JSON-RPC 启用检查"""
    print("\n=== 测试 4: JSON-RPC 启用检查 ===")

    # 测试默认值（应为 False）
    default_enabled = JsonRpcBuilder.is_jsonrpc_enabled()
    if default_enabled:
        print(f"[FAIL] 默认情况下 JSON-RPC 应禁用，实际: {default_enabled}")
        return False

    print("[PASS] JSON-RPC 启用检查测试通过（默认禁用）")
    return True


def test_error_code_messages():
    """测试错误码消息"""
    print("\n=== 测试 5: 错误码消息 ===")

    test_cases = [
        (ErrorCode.PARSE_ERROR, "JSON 解析错误"),
        (ErrorCode.ANIMATION_PARAM_OUT_OF_RANGE, "动画参数超出范围"),
        (ErrorCode.AUDIO_TTS_INIT_FAILED, "TTS 初始化失败"),
        (ErrorCode.AI_MODEL_UNAVAILABLE, "AI 模型不可用"),
        (999999, "未知错误 (代码: 999999)"),  # 未知错误码
    ]

    for code, expected_message in test_cases:
        message = ErrorCode.get_error_message(code)
        if message != expected_message:
            print(f"[FAIL] 错误码 {code} 消息错误: '{message}' != '{expected_message}'")
            return False

    print("[PASS] 错误码消息测试通过")
    return True


def test_ws_server_channel_inference():
    """测试 WS 服务器通道推断"""
    print("\n=== 测试 6: WS 服务器通道推断 ===")

    # 需要导入 WSServer，但会触发实际初始化，使用模拟
    from netwebsocket.ws_server import WSServer

    server = WSServer()

    test_cases = [
        ({"type": "TTS_AUDIO", "audio_base64": "AAAA..."}, "audio"),
        ({"ParamAngleX": 10, "ParamAngleY": -5}, "animation"),
        ({"ParamMouthOpenY": 0.5, "ParamEyeLOpen": 1.0}, "animation"),
        ({"command": "reset", "action": "restart"}, "control"),
        ({"text": "你好", "type": "MESSAGE"}, "control"),
        ({"signal": "heartbeat"}, "control"),
    ]

    for data, expected_channel in test_cases:
        channel = server._infer_channel_from_data(data)
        if channel != expected_channel:
            print(f"[FAIL] 数据 {data} 推断通道错误: '{channel}' != '{expected_channel}'")
            return False

    print("[PASS] WS 服务器通道推断测试通过")
    return True


async def test_ws_server_send_wrapping():
    """测试 WS 服务器发送包装"""
    print("\n=== 测试 7: WS 服务器发送包装 ===")

    # 模拟测试，因为实际测试需要 WebSocket 连接
    from netwebsocket.ws_server import WSServer

    # 创建服务器实例
    server = WSServer()

    # 模拟 WebSocket
    mock_websocket = AsyncMock()
    server.websocket = mock_websocket

    # 测试数据
    test_data = {"ParamAngleX": 20, "ParamAngleY": -10}

    # 1. 测试禁用 JSON-RPC 时的发送
    with patch.object(JsonRpcBuilder, 'is_jsonrpc_enabled', return_value=False):
        await server._send(test_data)

        # 验证发送的数据是原始数据
        call_args = mock_websocket.send.call_args
        if call_args:
            sent_data = json.loads(call_args[0][0])
            if sent_data != test_data:
                print(f"[FAIL] 禁用 JSON-RPC 时发送数据错误: {sent_data} != {test_data}")
                return False
        else:
            print("[FAIL] 禁用 JSON-RPC 时未调用 send")
            return False

    # 重置模拟
    mock_websocket.reset_mock()

    # 2. 测试启用 JSON-RPC 时的发送
    with patch.object(JsonRpcBuilder, 'is_jsonrpc_enabled', return_value=True):
        await server._send(test_data)

        # 验证发送的数据是包装后的数据
        call_args = mock_websocket.send.call_args
        if call_args:
            sent_data = json.loads(call_args[0][0])

            # 检查 JSON-RPC 结构
            if sent_data.get("jsonrpc") != "2.0":
                print(f"[FAIL] 启用 JSON-RPC 时 jsonrpc 字段错误: {sent_data.get('jsonrpc')}")
                return False

            if sent_data.get("method") != "animation.update":
                print(f"[FAIL] 启用 JSON-RPC 时 method 字段错误: {sent_data.get('method')}")
                return False

            params = sent_data.get("params", {})
            if params.get("channel") != "animation":
                print(f"[FAIL] 启用 JSON-RPC 时 channel 字段错误: {params.get('channel')}")
                return False

            if params.get("data") != test_data:
                print(f"[FAIL] 启用 JSON-RPC 时 data 字段错误")
                return False
        else:
            print("[FAIL] 启用 JSON-RPC 时未调用 send")
            return False

    print("[PASS] WS 服务器发送包装测试通过")
    return True


def main():
    """运行所有测试"""
    print("=" * 70)
    print("Step 4 JSON-RPC 出口包装层阻断验证测试")
    print("验证出口包装和错误规范是否生效")
    print("=" * 70)

    results = []

    # 运行同步测试
    results.append(("JSON-RPC 成功响应构造", test_jsonrpc_builder_success_response()))
    results.append(("JSON-RPC 错误响应构造", test_jsonrpc_builder_error_response()))
    results.append(("根据通道包装数据", test_wrap_data_for_channel()))
    results.append(("JSON-RPC 启用检查", test_is_jsonrpc_enabled()))
    results.append(("错误码消息", test_error_code_messages()))
    results.append(("WS 服务器通道推断", test_ws_server_channel_inference()))

    # 运行异步测试
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results.append(("WS 服务器发送包装", loop.run_until_complete(test_ws_server_send_wrapping())))
    finally:
        loop.close()

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

    # 提供启用 JSON-RPC 的说明
    print("\n如何启用 JSON-RPC 响应包装:")
    print("1. 设置环境变量: export ENABLE_JSONRPC_RESPONSE=true")
    print("2. 或者在 .env 文件中添加: ENABLE_JSONRPC_RESPONSE=true")
    print("3. 或者在 config.py 中设置: ENABLE_JSONRPC_RESPONSE = True")
    print("\n注意: 启用后，前端需要支持 JSON-RPC 2.0 格式解析")
    print("      默认禁用以保证前端兼容性")

    if all_passed:
        print("\n[PASS] 所有测试通过！Step 4 验证完成。")
        print("系统保持向后兼容，开关关闭时行为与 Step 3 完全一致。")
        return 0
    else:
        print("\n[FAIL] 测试失败！请修复问题。")
        return 1


if __name__ == "__main__":
    sys.exit(main())