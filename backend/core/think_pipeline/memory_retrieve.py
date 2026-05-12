"""
Stage 1: 记忆检索 + 情绪推断

委托 MemoryCore 执行意图检测、BFS 检索、情绪推断，
将结果写入 ThinkContext。
"""

import logging
from typing import Optional

from backend.core.think_pipeline.context import ThinkContext
from backend.core.think_pipeline.pipeline import PipelineStage, ResponseDispatcher
from backend.core.emotion.emotion_engine import EmotionEngine

logger = logging.getLogger(__name__)


class MemoryRetrieveStage(PipelineStage):
    """记忆检索 + 情绪推断（合并原 Step 0 + Step 0.5）"""

    def __init__(
        self,
        memory_core,
        emotion_engine: EmotionEngine,
        dispatcher: Optional[ResponseDispatcher] = None,
    ):
        self._memory = memory_core
        self._emotion = emotion_engine
        self._dispatcher = dispatcher

    async def process(self, ctx: ThinkContext) -> ThinkContext:
        structured = {
            "diary_memory": "（暂无日记记录）",
            "precise_query": "（本次未触发精准查询）",
            "pre_search": "（无预检索结果）",
            "deep_recall": "（无深层记忆浮现）",
            "terrain": "",
            "time_context": "",
            "write_request": False,
        }

        if self._memory:
            structured = self._memory.build_structured_sections(
                ctx.user_input, ctx.deep_recall_result
            )
            # 旧版兼容：deep_recall_result 已有值则覆盖
            if ctx.deep_recall_result:
                structured["deep_recall"] = ctx.deep_recall_result

            # 旧版兼容：recall_injection 追加到 deep_recall
            recall_injection = ctx.memory_context.get("recall_injection", "")
            if recall_injection:
                if structured.get("deep_recall", "") == "（无深层记忆浮现）":
                    structured["deep_recall"] = recall_injection.replace("【潜意识浮现】", "").strip()
                else:
                    structured["deep_recall"] = structured.get("deep_recall", "") + "\n" + recall_injection

            structured["time_context"] = (
                self._memory.get_time_context() if hasattr(self._memory, "get_time_context") else ""
            )

            # 短期对话历史（供 PromptBuildStage 使用，保持其纯函数性）
            structured["_history"] = (
                self._memory.get_short_term_context(max_turns=20)
                if hasattr(self._memory, "get_short_term_context")
                else "（暂无对话记录）"
            )

            # 压缩过的旧对话摘要
            structured["_compressed_history"] = (
                self._memory.get_compressed_summary()
                if hasattr(self._memory, "get_compressed_summary")
                else ""
            )

            # 当前视觉观察（如果有截图，注入提示词）
            structured["_visual_observation"] = (
                self._memory.get_short_term_visual()
                if hasattr(self._memory, "get_short_term_visual")
                else ""
            )

            # 情绪推断（纯规则，0 延迟）
            etype, estrength = self._emotion.infer_from_text(ctx.user_input)
            if estrength > 0:
                self._emotion.update_emotion(etype, estrength)

        # 计算情绪标签
        emotion_label = EmotionEngine.type_to_label(self._emotion.type)

        # 推送情绪到 TTS + Live2D
        if self._dispatcher:
            self._dispatcher.set_emotion(emotion_label)

        logger.info(
            "[MemoryRetrieve] diary=%sc precise=%sc presearch=%sc emotion=%s",
            len(structured.get("diary_memory", "")),
            len(structured.get("precise_query", "")),
            len(structured.get("pre_search", "")),
            emotion_label,
        )

        return ctx.replace(
            memory_context=structured,
            emotion_state=emotion_label,
        )
