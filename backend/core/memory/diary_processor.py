"""
日记处理器：多LLM实例协作，将原始对话记录转化为结构化日记。

流程：
  1. LLM #1 (filter) — 过滤废话，浓缩有价值对话
  2. LLM #2 (summary) — 基于浓缩对话生成摘要
  3. 组装结构化日记，写入 daily/YYYY-MM-DD.md

LLM 实例在方法内创建，完成后自动销毁（Python GC）。
整个处理在后台线程中运行，不阻塞主对话流。
"""
import logging
import threading
from pathlib import Path

import config
from core.llm.llm_api import LLMAPI

_DIARY_LLM_TIMEOUT = 120  # 日记处理 LLM 超时（秒），比默认 30s 长

logger = logging.getLogger(__name__)

_SPLIT_MARKER = "\n\n---\n\n## 浓缩对话\n\n"


def _load_prompt(name: str) -> str:
    prompt_path = Path(__file__).parent.parent.parent / "agent_memory" / "prompts" / name
    if prompt_path.exists():
        try:
            return prompt_path.read_text(encoding="utf-8")
        except Exception:
            pass
    return ""


class DiaryProcessor:
    """日记处理器：每次处理创建独立 LLM 实例，完成后自动销毁"""

    def __init__(self, memory_root: Path):
        self._memory_root = memory_root

    # ── 公开接口 ──

    def process_daily_diary_async(self, date_str: str) -> None:
        """启动后台线程处理日记（fire-and-forget）"""
        thread = threading.Thread(
            target=self._process_sync,
            args=(date_str,),
            daemon=False,
            name=f"diary-process-{date_str}",
        )
        thread.start()
        logger.info("[DiaryProcessor] 启动后台处理: %s", date_str)

    def process_daily_diary_sync(self, date_str: str) -> bool:
        """同步处理日记，等待完成，返回是否成功"""
        return self._process_sync(date_str)

    # ── 内部实现 ──

    def _process_sync(self, date_str: str) -> bool:
        """同步处理入口（运行在后台线程中）。返回 True 表示成功生成了日记。"""
        try:
            raw_file = self._memory_root / "diary" / "daily" / f"{date_str}.md"
            if not raw_file.exists():
                logger.warning("[DiaryProcessor] 文件不存在: %s", raw_file)
                return False

            raw_text = raw_file.read_text(encoding="utf-8")
            if not raw_text.strip():
                return False

            logger.info("[DiaryProcessor] 开始处理 %s (%d 字符)", date_str, len(raw_text))

            # ── LLM #1: 过滤浓缩对话 ──
            llm_filter = LLMAPI(
                api_key=config.DEEPSEEK_API_KEY,
                base_url=config.DEEPSEEK_BASE_URL,
                model=config.DEEPSEEK_MODEL,
                timeout=_DIARY_LLM_TIMEOUT,
            )
            condensed = self._filter_dialogue(llm_filter, raw_text, date_str)
            del llm_filter  # 实例销毁

            if not condensed or condensed == raw_text:
                logger.warning("[DiaryProcessor] %s 过滤未产生变化，跳过摘要生成", date_str)
                return False

            # ── LLM #2: 生成摘要 ──
            llm_summary = LLMAPI(
                api_key=config.DEEPSEEK_API_KEY,
                base_url=config.DEEPSEEK_BASE_URL,
                model=config.DEEPSEEK_MODEL,
                timeout=_DIARY_LLM_TIMEOUT,
            )
            summary = self._generate_summary(llm_summary, condensed, date_str)
            del llm_summary  # 实例销毁

            if not summary:
                logger.warning("[DiaryProcessor] %s 摘要生成为空", date_str)
                return False

            # ── 组装并写入 ──
            structured = self._assemble(summary, condensed)
            final_size = len(structured)
            raw_file.write_text(structured, encoding="utf-8")

            logger.info(
                "[DiaryProcessor] %s 处理完成: %d → %d 字符 (压缩率 %.0f%%)",
                date_str, len(raw_text), final_size,
                (1 - final_size / max(len(raw_text), 1)) * 100,
            )
            return True

        except Exception as e:
            logger.error("[DiaryProcessor] %s 处理失败: %s", date_str, e)
            return False

    def _filter_dialogue(self, llm: LLMAPI, raw_text: str, date_str: str) -> str:
        """LLM #1: 过滤浓缩对话"""
        template = _load_prompt("diary_filter.md")
        if not template:
            return raw_text

        system_prompt = template.replace("{raw_dialogue}", raw_text)

        try:
            response = llm.chat(
                messages=[
                    {"role": "system", "content": "你是日记整理助手，只输出过滤后的对话文本。"},
                    {"role": "user", "content": system_prompt},
                ],
                temperature=0.3,
            )
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content and len(content.strip()) >= 20:
                return content.strip()
        except Exception as e:
            logger.error("[DiaryProcessor] LLM过滤失败: %s", e)

        return raw_text

    def _generate_summary(self, llm: LLMAPI, condensed: str, date_str: str) -> str:
        """LLM #2: 生成日记摘要"""
        template = _load_prompt("diary_summary.md")
        if not template:
            return ""

        system_prompt = template.replace("{condensed_dialogue}", condensed).replace("{date}", date_str)

        try:
            response = llm.chat(
                messages=[
                    {"role": "system", "content": "你是日记摘要助手，只输出日记摘要。"},
                    {"role": "user", "content": system_prompt},
                ],
                temperature=0.5,
            )
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content and len(content.strip()) >= 20:
                return content.strip()
        except Exception as e:
            logger.error("[DiaryProcessor] LLM摘要失败: %s", e)

        return ""

    def _assemble(self, summary: str, condensed: str) -> str:
        """组装结构化日记：上半部摘要 + 分割线 + 下半部浓缩对话"""
        # 去掉摘要中可能包含的 markdown 代码块标记
        summary = summary.strip()
        if summary.startswith("```"):
            lines = summary.split("\n")
            summary = "\n".join(lines[1:]) if len(lines) > 1 else summary
        if summary.endswith("```"):
            summary = summary[: summary.rfind("```")].strip()

        return summary + _SPLIT_MARKER + condensed
