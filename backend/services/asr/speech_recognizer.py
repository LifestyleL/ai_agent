"""
ASR 语音识别：DashScope Paraformer 实时识别封装
复用已有 DashScope API Key，中文优化。

改造为 Capability 实现，去掉全局单例。
"""

import asyncio
import base64
import json
import threading
import time
from typing import Callable, Optional

import dashscope
from dashscope.audio.asr import Recognition, RecognitionCallback

from services.asr.vad_processor import VADProcessor
import config


class SpeechRecognizer:
    """DashScope Paraformer 实时语音识别"""

    name = "asr"
    version = "1.0"

    def __init__(self):
        dashscope.api_key = config.DASHSCOPE_API_KEY
        self._on_result: Optional[Callable[[str, bool], None]] = None
        self._on_partial: Optional[Callable[[str], None]] = None
        self._recognition = None
        self._is_active = False
        self._accumulated_text = ""
        self._vad = VADProcessor()
        self._audio_buffer = bytearray()
        self._lock = threading.Lock()
        print("[ASR] SpeechRecognizer 初始化完成")

    # ── ASRCapability 窄接口 ──

    def set_result_callback(self, callback: Callable[[str, bool], None]):
        """设置识别结果回调 (text, is_final)"""
        self._on_result = callback

    def set_partial_callback(self, callback: Callable[[str], None]):
        """设置中间结果回调"""
        self._on_partial = callback

    async def start_listening(self):
        """开始监听（ASRCapability 协议）"""
        return await self.start_session()

    async def stop_listening(self):
        """停止监听（ASRCapability 协议）"""
        return await self.stop_session()

    def feed_audio(self, audio_bytes: bytes):
        """喂入音频数据（ASRCapability 协议，同步包装）"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.send_audio(audio_bytes))
            else:
                asyncio.run(self.send_audio(audio_bytes))
        except RuntimeError:
            asyncio.run(self.send_audio(audio_bytes))

    # ── Capability 生命周期 ──

    @property
    def enabled(self) -> bool:
        return True

    async def initialize(self, deps) -> None:
        pass

    async def shutdown(self) -> None:
        await self.close()

    def get_status(self) -> dict:
        return {
            "is_active": self._is_active,
            "accumulated_text": self._accumulated_text[:50] if self._accumulated_text else "",
        }

    # ── 原有接口 ──

    async def start_session(self):
        """开始 ASR 会话"""
        if self._is_active:
            return
        self._is_active = True
        self._accumulated_text = ""
        self._audio_buffer.clear()
        print("[ASR] 会话已开始")

    async def send_audio(self, pcm_bytes: bytes):
        """接收前端推送的音频帧 (16kHz, mono, int16)"""
        if not self._is_active:
            return

        with self._lock:
            self._audio_buffer.extend(pcm_bytes)

        vad_state = self._vad.process(pcm_bytes)

        if vad_state == "end":
            await self._finalize()

    async def stop_session(self):
        """停止 ASR 会话并取回最终结果"""
        await self._finalize()

    async def _finalize(self):
        """使用 DashScope Paraformer 一次性识别缓存的音频"""
        if not self._is_active:
            return

        with self._lock:
            if len(self._audio_buffer) < 800:  # 少于 50ms 音频
                self._is_active = False
                self._audio_buffer.clear()
                self._accumulated_text = ""
                return
            audio_to_recognize = bytes(self._audio_buffer)
            self._audio_buffer.clear()

        self._is_active = False

        try:
            text = await self._call_paraformer(audio_to_recognize)
            text = text.strip() if text else ""

            if text and self._on_result:
                self._on_result(text, True)

            if self._on_partial:
                self._on_partial(text)

            print(f"[ASR] 最终识别结果: '{text}'" if text else "[ASR] 识别结果为空")
            self._accumulated_text = ""

        except Exception as e:
            print(f"[ASR] 识别异常: {e}")
            self._accumulated_text = ""

    async def _call_paraformer(self, pcm_bytes: bytes) -> str:
        """调用 DashScope Paraformer 实时识别（REST 模式兜底）"""
        import aiohttp

        url = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
        headers = {
            "Authorization": f"Bearer {config.DASHSCOPE_API_KEY}",
            "Content-Type": "application/json",
        }

        audio_b64 = base64.b64encode(pcm_bytes).decode("utf-8")

        payload = {
            "model": "paraformer-realtime-v2",
            "input": {
                "audio": audio_b64,
                "sample_rate": 16000,
                "format": "pcm",
            },
            "parameters": {
                "language": "zh",
            },
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    result = await resp.json()
                    text = (
                        result.get("output", {})
                        .get("sentence", {})
                        .get("text", "")
                    )
                    return text
        except Exception as e:
            print(f"[ASR] Paraformer 请求失败: {e}")
            return ""

    async def close(self):
        """关闭 ASR 连接"""
        self._is_active = False
        with self._lock:
            self._audio_buffer.clear()
        self._accumulated_text = ""


# get_speech_recognizer() 已移除 — 请通过 DI 容器获取 SpeechRecognizer 实例
