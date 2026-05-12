"""
轻量 VAD 处理器：基于音量门限的语音活动检测
当使用 DashScope Paraformer 自带 VAD 时可切换为透传模式。
"""

import struct
import math
from typing import Optional


class VADProcessor:
    """基于 RMS 能量门限的 VAD"""

    def __init__(
        self,
        threshold_db: float = -40.0,
        min_speech_ms: int = 300,
        max_silence_ms: int = 800,
    ):
        self.threshold_db = threshold_db
        self.min_speech_frames = max(1, min_speech_ms // 20)  # 按 20ms 帧计算
        self.max_silence_frames = max(1, max_silence_ms // 20)

        self._speech_frames = 0
        self._silence_frames = 0
        self._in_speech = False

    def _rms_db(self, pcm_bytes: bytes) -> float:
        """计算 PCM int16 音频帧的 RMS 分贝值"""
        if len(pcm_bytes) < 2:
            return -100.0

        sample_count = len(pcm_bytes) // 2
        try:
            samples = struct.unpack(f"<{sample_count}h", pcm_bytes[: sample_count * 2])
        except struct.error:
            return -100.0

        sum_sq = sum(s * s for s in samples)
        rms = math.sqrt(sum_sq / sample_count) if sample_count > 0 else 0.0
        if rms < 1:
            return -100.0
        return 20.0 * math.log10(rms / 32768.0) + 3.0  # +3dB 补偿

    def process(self, pcm_bytes: bytes) -> str:
        """
        处理一帧音频，返回状态:
          "speech"  — 说话中
          "silence" — 静音中
          "start"   — 检测到说话开始
          "end"     — 检测到说话结束
        """
        db = self._rms_db(pcm_bytes)
        is_speech = db > self.threshold_db

        if is_speech:
            self._silence_frames = 0
            self._speech_frames += 1

            if not self._in_speech and self._speech_frames >= self.min_speech_frames:
                self._in_speech = True
                return "start"

            return "speech"
        else:
            self._speech_frames = 0
            self._silence_frames += 1

            if self._in_speech and self._silence_frames >= self.max_silence_frames:
                self._in_speech = False
                return "end"

            return "silence"

    def reset(self):
        self._speech_frames = 0
        self._silence_frames = 0
        self._in_speech = False
