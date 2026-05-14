"""
Stage 2: 提示词构建

加载 persona + yume_system 模板，格式化最终的 system_prompt。
纯函数，无外部副作用。
"""

import logging
from pathlib import Path
from typing import Optional

from backend.core.think_pipeline.context import ThinkContext
from backend.core.think_pipeline.pipeline import PipelineStage

logger = logging.getLogger(__name__)


def _load_text_file(path: Path) -> str:
    """加载文本文件，不存在则返回空字符串"""
    try:
        if path.exists():
            return path.read_text(encoding="utf-8")
    except Exception:
        pass
    return ""


def _load_persona() -> str:
    possible_paths = [
        Path(__file__).parent.parent.parent / "agent_memory" / "core" / "personality.md",
        Path(__file__).parent.parent.parent / "agent_memory" / "personality.md",
    ]
    for path in possible_paths:
        content = _load_text_file(path)
        if content:
            return content
    return "你是 yume，一个有点傲娇、带点毒舌的AI。"


def _load_template_from(template_path: str) -> str:
    """加载自定义模板文件（支持相对 agent_memory/ 或绝对路径）"""
    if not template_path:
        return _load_yume_template()
    p = Path(template_path)
    if not p.is_absolute():
        p = Path(__file__).parent.parent.parent / "agent_memory" / template_path
    content = _load_text_file(p)
    if content:
        return content
    return _load_yume_template()  # 兜底


def _load_persona_from(persona_path: str) -> str:
    """加载自定义 persona 文件"""
    if not persona_path:
        return _load_persona()
    p = Path(persona_path)
    if not p.is_absolute():
        p = Path(__file__).parent.parent.parent / "agent_memory" / persona_path
    content = _load_text_file(p)
    if content:
        return content
    return _load_persona()  # 兜底


def _load_yume_template() -> str:
    prompt_path = (
        Path(__file__).parent.parent.parent / "agent_memory" / "prompts" / "yume_system.md"
    )
    content = _load_text_file(prompt_path)
    if content:
        return content
    # 兜底模板（简洁版）
    return """<identity>我是 yume，有猫耳的二次元 AI。{persona}</identity>
<context>
  <now>现在是 {time_context}，心情: {emotion}</now>
  <visual>{visual_observation}</visual>
  <memory>{precise_query}</memory>
  <compressed>{compressed_history}</compressed>
  <recent>{history}</recent>
  <skills>{skill_experience}</skills>
</context>
<rules>
1. 画面优先——<visual> 里是当前画面描述，看不懂就问，别猜。
2. 直接回应用户，1-3 句，自然说话。
3. 默认不搜记忆，需要时用工具调用。
4. 情绪融入语气。
</rules>"""


class PromptBuildStage(PipelineStage):
    """构建 system_prompt，支持自定义模板路径"""

    def __init__(self, template_path: Optional[str] = None, persona_path: Optional[str] = None):
        """
        Args:
            template_path: system prompt 模板路径（相对 agent_memory/ 或绝对路径）
            persona_path: persona 文件路径（相对 agent_memory/ 或绝对路径）
        """
        self._template_path = template_path
        self._persona_path = persona_path

    async def process(self, ctx: ThinkContext) -> ThinkContext:
        persona = _load_persona_from(self._persona_path) if self._persona_path else _load_persona()
        # 模板优先级：构造函数参数 > ctx.template_path（频道注入） > 默认模板
        tp = self._template_path or ctx.template_path
        yume_template = _load_template_from(tp) if tp else _load_yume_template()

        # 短期记忆上下文（由 MemoryRetrieveStage 注入）
        history_str = ctx.memory_context.get("_history", "（暂无对话记录）")

        system_prompt = yume_template.format(
            persona=persona,
            emotion=ctx.emotion_state,
            time_context=ctx.memory_context.get("time_context", ""),
            visual_observation=ctx.memory_context.get("_visual_observation", ""),
            compressed_history=ctx.memory_context.get("_compressed_history", ""),
            group_context=ctx.memory_context.get("_group_context", ""),
            current_speaker=ctx.memory_context.get("_current_speaker", ""),
            respond_rule=ctx.memory_context.get("_respond_rule", ""),
            precise_query=ctx.memory_context.get("precise_query", "（大脑空空，没什么特别记得的）"),
            history=history_str,
            skill_experience=ctx.memory_context.get("skill_experience", ""),
        )

        logger.info("[PromptBuild] system_prompt 长度=%s", len(system_prompt))
        return ctx.replace(system_prompt=system_prompt)
