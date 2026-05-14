"""
Channel ABC — 频道抽象基类

每个实现负责：pre_process（注入上下文）→ post_process（后处理）→ send_response（输出路由）
"""

from abc import ABC, abstractmethod

from backend.core.think_pipeline.context import ThinkContext


class Channel(ABC):
    """频道抽象：统一本地/QQ/Telegram 等频道的消息路由"""

    @property
    def is_external(self) -> bool:
        """外部频道（QQ/Telegram）= True，本地（TTS/Frontend）= False"""
        return False

    @property
    def template_path(self) -> str:
        """频道对应的 system prompt 模板路径（相对 agent_memory/）"""
        return ""

    async def pre_process(self, ctx: ThinkContext) -> ThinkContext:
        """管线前处理：注入频道特定上下文（群聊信息、回应规则等）"""
        return ctx

    async def post_process(self, ctx: ThinkContext) -> ThinkContext:
        """管线后处理：PASS 检测、响应过滤等"""
        return ctx

    async def send_response(self, ctx: ThinkContext) -> None:
        """发送最终响应到频道的输出端（TTS/Frontend 或 OneBot WS）"""
        pass
