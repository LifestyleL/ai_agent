"""
WebSocket 消息路由器
基于 JSON-RPC 2.0 规范，实现通道分发机制
"""

import json
import logging
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


class MessageRouter:
    """
    WebSocket 消息路由器
    负责解析 JSON-RPC 2.0 格式消息，并根据通道进行分发
    """

    def __init__(self, ws_server):
        """
        初始化路由器

        Args:
            ws_server: WebSocket 服务器实例，用于访问驱动器和相关服务
        """
        self.ws_server = ws_server
        self._initialized = False
        self._initialize_handlers()

    def _initialize_handlers(self):
        """初始化通道处理器"""
        self.channel_handlers = {
            "animation": self._handle_animation_channel,
            "audio": self._handle_audio_channel,
            "control": self._handle_control_channel,
        }
        self._initialized = True

    def parse_jsonrpc_message(self, raw_message: str) -> Optional[Dict[str, Any]]:
        """
        解析消息，尝试提取 JSON-RPC 2.0 字段

        Args:
            raw_message: 原始消息字符串

        Returns:
            解析后的字典，包含 JSON-RPC 字段，如果解析失败返回 None
        """
        try:
            data = json.loads(raw_message)

            # 检查是否包含 JSON-RPC 2.0 必需字段
            if "jsonrpc" in data and data.get("jsonrpc") == "2.0":
                # 标准 JSON-RPC 2.0 格式
                return {
                    "jsonrpc": data["jsonrpc"],
                    "method": data.get("method", ""),
                    "params": data.get("params", {}),
                    "id": data.get("id"),
                    "raw_data": data,  # 保留原始数据以备后用
                }
            elif "channel" in data:
                # 非标准但包含通道字段的消息，包装为 JSON-RPC 格式
                return {
                    "jsonrpc": "2.0",
                    "method": "message",
                    "params": data,
                    "id": None,
                    "raw_data": data,
                    "is_wrapped": True,  # 标记为包装消息
                }
            else:
                # 无法识别为 JSON-RPC 格式
                return None

        except json.JSONDecodeError as e:
            logger.warning(f"消息解析失败 (JSON解码错误): {e}")
            return None
        except Exception as e:
            logger.error(f"消息解析异常: {e}")
            return None

    def route_message(self, raw_message: str, websocket) -> bool:
        """
        路由消息到相应的通道处理器

        Args:
            raw_message: 原始消息字符串
            websocket: WebSocket 连接对象

        Returns:
            bool: 是否成功处理消息
        """
        # 1. 尝试解析为 JSON-RPC 格式
        parsed = self.parse_jsonrpc_message(raw_message)

        if parsed is None:
            # 无法解析为 JSON-RPC，返回 False 让调用者降级处理
            logger.debug("消息不是 JSON-RPC 格式，将降级到旧逻辑处理")
            return False

        # 2. 提取通道信息
        params = parsed.get("params", {})
        channel = params.get("channel")

        if not channel:
            # 没有指定通道，尝试从 method 或原始数据推断
            channel = self._infer_channel(parsed)
            logger.debug(f"未指定通道，推断为: {channel}")

        # 3. 路由到对应的处理器
        if channel in self.channel_handlers:
            try:
                logger.debug(f"路由消息到通道: {channel}")
                self.channel_handlers[channel](parsed, websocket)
                return True
            except Exception as e:
                logger.error(f"通道处理器执行失败 (通道: {channel}): {e}")
                # 处理器失败，返回 False 触发降级
                return False
        else:
            logger.warning(f"未知通道: {channel}，将降级处理")
            return False

    def _infer_channel(self, parsed_message: Dict[str, Any]) -> str:
        """
        推断消息所属通道

        Args:
            parsed_message: 解析后的消息

        Returns:
            推断的通道名称
        """
        params = parsed_message.get("params", {})
        raw_data = parsed_message.get("raw_data", {})

        # 优先检查 params（对于 JSON-RPC 标准格式）
        if "type" in params and params["type"] == "TTS_TEST":
            return "audio"
        elif params.get("type") == "PARAMS":
            return "animation"
        elif params.get("signal") is not None:
            return "control"
        elif "text" in params and params["text"]:
            return "control"

        # 降级检查 raw_data（对于包装消息或旧格式）
        if "type" in raw_data and raw_data["type"] == "TTS_TEST":
            return "audio"
        elif raw_data.get("type") == "PARAMS":
            return "animation"
        elif raw_data.get("signal") is not None:
            return "control"
        elif "text" in raw_data and raw_data["text"]:
            return "control"
        else:
            # 默认通道
            return "control"

    # ==================== 通道处理器 ====================
    # 注意：这些处理器暂时直接调用现有的业务逻辑
    # 后续重构时应将业务逻辑迁移到独立的服务类中

    def _handle_animation_channel(self, parsed_message: Dict[str, Any], websocket) -> bool:
        """
        处理动画通道消息
        对应旧逻辑中的 PARAMS 类型消息

        Returns:
            bool: 是否成功处理消息
        """
        params = parsed_message.get("params", {})

        # 直接调用现有的 Live2D 参数处理逻辑
        if params.get("type") == "PARAMS" and "data" in params:
            try:
                print(f"[PARAMS] 收到Live2D参数: {params['data']}")
                # 将参数数据（不带type包装）放入队列，让_queue_consumer发送给前端
                self.ws_server.send_queue.put(params['data'])
                return True
            except Exception as e:
                logger.error(f"动画通道处理失败: {e}")
                return False
        else:
            # 如果不是 PARAMS 类型，尝试其他动画相关处理
            logger.debug(f"动画通道收到消息: {params}")
            return False

    def _handle_audio_channel(self, parsed_message: Dict[str, Any], websocket):
        """
        处理音频通道消息
        对应旧逻辑中的 TTS_TEST 类型消息
        """
        params = parsed_message.get("params", {})

        # 直接调用现有的 TTS 测试逻辑
        if params.get("type") == "TTS_TEST":
            text = params.get("text", "").strip()
            if not text or self.ws_server.tts is None:
                print("[WAIT] TTS 还在初始化，稍后再试")
                return

            # 这里需要异步执行，但为了保持与旧逻辑一致，先记录
            print(f"[TTS_TEST] 收到音频测试请求: {text[:50]}...")
            # 实际处理将由 ws_server._handle_client 中的逻辑执行
            # 由于我们是在原有逻辑之前路由，这里只记录，实际处理仍由旧逻辑完成
            pass
        else:
            logger.debug(f"音频通道收到消息: {params}")

    def _handle_control_channel(self, parsed_message: Dict[str, Any], websocket) -> bool:
        """
        处理控制通道消息
        对应旧逻辑中的信号、用户输入等

        Returns:
            bool: 是否成功处理消息
        """
        params = parsed_message.get("params", {})

        # 处理信号（心跳/启动）
        if params.get("signal") is not None:
            try:
                print(f"[SIGNAL] 收到信号: {params['signal']}")
                # 直接调用现有的信号处理逻辑
                if self.ws_server.driver is None:
                    from agent.agent_driver import YumeDriver
                    self.ws_server.driver = YumeDriver()
                import threading
                threading.Thread(target=self.ws_server.driver.handle_user_input, args=("",), daemon=True).start()
                return True
            except Exception as e:
                logger.error(f"信号处理失败: {e}")
                return False

        # 处理用户输入
        text = params.get("text", "").strip()
        if text and self.ws_server.driver:
            try:
                print(f"[消息] [WS] 收到用户输入: {text[:30]}...")
                import threading
                threading.Thread(target=self.ws_server.driver.handle_user_input, args=(text,), daemon=True).start()
                return True
            except Exception as e:
                logger.error(f"用户输入处理失败: {e}")
                return False

        logger.debug(f"控制通道收到消息: {params}")
        return False


# 工具函数：创建路由器实例
def create_router(ws_server):
    """创建消息路由器实例"""
    return MessageRouter(ws_server)