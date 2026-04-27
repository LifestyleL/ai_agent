import time
from typing import Dict, Any


class FrontendBridge:
    """前端通信桥接：Live2D 指令 + 文本推送"""

    def __init__(self, driver):
        self.driver = driver

    def send_live2d_cmd(self, cmd: str, **kwargs):
        """发送高层指令到前端 Live2D SDK"""
        try:
            from api.netwebsocket.ws_server import ws_instance
            if ws_instance and hasattr(ws_instance, 'send_queue'):
                message = {"type": "LIVE2D_CMD", "cmd": cmd}
                message.update(kwargs)
                ws_instance.send_queue.put(message)
        except Exception as e:
            print(f"[WARN] [Live2D] 发送指令失败: {e}")

    def send_text_to_frontend(self, text: str, text_type: str = "chunk"):
        """发送文本消息到前端（打字机效果）"""
        try:
            from api.netwebsocket.ws_server import ws_instance
            if not ws_instance:
                return

            data = {
                "type": "TEXT_" + text_type.upper(),
                "text": text,
                "timestamp": time.time()
            }

            if hasattr(ws_instance, 'send_queue'):
                ws_instance.send_queue.put(data)
                if text_type == "thinking":
                    print(f"[WS] 思考提示已排队: '{text[:30]}...'")
                else:
                    print(f"[WS] 文本片段已排队: '{text[:30]}...'")
            else:
                print(f"[WARN] ws_instance没有send_queue属性")
        except ImportError:
            print(f"[WARN] WebSocket模块导入失败，前端打字机效果不可用")
        except Exception as e:
            print(f"[ERROR] 发送文本到前端失败: {e}")
