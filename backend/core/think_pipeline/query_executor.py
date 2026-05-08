"""
查询子 LLM 执行器 — 独立线程中运行查询 LLM，返回摘要。

从 actions.py 中提取，供 ThinkOrchestrator 和 RecallDetectStage 共享。
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from backend.core.llm.llm_api import LLMAPI
from backend.core.llm.llm_factory import LLMFactory

logger = logging.getLogger(__name__)


def _build_file_index() -> str:
    """扫描 agent_memory 目录，返回供查询 LLM 参考的文件索引"""
    agent_dir = Path(__file__).parent.parent.parent / "agent_memory"
    lines = []

    # ── 日记文件 ──
    diary_dir = agent_dir / "diary" / "daily"
    diary_files = sorted(diary_dir.glob("*.md"), reverse=True) if diary_dir.exists() else []
    if diary_files:
        lines.append("## 日记文件 (diary/daily/)")
        for f in diary_files[:14]:  # 最近两周
            lines.append(f"  - {f.name}")
        if len(diary_files) > 14:
            lines.append(f"  ... 共 {len(diary_files)} 篇日记")

    # ── 记忆卡片索引 ──
    index_path = agent_dir / "cards" / "index.json"
    if index_path.exists():
        try:
            index_data = json.loads(index_path.read_text(encoding="utf-8"))
            meta = index_data.get("meta", {})
            categories = index_data.get("categories", {})
            lines.append(f"\n## 记忆卡片索引 (cards/)")
            lines.append(f"  总卡片: {meta.get('total_cards', '?')} 条, "
                         f"总标签: {meta.get('total_tags', '?')} 个")
            if categories:
                lines.append("  分类:")
                for cat_name, cat_info in list(categories.items())[:8]:
                    card_n = cat_info.get("card_count", 0)
                    tags_sample = cat_info.get("tags", [])[:5]
                    tags_preview = ", ".join(tags_sample)
                    lines.append(f"    ▸ {cat_name} ({card_n}条卡片) tags: {tags_preview}...")
        except (json.JSONDecodeError, IOError):
            pass

    # ── 用户信息 ──
    user_path = agent_dir / "user" / "user_info.json"
    if user_path.exists():
        lines.append(f"\n## 用户信息 (user/user_info.json) — 可用")

    # ── 对话记忆库 ──
    core_dir = agent_dir / "core"
    personality = core_dir / "personality.md"
    mood_blank = core_dir / "mood_blank.md"
    if personality.exists() or mood_blank.exists():
        lines.append("\n## 核心配置 (core/)")
        if personality.exists():
            lines.append("  - personality.md (人设)")
        if mood_blank.exists():
            lines.append("  - mood_blank.md (情绪空白模板)")

    return "\n".join(lines) if lines else "（记忆目录暂无可读取文件）"


def _load_prompt(name: str) -> str:
    """加载提示词文件"""
    prompt_path = Path(__file__).parent.parent.parent / "agent_memory" / "prompts" / name
    if prompt_path.exists():
        try:
            return prompt_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning(f"加载提示词 {name} 失败: {e}")
    return ""


def execute_single_tool(registry, tool_name: str, params: dict, llm) -> str:
    """执行单个工具，返回结果字符串"""
    try:
        if not registry:
            return "工具注册中心不可用"
        tool = registry.get_tool(tool_name)
        if not tool:
            return f"工具未注册: {tool_name}"
        filtered_params = {k: v for k, v in params.items() if v}
        all_params = {**filtered_params, "llm": llm}
        result = registry.execute_tool(tool_name, **all_params)
        return str(result)[:500]
    except Exception as e:
        return f"工具执行失败: {e}"


def run_memory_query(
    query_goal: str,
    registry,
    query_llm: Optional[LLMAPI] = None,
    max_steps: int = 3,
) -> str:
    """在独立线程中运行查询子 LLM"""
    if query_llm is None:
        query_llm = LLMFactory.get_default()
    try:
        tools_schemas = registry.get_legacy_schema() if registry else []
        tools_json = json.dumps(tools_schemas, ensure_ascii=False, indent=2)

        file_index = _build_file_index()

        query_prompt_template = _load_prompt("query_system.md")
        if not query_prompt_template:
            query_prompt_template = """你是记忆检索助手。
可用工具：{tools_json}
查询目标：{query_goal}
文件索引：{file_index}
规则：检索相关记忆，返回 JSON 摘要。最多 3 次工具调用。"""

        system_prompt = query_prompt_template.format(
            tools_json=tools_json, query_goal=query_goal,
            file_index=file_index, experience=""
        )

        messages = [{"role": "system", "content": system_prompt}]

        for step in range(max_steps):
            response = query_llm.chat(messages, temperature=0.2)

            if "error" in response:
                logger.error(f"[查询子LLM] API 错误: {response['error']}")
                break

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                break

            try:
                decision = json.loads(content.strip())
            except json.JSONDecodeError:
                logger.info(f"[查询子LLM] 第{step+1}步返回非JSON，视为最终摘要")
                return content.strip()

            if decision.get("found") is not None:
                summary = decision.get("summary", "")
                detail = decision.get("detail", "")
                return f"{summary}\n{detail}" if detail else summary

            tools_to_call = decision.get("tools", [])
            tool_name = decision.get("tool_name", "")
            params = decision.get("params", {})

            if tools_to_call:
                tool_results = []
                for tool_info in tools_to_call:
                    t_name = tool_info.get("tool_name", "")
                    t_params = tool_info.get("params", {})
                    if t_name:
                        result = execute_single_tool(registry, t_name, t_params, query_llm)
                        tool_results.append(f"[{t_name}] {result}")
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": "工具结果：\n" + "\n".join(tool_results)})
            elif tool_name:
                result = execute_single_tool(registry, tool_name, params, query_llm)
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": f"工具 [{tool_name}] 结果：{result}"})
            else:
                return content.strip()

        messages.append({"role": "user", "content": "请基于以上检索结果，给出最终摘要。"})
        try:
            final = query_llm.chat(messages, temperature=0.2)
            fc = final.get("choices", [{}])[0].get("message", {}).get("content", "")
            return fc.strip() if fc else "检索完成，但未能生成摘要"
        except Exception:
            return "检索完成，但摘要生成失败"

    except Exception as e:
        logger.error(f"[查询子LLM] 执行异常: {e}")
        return f"记忆查询失败: {e}"
