#!/usr/bin/env python3
"""
Live2D 软屏蔽管理器

实现空接口，提供与原有 Live2DManager 兼容的 API。
当 LIVE2D_ENABLED 为 false 时，所有方法为空操作。
"""

import config


class Live2DManager:
    """Live2D 空实现（软屏蔽）"""

    def __init__(self):
        self.enabled = config.LIVE2D_ENABLED
        if self.enabled:
            print("[Live2DManager] Live2D 功能已启用（但未实现具体功能）")
        else:
            print("[Live2DManager] Live2D 功能已禁用（空实现）")

    def set_emotion_mode(self, emotion: str) -> None:
        """设置情绪模式（空实现）"""
        if self.enabled:
            # 理论上可以调用真实实现，但此处为空
            pass
        # 禁用时什么也不做

    def start(self) -> None:
        """启动 Live2D 动画循环（空实现）"""
        if self.enabled:
            print("[Live2DManager] Live2D 动画循环已启动（空实现）")
        # 禁用时什么也不做

    def update(self) -> None:
        """更新 Live2D 状态（空实现）"""
        if self.enabled:
            pass

    def send_params(self, params: dict) -> None:
        """发送 Live2D 参数（空实现）"""
        if self.enabled:
            pass

    def shutdown(self) -> None:
        """关闭 Live2D（空实现）"""
        if self.enabled:
            pass

    def send_tts(self, audio_b64: str, mouth_frames: list) -> None:
        """发送 TTS 音频和嘴型数据到 Live2D（空实现）"""
        if self.enabled:
            # 理论上可以调用真实实现，但此处为空
            pass
        # 禁用时什么也不做