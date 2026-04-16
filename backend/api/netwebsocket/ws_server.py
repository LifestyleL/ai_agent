import asyncio
import json
import base64
import threading
import websockets
from queue import Queue
from services.live2d.live2d_manager import Live2DManager
from .message_router import create_router
from .json_rpc_builder import JsonRpcBuilder
from .error_code import ErrorCode
from config import WS_PORT
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
        self.live2d = None
        self.tts = None
        self._initialized = True

        # [FIX] TTS 后台初始化（只启动一次）
        def init_tts():
            try:
                import time
                time.sleep(0.3)
                from services.modules.tts.tts_service import TTSService
                self.tts = TTSService()
                print("[OK] [后台] TTS 初始化完成")
            except Exception as e:
                print(f"[ERROR] [后台] TTS 初始化失败: {e}")
        
        threading.Thread(target=init_tts, daemon=True).start()

    async def _handle_client(self, websocket):
        self.websocket = websocket
        print("[PHONE] 前端已连接")

        if self.live2d is None:
            # Live2DManager already imported at top level
            self.live2d = Live2DManager()
            self.live2d.start()
            print("[LIVE2D] Live2D 动画循环已启动")

        asyncio.create_task(self._queue_consumer())

        # 创建消息路由器
        router = create_router(self)

        try:
            async for message in websocket:
                # 尝试使用新的路由器处理消息
                try:
                    # 路由器返回 True 表示成功处理，False 表示需要降级到旧逻辑
                    if router.route_message(message, websocket):
                        # 路由器已处理，继续下一条消息
                        continue
                except Exception as router_error:
                    print(f"[ROUTER] 路由器异常: {router_error}")
                    # 路由器出错，降级到旧逻辑
                    pass

                # 降级逻辑：原有的消息处理代码
                data = json.loads(message)

                # [FIX][FIX][FIX] 终极探针：每条消息都打印原始内容
                print(f"[PROBE] [探针] 收到原始消息: {message[:200]}")

                data = json.loads(message)
                msg_type = data.get("type", "无type")
                msg_text = data.get("text", data.get("content", data.get("message", "无文本")))
                print(f"[PROBE] [探针] type={msg_type}, text={msg_text}")

                # [FIX] 分支1: 心跳/信号
                if data.get("signal"):
                    if self.driver is None:
                        from core.agent.agent_driver import YumeDriver
                        self.driver = YumeDriver()
                    threading.Thread(target=self.driver.handle_user_input, args=("",), daemon=True).start()
                    continue

                text = data.get("text", "").strip()

                # [FIX] 分支2: TTS 测试
                if data.get("type") == "TTS_TEST" and text:
                    if self.tts is None:
                        print("[WAIT] TTS 还在初始化，稍后再试")
                        continue
                    loop = asyncio.get_running_loop()
                    pcm_bytes, mouth_frames = await loop.run_in_executor(
                        None, self.tts._synthesize_with_retry, text, data.get("emotion", "neutral")
                    )
                    if len(pcm_bytes) == 0:
                        continue
                    audio_b64 = base64.b64encode(pcm_bytes).decode("utf-8")
                    visemes = [f for f in mouth_frames if f['v'] > 0.01 or f == mouth_frames[0]]
                    await self._send({"type": "TTS_AUDIO", "audio_base64": audio_b64, "visemes": visemes})
                    continue

                # [FIX][FIX][FIX] 分支3: 用户正常输入（之前这里完全缺失！）
                if text and self.driver:
                    print(f"[消息] [WS] 收到用户输入: {text[:30]}...")
                    threading.Thread(target=self.driver.handle_user_input, args=(text,), daemon=True).start()
                    continue

                # 分支4: Live2D参数控制
                if msg_type == "PARAMS" and "data" in data:
                    print(f"[PARAMS] 收到Live2D参数: {data['data']}")
                    # 将参数数据（不带type包装）放入队列，让_queue_consumer发送给前端
                    self.send_queue.put(data['data'])
                    continue

        except websockets.exceptions.ConnectionClosed:
            print("[PHONE] 前端已断开")
            self.websocket = None
        except Exception as e:
            print(f"[错误] WS异常: {e}")

    async def _queue_consumer(self):
        while True:
            try:
                while self.send_queue.empty():
                    await asyncio.sleep(0.01)
                data = self.send_queue.get_nowait()
                if data.get("type") == "TTS_AUDIO":
                    print("[发送] [WS] 队列成功吐出 TTS 音频包，准备发给前端！")
                else:
                    # 添加参数发送调试日志
                    # print(f"[发送] [WS] 发送参数到前端: {json.dumps(data)[:200]}")
                    pass
                await self._send(data)
            except Exception:
                pass

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
