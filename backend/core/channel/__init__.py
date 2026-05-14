"""
channel: Channel 抽象 — 统一本地/QQ/Telegram 等频道的消息路由

每个 Channel 负责:
- pre_process:  注入频道特定上下文到 ThinkContext
- post_process: 频道特定后处理（PASS 检测等）
- send_response: 输出路由（TTS/Frontend vs OneBot WS）
"""

from backend.core.channel.base import Channel
from backend.core.channel.local_channel import LocalChannel
from backend.core.channel.qq_channel import QQChannel

__all__ = [
    "Channel",
    "LocalChannel",
    "QQChannel",
]
