"""
卡片管理器：LLM 提取 + 算法打分/链接，异步记忆写入
"""
import json
import re
import threading
from datetime import datetime
from typing import Optional
import config
from core.llm.llm_api import LLMAPI
from core.memory.card import (
    Card, generate_card_id, score_importance,
)


# ── 输入清洗：去除系统注入的 XML 标签，防止泄漏到记忆卡片 ──

_XML_TAG_PATTERN = re.compile(
    r'</?(?:system|recall_result|original_question|guidelines|rule|memory_context'
    r'|injected_context|deep_recall|search_result|context_block)'
    r'[^>]*>.*?</(?:system|recall_result|original_question|guidelines|rule'
    r'|memory_context|injected_context|deep_recall|search_result|context_block)>',
    re.DOTALL
)
_XML_SELF_CLOSING = re.compile(
    r'<(?:system|recall_result|original_question|guidelines|rule|memory_context'
    r'|injected_context|deep_recall|search_result|context_block)[^>]*/>'
)


def sanitize_card_text(text: str) -> str:
    """去除内部 XML 标签，只保留用户/AI 的真实对话"""
    text = _XML_TAG_PATTERN.sub('', text)
    text = _XML_SELF_CLOSING.sub('', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


class CardManager:
    def __init__(self, card_store, llm_api=None, emotion_engine=None,
                 short_term=None, diary_writer=None, context_builder=None):
        self._card_store = card_store
        self._llm_api = llm_api
        self._emotion_engine = emotion_engine
        self._short_term = short_term
        self._diary_writer = diary_writer
        self._context_builder = context_builder
        self._write_threads: list = []

    # ── 卡片创建 ──

    def _async_create_card(self, user_text: str, ai_text: str):
        t = threading.Thread(
            target=self._create_card_sync,
            args=(user_text, ai_text),
            daemon=True,
        )
        t.start()
        self._write_threads.append(t)
        self._write_threads = [t for t in self._write_threads if t.is_alive()]

    def _create_card_sync(self, user_text: str, ai_text: str):
        try:
            if not self._llm_api:
                return

            # 清洗内部 XML 标签，防止系统提示词泄漏到记忆卡片
            clean_user = sanitize_card_text(user_text)
            clean_ai = sanitize_card_text(ai_text)

            prompt = (
                '## 记忆卡片生成\n'
                '你正在整理自己的记忆。请以第一人称（我是 yume）的视角，从以下对话中提取关键信息，生成一张记忆卡片：\n\n'
                '【对话】\n'
                f'用户: {clean_user[:300]}\n'
                f'yume: {clean_ai[:300]}\n\n'
                '【要求】\n'
                '- topic 和 content 都必须用第一人称"我"来写（你是 yume）\n'
                '- 用"他"指代用户，不要用"用户"\n'
                '- content 示例："我今天和用户聊了...，他说...，我觉得..."\n\n'
                '【输出格式】(严格 JSON，不要输出其他内容)\n'
                '{\n'
                '  "topic": "一句话主题 (≤30字，第一人称)",\n'
                '  "tags": ["标签1", "标签2", ...],\n'
                '  "content": "卡片正文 (≤200字，第一人称，概括核心内容)",\n'
                '  "emotion": "neutral|happy|sad|angry|fear|surprise"\n'
                '}'
            )
            print(f"\n{'='*60}")
            print(f"[CardManager] LLM 提示词 (卡片生成):")
            print(f"  user_text[:100]: {clean_user[:100]}")
            print(f"  prompt:\n{prompt}")
            print(f"{'='*60}\n")
            result = self._llm_api.ask(prompt)
            if not result or result.isspace():
                return

            card_data = self._parse_card_json(result)
            if not card_data:
                return

            tags = card_data.get("tags", [])
            content = card_data.get("content", "")
            emotion = card_data.get("emotion", "neutral")
            topic = card_data.get("topic", "")

            emotion_eng = self._emotion_engine.get_emotion_dict() if self._emotion_engine else {}
            importance = score_importance(
                tags=tags,
                emotion_strength=emotion_eng.get("strength", 0),
                content_len=len(content),
            )

            # 质量门：低质量卡片不落盘
            if importance < 0.4:
                print(f"[Memory] 卡片质量不足，跳过: importance={importance:.2f}")
                return
            if len(content) < 15:
                print(f"[Memory] 内容过短，跳过: len={len(content)}")
                return
            if len(tags) < 2:
                print(f"[Memory] 标签过少，跳过: tags={tags}")
                return

            # 自动批准 / 待审核分支
            suggestion_mode = getattr(config, 'CARD_SUGGESTION_MODE', False)
            auto_threshold = getattr(config, 'CARD_AUTO_APPROVE_THRESHOLD', 0.6)
            if suggestion_mode:
                status = "pending"
            else:
                status = "approved" if importance >= auto_threshold else "pending"
            now = datetime.now().isoformat()

            card = Card(
                id=generate_card_id(),
                type="dialogue",
                timestamp=now,
                topic=topic,
                tags=tags,
                content=content,
                detail=f"用户: {clean_user[:500]}\nyume: {clean_ai[:500]}",
                importance=importance,
                emotion=emotion,
                tier=0,
                status=status,
                reviewed_by="auto",
                created_at=now,
            )

            card_id = self._card_store.append_card(card)
            if status == "pending":
                print(f"[Memory] 卡片待审核: {card_id} topic={topic} importance={importance:.2f}")
            else:
                print(f"[Memory] 卡片已创建: {card_id} topic={topic} importance={importance:.2f}")

        except Exception as e:
            print(f"[Memory] 卡片创建失败: {e}")

    def _parse_card_json(self, raw: str) -> Optional[dict]:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        m = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        return None

    # ── 异步记忆写入 ──

    def start_async_memory_write(self, user_text: str, ai_reply_text: str):
        def task():
            try:
                self._sync_memory_write(user_text, ai_reply_text)
            except Exception as e:
                print(f"[Memory] 异步记忆写入失败: {e}")
        t = threading.Thread(target=task, daemon=False)
        t.start()
        self._write_threads.append(t)

    def _sync_memory_write(self, user_text: str, ai_reply_text: str):
        try:
            if self._diary_writer:
                self._diary_writer.append_diary_draft(f"用户：{user_text[:200]}")
                self._diary_writer.append_diary_draft(f"我：{ai_reply_text[:200]}")

            if self._short_term:
                self._short_term._pending_card_data = (user_text, ai_reply_text)

            real_emotion = self._emotion_engine.get_emotion_dict() if self._emotion_engine else {}
            tag_result = {
                "emotion_type": real_emotion.get("type", 0),
                "emotion_strength": real_emotion.get("strength", 1),
                "scene_type": real_emotion.get("scene", "A")
            }

            if self._short_term:
                self._short_term.add_short_term("user", user_text)
                self._short_term.add_short_term("assistant", ai_reply_text)

            print(f"[Memory] 记忆写入完成 (情绪: {tag_result['emotion_type']})")

            if tag_result["emotion_strength"] >= 5 and self._context_builder:
                diary_snippets = self._context_builder.search_diary(user_text[:50], limit=2)
                if diary_snippets:
                    self._context_builder._pending_recalls = [diary_snippets]
                    print(f"[深度回忆] 捕获日记片段，留待下轮注入")

        except Exception as e:
            print(f"[Memory] 记忆写入失败: {e}")

    @property
    def last_emotion_tag(self):
        return getattr(self._short_term, 'last_emotion_tag', None)
