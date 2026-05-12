"""
DefaultResponseDispatcher: ResponseDispatcher 协议的具体实现

包装 TTSManager + FrontendBridge，实现统一的设置情绪/入队TTS/推前端/完整播报。
"""


class DefaultResponseDispatcher:
    """将 TTSManager + FrontendBridge 组合为 ResponseDispatcher"""

    def __init__(self, tts_manager, frontend_bridge):
        self._tts = tts_manager
        self._frontend = frontend_bridge

    def set_emotion(self, emotion: str) -> None:
        """推送情绪标签到 TTS + Live2D"""
        self._tts.current_emotion = emotion
        self._frontend.send_live2d_cmd("emotion", emotion=emotion)

    def enqueue_tts(self, text: str, emotion: str) -> None:
        """流式断句 → TTS 队列"""
        self._tts.enqueue_text(text, emotion)

    def send_to_frontend(self, text: str, msg_type: str) -> None:
        """文本推前端"""
        self._frontend.send_text_to_frontend(text, msg_type)

    def speak_complete(self, text: str) -> None:
        """完整文本播报（非流式降级）"""
        self._tts.speak_final_text(text)
