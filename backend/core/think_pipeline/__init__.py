"""
think_pipeline: action_think 的 Pipeline 替代品

将原 228 行 God Function 拆分为 5 个独立 Stage，每个可独立测试。
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
from backend.core.think_pipeline.llm_stream import LLMStreamStage
from backend.core.think_pipeline.recall_detect import RecallDetectStage, QueryExecutor
from backend.core.think_pipeline.finalize import FinalizeStage
from backend.core.think_pipeline.skill_match_stage import (
    SkillMatchStage, SkillMatcher, SkillInfo, build_default_matcher,
)

__all__ = [
    "ThinkContext",
    "ThinkPipeline",
    "PipelineStage",
    "ResponseDispatcher",
    "DefaultResponseDispatcher",
    "MemoryRetrieveStage",
    "SkillMatchStage",
    "SkillMatcher",
    "SkillInfo",
    "build_default_matcher",
    "PromptBuildStage",
    "LLMStreamStage",
    "RecallDetectStage",
    "QueryExecutor",
    "FinalizeStage",
]
