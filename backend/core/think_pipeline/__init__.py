"""
think_pipeline: ReAct 循环架构（v2）

Setup → [LLM ↔ Tool Exec] × N → Finalize
"""

from backend.core.think_pipeline.context import ThinkContext
from backend.core.think_pipeline.pipeline import (
    ThinkPipeline,
    PipelineStage,
    ResponseDispatcher,
)
from backend.core.think_pipeline.dispatchers import DefaultResponseDispatcher
from backend.core.think_pipeline.memory_retrieve import MemoryRetrieveStage
from backend.core.think_pipeline.prompt_build import PromptBuildStage
from backend.core.think_pipeline.llm_chat_stage import LLMChatStage
from backend.core.think_pipeline.tool_exec_stage import ToolExecStage
from backend.core.think_pipeline.finalize import FinalizeStage
from backend.core.think_pipeline.observation_compress import ObservationCompressor
from backend.core.think_pipeline.skill_match_stage import SkillMatchStage

# 旧版兼容（仍被部分代码引用）
from backend.core.think_pipeline.llm_stream import LLMStreamStage
from backend.core.think_pipeline.recall_detect import RecallDetectStage, QueryExecutor

__all__ = [
    "ThinkContext",
    "ThinkPipeline",
    "PipelineStage",
    "ResponseDispatcher",
    "DefaultResponseDispatcher",
    "MemoryRetrieveStage",
    "SkillMatchStage",
    "PromptBuildStage",
    "LLMChatStage",
    "ToolExecStage",
    "FinalizeStage",
    "ObservationCompressor",
    # 旧版兼容
    "LLMStreamStage",
    "RecallDetectStage",
    "QueryExecutor",
]
