import asyncio
import json
import base64
import threading
import websockets
from queue import Queue
from .message_router import create_router
from .json_rpc_builder import JsonRpcBuilder
from .error_code import ErrorCode
from config import WS_PORT
from core.state_machine.state_machine import get_state_machine, State, Event
from core.state_machine.transitions import setup_base_transitions
from core.state_machine.actions import create_real_think_action, create_real_do_tool_action
from backend.plugins.registry import get_global_registry
class WSServer:
    _instance = None 
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.send_queue = Queue()
        self.websocket = None
        self.driver = None
        self.tts = None
        self._initialized = True

        # [FIX] TTS 后台初始化（只启动一次）
        def init_tts():
            try:
                import time
                time.sleep(0.3)
                from services.tts.tts_service import TTSService
                self.tts = TTSService()
                print("[OK] [后台] TTS 初始化完成")
            except Exception as e:
                print(f"[ERROR] [后台] TTS 初始化失败: {e}")
        
        threading.Thread(target=init_tts, daemon=True).start()

    def _setup_driver_state_machine(self, driver):
        """配置driver的状态机（使用真实Action引擎，与main.py保持一致）"""
        print("[WSServer] 配置driver状态机（真实引擎）...")
        sm = get_state_machine()
        setup_base_transitions(sm)
        # 获取全局工具注册中心
        reg = get_global_registry()
        # 绑定真实 Action 引擎
        real_think = create_real_think_action(state_machine=sm, registry=reg, driver_instance=driver)
        real_do_tool = create_real_do_tool_action(state_machine=sm, registry=reg)
        sm.register_action(State.THINK, real_think)
        sm.register_action(State.DO_TOOL, real_do_tool)
        driver.state_machine = sm
        print("[WSServer] 状态机配置完成（真实引擎）")

    async def _handle_client(self, websocket):
        self.websocket = websocket
        print("[PHONE] 前端已连接")

        asyncio.create_task(self._queue_consumer())

        # 创建消息路由器（传递当前事件循环）
        router = create_router(self, asyncio.get_running_loop())

        try:
            async for message in websocket:
                # 使用路由器处理消息
                try:
                    if router.route_message(message, websocket):
                        # 路由器已处理，继续下一条消息
                        continue
                    else:
                        # 路由器无法处理的消息（未知通道）
                        print(f"[WARN] [ROUTER] 无法路由的消息: {message[:200]}")
                        continue
                except Exception as router_error:
                    print(f"[ERROR] [ROUTER] 路由器异常: {router_error}")
                    # 继续处理下一条消息，不降级
                    continue

        except websockets.exceptions.ConnectionClosed:
            print("[PHONE] 前端已断开")
            self.websocket = None
        except Exception as e:
            print(f"[错误] WS异常: {e}")

    async def _queue_consumer(self):
        loop = asyncio.get_running_loop()
        print("[WS] 队列消费者已启动")
        while True:
            try:
                data = await loop.run_in_executor(None, self.send_queue.get)
                if data.get("type") == "TTS_AUDIO":
                    print(f"[发送] [WS] 队列成功吐出 TTS 音频包 ({len(data.get('audio_base64',''))}B base64)，准备发给前端！")
                else:
                    pass
                await self._send(data)
            except Exception as e:
                print(f"[ERROR] [WS] 队列消费者异常: {e}")
                import traceback
                traceback.print_exc()

    def _infer_channel_from_data(self, data):
        """
        根据数据内容推断所属通道

        Args:
            data: 要发送的数据

        Returns:
            str: 通道名称 ("animation", "audio", "control")
        """
        # 检查是否为 TTS 音频数据
        if isinstance(data, dict) and data.get("type") == "TTS_AUDIO":
            return "audio"

        # 检查是否为 Live2D 参数数据
        # Live2D 参数通常包含 Param 开头的键
        if isinstance(data, dict):
            for key in data.keys():
                if isinstance(key, str) and key.startswith("Param"):
                    return "animation"

        # 默认为控制通道
        return "control"

    async def _send(self, data):
        if self.websocket:
            try:
                # JSON-RPC 包装逻辑
                if JsonRpcBuilder.is_jsonrpc_enabled():
                    # 推断通道
                    channel = self._infer_channel_from_data(data)

                    # 构建 JSON-RPC 响应
                    wrapped_data = JsonRpcBuilder.wrap_data_for_channel(
                        channel=channel,
                        data=data,
                        request_id=None  # 目前没有请求ID追踪
                    )

                    json_str = json.dumps(wrapped_data)
                    print(f"[JSON-RPC] 发送包装数据 (通道: {channel}): {json_str[:200]}...")
                else:
                    json_str = json.dumps(data)

                await self.websocket.send(json_str)

                # 调试：记录发送成功
                if "type" not in data or data.get("type") != "TTS_AUDIO":
                    pass
                    #print(f"[发送成功] [WS] 已发送消息到前端，长度: {len(json_str)}")
            except Exception as e:
                print(f"[发送失败] [WS] 发送到前端失败: {e}")

                # JSON-RPC 错误响应（如果启用）
                if JsonRpcBuilder.is_jsonrpc_enabled():
                    try:
                        error_response = JsonRpcBuilder.build_error_response(
                            code=ErrorCode.INTERNAL_ERROR,
                            message=f"发送失败: {str(e)}",
                            request_id=None
                        )
                        await self.websocket.send(json.dumps(error_response))
                    except Exception as inner_e:
                        print(f"[发送失败] [WS] 发送错误响应也失败: {inner_e}")
    #端口监听，使用端口8765
    async def start_server(self, host="0.0.0.0", port=WS_PORT):
        print(f"[启动] 启动 WebSocket 服务 ws://{host}:{port}")
        return await websockets.serve(self._handle_client, host, port)

ws_instance = WSServer()
