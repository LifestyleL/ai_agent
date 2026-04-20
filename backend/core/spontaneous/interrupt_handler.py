"""
ASR打断处理器（预留）：处理语音识别实时打断主动发言的能力

预留接口，为未来语音交互做准备。
"""

import asyncio
import time
from typing import Optional, Callable, Any, Dict
from enum import Enum


class InterruptType(Enum):
    """打断类型"""
    VOICE_START = "voice_start"      # 检测到用户开始说话
    VOICE_CONTENT = "voice_content"  # 识别到语音内容
    MANUAL_STOP = "manual_stop"      # 手动停止（如按钮）
    TIMEOUT = "timeout"              # 超时打断


class InterruptHandler:
    """ASR打断处理器（预留实现）"""

    def __init__(self):
        self.is_active = False
        self.current_speech_text = ""  # 当前正在说的话
        self.interrupt_callback = None  # 打断回调函数
        self.last_interrupt_time = 0
        self.interrupt_cooldown = 1.0  # 打断冷却时间（秒）

    def set_interrupt_callback(self, callback: Callable[[InterruptType, str], None]):
        """设置打断回调函数"""
        self.interrupt_callback = callback
        print(f"[InterruptHandler] 打断回调已设置")

    def start_speech(self, text: str):
        """开始说话（记录当前发言内容）"""
        self.is_active = True
        self.current_speech_text = text
        print(f"[InterruptHandler] 开始说话: '{text[:50]}...'")

    def end_speech(self):
        """结束说话"""
        self.is_active = False
        self.current_speech_text = ""
        print(f"[InterruptHandler] 结束说话")

    def simulate_voice_interrupt(self, interrupt_type: InterruptType, content: str = ""):
        """
        模拟语音打断（用于测试）

        Args:
            interrupt_type: 打断类型
            content: 识别到的内容（如果适用）
        """
        if not self.is_active:
            print(f"[InterruptHandler] 模拟打断失败：当前没有在说话")
            return False

        now = time.time()
        if now - self.last_interrupt_time < self.interrupt_cooldown:
            print(f"[InterruptHandler] 模拟打断失败：冷却中 ({self.interrupt_cooldown:.1f}s)")
            return False

        self.last_interrupt_time = now
        print(f"[InterruptHandler] 模拟{interrupt_type.value}打断: {content}")

        if self.interrupt_callback:
            self.interrupt_callback(interrupt_type, content)

        return True

    def handle_asr_result(self, text: str, is_final: bool = True):
        """
        处理ASR识别结果（预留）

        Args:
            text: 识别到的文本
            is_final: 是否为最终结果
        """
        if not self.is_active:
            # 不在说话时，ASR结果直接作为用户输入
            print(f"[InterruptHandler] ASR结果（非打断）: '{text}'")
            return

        # 检测是否应该打断
        should_interrupt = self._should_interrupt_for_asr(text, is_final)

        if should_interrupt:
            interrupt_type = InterruptType.VOICE_CONTENT if is_final else InterruptType.VOICE_START
            print(f"[InterruptHandler] ASR打断: {interrupt_type.value}, 内容: '{text}'")

            if self.interrupt_callback:
                self.interrupt_callback(interrupt_type, text)

    def _should_interrupt_for_asr(self, text: str, is_final: bool) -> bool:
        """
        判断ASR结果是否应该触发打断（预留逻辑）

        实际实现应考虑：
        1. 语音能量/开始检测
        2. 识别置信度
        3. 内容重要性
        4. 当前发言的进展
        """
        if not text.strip():
            return False

        # 简单逻辑：最终结果且非空就打断
        if is_final and len(text.strip()) > 1:
            return True

        return False

    def manual_interrupt(self, reason: str = "用户手动停止"):
        """手动打断"""
        if self.is_active:
            print(f"[InterruptHandler] 手动打断: {reason}")
            if self.interrupt_callback:
                self.interrupt_callback(InterruptType.MANUAL_STOP, reason)
            return True
        return False

    def get_status(self) -> Dict[str, Any]:
        """获取当前状态"""
        return {
            "is_active": self.is_active,
            "current_speech_length": len(self.current_speech_text),
            "last_interrupt_ago": time.time() - self.last_interrupt_time if self.last_interrupt_time > 0 else None,
            "has_callback": self.interrupt_callback is not None
        }


# 全局实例（单例模式）
_global_interrupt_handler: Optional[InterruptHandler] = None


def get_interrupt_handler() -> InterruptHandler:
    """获取全局打断处理器实例"""
    global _global_interrupt_handler
    if _global_interrupt_handler is None:
        _global_interrupt_handler = InterruptHandler()
        print("[InterruptHandler] 创建全局实例")
    return _global_interrupt_handler


def setup_interrupt_handler() -> InterruptHandler:
    """设置打断处理器（兼容性函数）"""
    return get_interrupt_handler()