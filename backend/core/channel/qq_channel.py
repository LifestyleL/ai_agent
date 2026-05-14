"""
QQChannel — QQ 频道（OneBot v11 反向 WS）
"""

import logging
import re
from typing import Optional

from backend.core.channel.base import Channel
from backend.core.think_pipeline.context import ThinkContext

logger = logging.getLogger(__name__)

# PASS 检测：非强制消息时 LLM 可能输出 [PASS] 表示沉默
_PASS_PATTERN = re.compile(r'^\s*\[PASS\]', re.IGNORECASE)

# 意图关键词（轻量预搜索，结果注入 precise_query）
_MEMORY_KEYWORDS = [
    "记得", "不记得", "忘了", "忘记", "回忆", "想起", "想起来",
    "以前", "之前", "上次", "上回", "过去", "那时候", "曾经",
    "说过", "聊过", "提到", "提过",
]
_DIARY_KEYWORDS = ["日记", "日志", "记录", "整理记忆", "整理日记"]
_DATE_HINT_KEYWORDS = ["几号", "什么时候", "哪天", "那天"]


class QQChannel(Channel):
    """QQ 频道：群聊上下文注入 + PASS 检测"""

    name = "qq"

    def __init__(self, memory=None, emotion=None):
        self._memory = memory
        self._emotion = emotion
        # 外部注入的会话参数（由 WS handler 在每次请求时设置）
        self._group_context: str = ""
        self._current_speaker: str = ""
        self._is_forced: bool = False

    @property
    def is_external(self) -> bool:
        return True

    @property
    def template_path(self) -> str:
        return "prompts/yume_qq_system.md"

    def set_session(self, group_context: str = "", current_speaker: str = "",
                    is_forced: bool = False):
        """由 WS handler 在每次请求前调用，设置当前会话参数"""
        self._group_context = group_context
        self._current_speaker = current_speaker or "未知"
        self._is_forced = is_forced

    async def pre_process(self, ctx: ThinkContext) -> ThinkContext:
        """注入 QQ 群聊上下文到 ThinkContext"""
        # 意图检测 + 预搜索（轻量关键词，结果注入 precise_query）
        intent_type, search_context = self._detect_intent(ctx.user_input)
        if search_context and self._memory:
            existing = ctx.memory_context.get("precise_query", "")
            if "未触发" in existing or not existing:
                ctx.memory_context["precise_query"] = search_context
            else:
                ctx.memory_context["precise_query"] = existing + "\n" + search_context

        # 群聊上下文
        ctx.memory_context["_group_context"] = self._group_context
        ctx.memory_context["_current_speaker"] = self._current_speaker
        ctx.memory_context["_is_forced"] = "true" if self._is_forced else "false"

        # 回应规则
        if self._is_forced:
            ctx.memory_context["_respond_rule"] = (
                "现在是强制回应模式——有人@你或喊你名字，你必须出声回应，不能沉默。"
            )
        else:
            ctx.memory_context["_respond_rule"] = (
                "现在是智能回应模式——看群聊上下文和当前消息，判断是否该出声：\n"
                "• 消息是跟别人说的（不是对你）→ 输出 [PASS]，不要其他内容\n"
                "• 消息在跟你说话或可以自然接话 → 正常回复\n"
                "• 只是表情包、单字、无意义消息 → 输出 [PASS]\n"
                "记住：[PASS] 必须独占一行，不要带任何其他文字。"
            )

        return ctx.replace(
            template_path=self.template_path,
            channel_name="qq",
        )

    async def post_process(self, ctx: ThinkContext) -> ThinkContext:
        """PASS 检测：非强制消息 + 回复以 [PASS] 开头 → 清空回复"""
        if not ctx.response_text:
            return ctx

        if not self._is_forced and _PASS_PATTERN.match(ctx.response_text.strip()):
            logger.info("[QQChannel] LLM pass: stay silent")
            return ctx.replace(response_text="")

        return ctx

    async def send_response(self, ctx: ThinkContext) -> None:
        """QQ 频道不在此发送 — WS handler 直接读 ctx.response_text"""
        pass

    # ── 意图检测（轻量关键词预搜索）──

    def _detect_intent(self, text: str):
        """检测用户意图类型 + 执行预搜索。返回 (intent_type, search_result_str)"""
        intent_type = "chat"
        search_result = ""

        text_lower = text.lower()

        # 日记意图
        if any(kw in text_lower for kw in _DIARY_KEYWORDS):
            intent_type = "diary_lookup"
            search_result = self._do_diary_lookup()
        # 日期意图
        elif any(kw in text_lower for kw in _DATE_HINT_KEYWORDS):
            intent_type = "date_lookup"
            search_result = self._do_date_search()
        # 记忆意图
        elif any(kw in text_lower for kw in _MEMORY_KEYWORDS):
            intent_type = "memory_search"
            search_result = self._do_memory_search(text)

        return intent_type, search_result

    def _do_memory_search(self, text: str) -> str:
        """关键词记忆预搜索"""
        if not self._memory:
            return ""
        try:
            raw = self._memory._context_builder.search_memory(keyword=text[:80], limit=5)
            return raw if raw and "未找到" not in raw else ""
        except Exception:
            return ""

    def _do_diary_lookup(self) -> str:
        """查找最新日记"""
        if not self._memory:
            return ""
        try:
            cb = self._memory._context_builder
            diary_text = cb.search_memory(keyword="日记索引", limit=3)
            return diary_text if diary_text and "未找到" not in diary_text else ""
        except Exception:
            return ""

    def _do_date_search(self) -> str:
        """日期相关搜索（轻量）"""
        if not self._memory:
            return ""
        try:
            cb = self._memory._context_builder
            result = cb._query_temporal("最近一周有什么记录")
            return result if result else ""
        except Exception:
            return ""
