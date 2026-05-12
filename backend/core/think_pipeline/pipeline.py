"""
ThinkPipeline 编排器 + PipelineStage 抽象 + ResponseDispatcher 协议

依赖方向：main(组装) → Pipeline(编排) → Stage(业务)
Stage 之间互不知晓，Pipeline 负责编排（含自循环重入）。
"""

import logging
from abc import ABC, abstractmethod
from typing import List, Protocol

from backend.core.think_pipeline.context import ThinkContext

logger = logging.getLogger(__name__)


class ResponseDispatcher(Protocol):
    """LLM Stream Stage 的抽象依赖，隔离 TTS + Live2D 的具体实现"""

    def set_emotion(self, emotion: str) -> None:
        """设置当前情绪：推送 TTS 标签 + Live2D 表情"""
        ...

    def enqueue_tts(self, text: str, emotion: str) -> None:
        """将文本送入 TTS 队列"""
        ...

    def send_to_frontend(self, text: str, msg_type: str) -> None:
        """推送文本到前端（打字机/思考提示）"""
        ...

    def speak_complete(self, text: str) -> None:
        """完整文本直接播报（非流式降级路径）"""
        ...


class PipelineStage(ABC):
    """Pipeline 阶段抽象基类"""

    @abstractmethod
    async def process(self, ctx: ThinkContext) -> ThinkContext:
        """处理上下文，返回新上下文（不可变）"""
        ...


class ThinkPipeline:
    """编排器：组合所有 Stage，处理自循环重入"""

    def __init__(self, stages: List[PipelineStage]):
        self._stages = stages

    async def execute(self, ctx: ThinkContext) -> ThinkContext:
        for stage in self._stages:
            ctx = await stage.process(ctx)
            if ctx.error or ctx.needs_recall_retry:
                break

        if ctx.needs_recall_retry and ctx.recall_round < ctx.max_recall_round and not ctx.error:
            logger.info("[Pipeline] 检测到回忆信号，启动深挖重入 (round=%s)", ctx.recall_round)
            # 替换 user_input 为补充提示，防止 LLM 重复完整回答
            original_question = ctx.user_input  # 此时的 user_input 还是原始问题
            continuation_prompt = (
                f"<system>\n"
                f"你刚才在回答用户问题时触发了内部记忆查询，查询已完成。\n"
                f"你之前已经回答过原始问题了，现在只需要补充你没想到的新内容。\n"
                f"</system>\n\n"
                f"<recall_result>\n{ctx.deep_recall_result}\n</recall_result>\n\n"
                f"<original_question>\n{original_question}\n</original_question>\n\n"
                f"<guidelines>\n"
                f"  <rule>只补充你刚才没想到的新内容，不要重复已经说过的话</rule>\n"
                f"  <rule>如果查询结果没有实质新信息，说一句自然的收尾（如'差不多就是这些啦'）</rule>\n"
                f"  <rule>保持简短，1-2句话即可</rule>\n"
                f"</guidelines>"
            )
            ctx = ctx.replace(needs_recall_retry=False, user_input=continuation_prompt)
            ctx = await self.execute(ctx)

        return ctx
