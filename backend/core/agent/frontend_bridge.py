import time
from typing import Dict, Any


class FrontendBridge:
    """前端通信桥接：Live2D 指令 + 文本推送"""

    def __init__(self, driver):
        self.driver = driver
        self.send_queue = None  # 由 main.py 注入 WSServer.send_queue

    def send_live2d_cmd(self, cmd: str, **kwargs):
        """发送高层指令到前端 Live2D SDK"""
        try:
            if self.send_queue is None:
                return
            message = {"type": "LIVE2D_CMD", "cmd": cmd}
            message.update(kwargs)
            self.send_queue.put(message)
        except Exception as e:
            print(f"[WARN] [Live2D] 发送指令失败: {e}")

    def send_text_to_frontend(self, text: str, text_type: str = "chunk"):
        """发送文本消息到前端（打字机效果）"""
        try:
            if self.send_queue is None:
                return

            data = {
                "type": "TEXT_" + text_type.upper(),
                "text": text,
                "timestamp": time.time()
            }

            self.send_queue.put(data)
            if text_type == "thinking":
                print(f"[WS] 思考提示已排队: '{text[:30]}...'")
            else:
                print(f"[WS] 文本片段已排队: '{text[:30]}...'")
        except ImportError:
            print(f"[WARN] WebSocket模块导入失败，前端打字机效果不可用")
        except Exception as e:
            print(f"[ERROR] 发送文本到前端失败: {e}")

    def send_interrupt_command(self):
        """通知前端停止播放音频"""
        try:
            if self.send_queue:
                self.send_queue.put({"type": "TTS_STOP"})
                print("[FrontendBridge] TTS_STOP 指令已发送")
        except Exception as e:
            print(f"[ERROR] 发送 TTS_STOP 失败: {e}")
