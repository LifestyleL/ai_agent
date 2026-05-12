"""
上下文压缩器 — 监控 ShortTermMemory 填充率，用 LLM 将旧消息压缩为摘要。

增量压缩：每次把上一轮摘要 + 新消息一起传给 LLM，LLM 审查并决定保留/合并/丢弃。
压缩结果同时写入 agent_memory/core/compressed_memory.jsonl，为做梦/深度记忆/学习能力做铺垫。
"""
import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from core.llm.llm_api import LLMAPI
import config

logger = logging.getLogger(__name__)


@dataclass
class CompressedHistory:
    summary: str = ""
    verbatim_keep: List[str] = field(default_factory=list)
    last_compressed_index: int = -1
    compressed_at: str = ""


COMPRESSION_PROMPT = """你是对话压缩助手，帮 yume 整理记忆。

{yume}是 yume（一个有猫耳的 AI），{user}是和她对话的人。

我会给你两部分内容：
1. 之前的记忆摘要（可能为空）
2. 新发生的对话（需要压缩的消息）

请审查新旧内容，输出一份合并后的摘要。用 JSON 输出：

{
  "summary": "合并后的对话摘要：关键话题、用户偏好、决定、情绪变化（300-500字，用第一人称'我'写）",
  "verbatim_keep": ["需要逐字保留的关键句子"],
  "discard": "简述丢弃了什么及原因（≤30字）"
}

压缩规则：
- 如果之前的摘要里还有相关信息，合并进新摘要，不要丢失
- 如果之前摘要的内容已经被新对话覆盖/纠正了，用新内容替换旧内容
- 闲聊寒暄合并为主题+情感倾向，不要逐条记录
- 用户说过"记住"的内容、重要决定、偏好信息 → 保留
- 重复的纠正只保留最终版本
- 丢弃：纯语气词（嗯、哦）、重复寒暄、已过时的纠正"""


class ContextCompressor:
    """增量上下文压缩器：旧摘要 + 新消息 → LLM 审查 → 合并摘要 → 写入压缩记忆文件"""

    def __init__(self, llm_api=None):
        self._llm = llm_api
        self._memory_root = Path(__file__).parent.parent.parent / "agent_memory"

    def _get_compressed_memory_path(self) -> Path:
        """压缩记忆归档文件路径"""
        core_dir = self._memory_root / "core"
        core_dir.mkdir(parents=True, exist_ok=True)
        return core_dir / "compressed_memory.jsonl"

    def _get_llm(self) -> LLMAPI:
        if self._llm:
            return self._llm
        from core.llm.llm_factory import LLMFactory
        return LLMFactory.get_default()

    def needs_compression(self, short_term_memory) -> bool:
        """检查是否需要压缩：条目数超过阈值"""
        base_cap = getattr(config, 'SHORT_TERM_CAPACITY_BASE', 15)
        threshold = max(10, int(base_cap * 0.8))
        count = len(short_term_memory.short_term_history)
        if count < threshold:
            return False
        # 如果已有压缩，检查新增条目是否够多
        if short_term_memory._compressed and short_term_memory._compressed.last_compressed_index >= 0:
            new_since = count - short_term_memory._compressed.last_compressed_index - 1
            return new_since >= 5  # 至少 5 条新消息再压缩
        return True

    def compress(self, short_term_memory) -> None:
        """后台线程：压缩旧消息，保留最近 8 条"""
        try:
            history = short_term_memory.short_term_history
            if len(history) < 10:
                return

            max_recent = getattr(config, 'COMPRESSION_MAX_RECENT_KEEP', 8)
            split_idx = max(0, len(history) - max_recent)

            # 待压缩的旧消息
            old_entries = history[:split_idx]
            if not old_entries:
                return

            # 上一次的压缩摘要
            prev_summary = ""
            if short_term_memory._compressed and short_term_memory._compressed.summary:
                prev_summary = short_term_memory._compressed.summary

            # 格式化旧消息
            formatted = []
            for d in old_entries:
                r = d.get("role", "")
                content = d.get("content", "")
                if r == "user":
                    label = "他"
                elif r == "system":
                    label = "画面"
                else:
                    label = "我"
                formatted.append(f"{label}: {content}")
            new_dialogue = "\n".join(formatted)

            prompt = COMPRESSION_PROMPT.replace("{yume}", "我").replace("{user}", "他")

            full_prompt = f"""{prompt}

【之前的记忆摘要】
{prev_summary if prev_summary else "（无，这是第一次压缩）"}

【新发生的对话】
{new_dialogue}

请输出合并后的 JSON："""

            llm = self._get_llm()
            response = llm.chat(
                [{"role": "user", "content": full_prompt}],
                temperature=0.2
            )

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                logger.warning("[ContextCompressor] LLM 返回空内容")
                return

            # 解析 JSON
            content = content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:]) if len(lines) > 1 else content
                if content.endswith("```"):
                    content = content[:-3]

            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                logger.warning(f"[ContextCompressor] JSON 解析失败: {content[:100]}")
                return

            summary = data.get("summary", "").strip()
            verbatim = data.get("verbatim_keep", [])
            discard = data.get("discard", "")

            if not summary:
                return

            compressed_at = datetime.now().isoformat()
            short_term_memory._compressed = CompressedHistory(
                summary=summary,
                verbatim_keep=verbatim if isinstance(verbatim, list) else [],
                last_compressed_index=split_idx - 1,
                compressed_at=compressed_at
            )

            # ── 写入压缩记忆归档文件（为做梦/深度记忆/学习做铺垫） ──
            self._append_compressed_memory(summary, verbatim, compressed_at)

            # 裁剪缓冲区：只保留压缩索引之后的条目
            # 但等 add_short_term 的下次调用再做，避免线程安全问题
            logger.info(f"[ContextCompressor] 压缩完成: 摘要 {len(summary)} 字, "
                        f"保留 {len(verbatim) if isinstance(verbatim, list) else 0} 条关键句, "
                        f"丢弃原因: {discard[:30]}")

        except Exception as e:
            logger.error(f"[ContextCompressor] 压缩失败: {e}")

    def _append_compressed_memory(self, summary: str, verbatim: list, compressed_at: str):
        """将压缩摘要追加写入 compressed_memory.jsonl"""
        try:
            fpath = self._get_compressed_memory_path()
            entry = {
                "compressed_at": compressed_at,
                "summary": summary,
                "verbatim_keep": verbatim if isinstance(verbatim, list) else [],
                "char_count": len(summary)
            }
            with open(fpath, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[ContextCompressor] 写入压缩记忆文件失败: {e}")
