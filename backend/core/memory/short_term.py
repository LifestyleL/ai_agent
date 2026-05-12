"""
短期记忆 RAM buffer
管理最近 N 轮对话，触发卡片创建回调、上下文压缩
"""
import threading
from datetime import datetime
from typing import List, Dict, Optional
import config


class ShortTermMemory:
    def __init__(self, card_store=None):
        self.short_term_history: List[Dict[str, str]] = []
        self._pending_card_data: Optional[tuple] = None
        self._card_creator = None
        self._card_store = card_store

        # ── 上下文压缩 ──
        from core.memory.context_compressor import CompressedHistory
        self._compressed: Optional[CompressedHistory] = None
        self._compressor = None
        self._compression_lock = threading.Lock()

    def set_card_creator(self, callback):
        self._card_creator = callback

    def set_compressor(self, compressor):
        self._compressor = compressor

    def add_short_term(self, role: str, content: str) -> None:
        if self.short_term_history:
            last = self.short_term_history[-1]
            if last.get("role") == role and last.get("content") == content:
                return
        # 视觉观察去重：只保留最新一条画面描述，旧的全删
        if role == "system" and "[刚才看到的画面]" in content:
            self.short_term_history = [
                d for d in self.short_term_history
                if not (d.get("role") == "system" and "[刚才看到的画面]" in d.get("content", ""))
            ]
        self.short_term_history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        max_cap = getattr(config, 'SHORT_TERM_CAPACITY_BASE', 20)
        if len(self.short_term_history) > max_cap + 10:
            self.short_term_history = self.short_term_history[-max_cap:]

        if role == "assistant" and self._pending_card_data:
            user_text, ai_text = self._pending_card_data
            self._pending_card_data = None
            if self._card_creator:
                self._card_creator(user_text, ai_text)

        # 非阻塞触发压缩检查
        self.maybe_compress()

    def maybe_compress(self):
        """如果填充率达到阈值，启动后台线程压缩旧消息"""
        if not self._compressor:
            return
        if self._compression_lock.locked():
            return
        if not self._compressor.needs_compression(self):
            return
        t = threading.Thread(
            target=self._compressor.compress, args=(self,),
            name="ContextCompressor", daemon=True
        )
        t.start()

    def get_compressed_summary(self) -> str:
        """返回压缩摘要文本，供提示词模板 {compressed_history} 使用"""
        if self._compressed and self._compressed.summary:
            return self._compressed.summary
        return ""

    def get_context_for_prompt(self, max_recent: int = 8) -> str:
        """组装完整上下文：压缩摘要（旧消息）+ 最近未压缩条目"""
        parts = []
        if self._compressed and self._compressed.summary:
            parts.append(f"【早期对话摘要】\n{self._compressed.summary}")

        start = self._compressed.last_compressed_index + 1 if self._compressed else 0
        recent = self.short_term_history[start:][-max_recent:]
        if recent:
            formatted = []
            for d in recent:
                r = d["role"]
                if r == "user":
                    role = "用户"
                elif r == "system":
                    role = "记忆"
                else:
                    role = "yume"
                formatted.append(f"{role}: {d['content']}")
            parts.append("\n".join(formatted))

        return "\n".join(parts) if parts else ""

    def get_short_term_visual(self) -> str:
        """返回最近一条视觉观察内容（system role 的 [刚才看到的画面] 消息）"""
        for d in reversed(self.short_term_history[-10:]):
            if d.get("role") == "system" and "[刚才看到的画面]" in d.get("content", ""):
                return d["content"].replace("[刚才看到的画面] ", "").strip()
        return ""

    def get_short_term_count(self) -> int:
        return len(self.short_term_history)

    def get_short_term_context(self, max_turns: Optional[int] = None) -> str:
        if not self.short_term_history:
            return ""
        buffer = self.short_term_history
        if max_turns is not None and max_turns > 0:
            buffer = buffer[-max_turns:]
        formatted = []
        for d in buffer:
            r = d["role"]
            if r == "user":
                role = "用户"
            elif r == "system":
                role = "记忆"
            else:
                role = "yume"
            formatted.append(f"{role}: {d['content']}")
        return "\n".join(formatted)

    def flush(self) -> None:
        if self._card_store:
            self._card_store.flush()
