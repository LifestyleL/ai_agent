"""
JSON-RPC 2.0 响应构造器
遵循架构方案 4.2 节规范，提供标准化的响应格式
"""

import json
import time
import os
from typing import Dict, Any, Optional

from .error_code import ErrorCode


class JsonRpcBuilder:
    """JSON-RPC 2.0 响应构造器"""

    # 通道与方法映射
    CHANNEL_METHOD_MAP = {
        "animation": "animation.update",
        "audio": "audio.stream",
        "control": "control.command",
    }

    @staticmethod
    def build_success_response(method: str, data: Dict[str, Any], request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        构建成功的 JSON-RPC 2.0 响应

        Args:
            method: 方法名，如 "animation.update"
            data: 实际业务数据
            request_id: 请求ID（如果有的话）

        Returns:
            JSON-RPC 2.0 格式的响应字典
        """
        # 从方法名推断通道
        channel = "control"  # 默认
        for chan, meth_prefix in JsonRpcBuilder.CHANNEL_METHOD_MAP.items():
            if method.startswith(chan):
                channel = chan
                break

        response = {
            "jsonrpc": "2.0",
            "method": method,
            "params": {
                "channel": channel,
                "version": "1.0",
                "timestamp": int(time.time() * 1000),  # 毫秒级时间戳
                "data": data,
            },
        }

        if request_id is not None:
            response["id"] = request_id

        return response

    @staticmethod
    def build_error_response(code: int, message: str, request_id: Optional[str] = None,
                            data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        构建错误的 JSON-RPC 2.0 响应

        Args:
            code: 错误码
            message: 错误消息
            request_id: 请求ID（如果有的话）
            data: 附加的错误数据

        Returns:
            JSON-RPC 2.0 格式的错误响应字典
        """
        error_obj = {
            "code": code,
            "message": message,
        }

        if data is not None:
            error_obj["data"] = data

        response = {
            "jsonrpc": "2.0",
            "error": error_obj,
        }

        if request_id is not None:
            response["id"] = request_id

        return response

    @staticmethod
    def wrap_data_for_channel(channel: str, data: Dict[str, Any], request_id: Optional[str] = None) -> Dict[str, Any]:
        """
        根据通道包装数据为 JSON-RPC 格式（便捷方法）

        Args:
            channel: 通道名称 ("animation", "audio", "control")
            data: 实际业务数据
            request_id: 请求ID

        Returns:
            JSON-RPC 2.0 格式的响应字典
        """
        if channel not in JsonRpcBuilder.CHANNEL_METHOD_MAP:
            raise ValueError(f"未知通道: {channel}")

        method = JsonRpcBuilder.CHANNEL_METHOD_MAP[channel]
        return JsonRpcBuilder.build_success_response(method, data, request_id)

    @staticmethod
    def is_jsonrpc_enabled() -> bool:
        """
        检查是否启用 JSON-RPC 响应包装

        Returns:
            bool: 是否启用 JSON-RPC 响应包装
        """
        # 优先检查环境变量
        env_value = os.getenv("ENABLE_JSONRPC_RESPONSE", "").strip().lower()
        if env_value:
            return env_value in ("true", "1", "yes", "on")

        # 如果没有环境变量，尝试从配置文件读取
        try:
            from config import ENABLE_JSONRPC_RESPONSE
            return ENABLE_JSONRPC_RESPONSE
        except ImportError:
            # 如果无法导入配置，返回默认值 False
            return False