"""
Stage 3: 流式 LLM + 逐句 TTS 分发

调用 LLM 流式 API，逐 token 产出，检测句子边界，
将完整句子通过 ResponseDispatcher 送入 TTS 队列。
流式失败时降级为非流式调用。
"""

import asyncio
import logging
import re

from backend.core.think_pipeline.context import ThinkContext
from backend.core.think_pipeline.pipeline import PipelineStage, ResponseDispatcher

logger = logging.getLogger(__name__)

_SENTENCE_END = ["。", "！", "？", "\n"]
_SEARCH_DIRECTIVE = re.compile(r'\[MEMORY_SEARCH:\s*.+?\]', re.IGNORECASE)


def _has_content(text: str) -> bool:
    """检查文本是否包含有效内容（中文或英文数字）"""
    return any(c.isalnum() or '一' <= c <= '鿿' for c in text)


class LLMStreamStage(PipelineStage):
    """流式 LLM 调用 + 逐句 TTS 分发。有截图时切 VLM，否则用快速文本模型。"""

    def __init__(self, llm_api, vision_llm=None, dispatcher: ResponseDispatcher = None):
        self._llm = llm_api            # 文本模型（快速）
        self._vision_llm = vision_llm  # VLM 多模态（看图）
        self._dispatcher = dispatcher

    def _pick_llm(self, ctx: ThinkContext):
        """有截图 → VLM；无截图 → 文本模型"""
        if ctx.screenshot_b64 and self._vision_llm:
            return self._vision_llm
        return self._llm

    async def process(self, ctx: ThinkContext) -> ThinkContext:
        # 构建用户消息：有截图时用多模态格式
        if ctx.screenshot_b64:
            user_content = [
                {"type": "text", "text": ctx.user_input},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{ctx.screenshot_b64}"}}
            ]
        else:
            user_content = ctx.user_input

        messages = [
            {"role": "system", "content": ctx.system_prompt},
            {"role": "user", "content": user_content},
        ]

        # ── DEBUG: 打印主 LLM 提示词 ──
        logger.warning(f"\n{'='*60}\n[LLMStream] LLM 提示词 (主对话流式):\n"
                       f"  system_prompt ({len(ctx.system_prompt)} chars):\n{ctx.system_prompt}\n"
                       f"  user_input ({len(ctx.user_input)} chars): {ctx.user_input}\n"
                       f"{'='*60}")

        response_text = ""
        streamed_to_tts = False

        llm = self._pick_llm(ctx)
        try:
            pending = ""
            async for token in llm.chat_stream_async(messages, temperature=0.7):
                if token.startswith("[ERROR]"):
                    raise RuntimeError(f"流式中断: {token}")
                response_text += token
                pending += token

                cut = -1
                for p in _SENTENCE_END:
                    pos = pending.find(p)
                    if pos != -1 and (cut == -1 or pos < cut):
                        cut = pos

                if cut != -1:
                    sentence = pending[: cut + 1]
                    pending = pending[cut + 1 :]
                    # 过滤 [MEMORY_SEARCH: ...] 指令，不送 TTS
                    sentence = _SEARCH_DIRECTIVE.sub("", sentence)
                    clean = sentence.strip()
                    if _has_content(clean) and len(clean) >= 2:
                        self._dispatcher.enqueue_tts(sentence, ctx.emotion_state)
                        streamed_to_tts = True
                        await asyncio.sleep(0)  # 让出事件循环，给队列消费者机会发送音频

            # 处理尾部残留文本
            if pending.strip():
                pending = _SEARCH_DIRECTIVE.sub("", pending)
                clean = pending.strip()
                if _has_content(clean) and len(clean) >= 2:
                    self._dispatcher.enqueue_tts(pending, ctx.emotion_state)
                    streamed_to_tts = True

            response_text = response_text.strip().strip('"').strip("'")

        except Exception as e:
            logger.error("[LLMStream] 流式LLM失败: %s, 回退到非流式", e)
            try:
                raw = await llm.ask_with_system_async(
                    ctx.system_prompt, ctx.user_input, temperature=0.7
                )
                response_text = raw.strip().strip('"').strip("'") if raw else ""
                if response_text:
                    # 过滤指令后播报
                    clean_for_tts = _SEARCH_DIRECTIVE.sub("", response_text).strip()
                    if clean_for_tts:
                        await asyncio.to_thread(self._dispatcher.speak_complete, clean_for_tts)
                        streamed_to_tts = True
            except Exception as e2:
                logger.error("[LLMStream] 非流式LLM也失败: %s", e2)
                return ctx.replace(error=str(e2))

        if not response_text or response_text.isspace():
            logger.error("[LLMStream] 主 LLM 返回空回复")
            return ctx.replace(error="主 LLM 返回空回复")

        logger.info("[LLMStream] 回复长度=%s streamed=%s", len(response_text), streamed_to_tts)
        return ctx.replace(response_text=response_text, streamed_to_tts=streamed_to_tts)
