"""
Phase 2 验证：ReAct 循环原型

测试闭环：用户提问 → Pipeline(Setup → [LLM ↔ Tool]×N → Finalize) → 最终回复

4 个场景：
  1. 单工具 → 回复
  2. 多工具链（search → read → 回复）
  3. 工具调用 + 无关问题（上下文保持）
  4. max_rounds 达到上限 → 兜底回复

用法:
  cd backend
  python tests/manual/test_react_loop.py              # mock LLM（快速验证）
  python tests/manual/test_react_loop.py --live        # 真实 LLM
"""

import asyncio
import json
import sys
import os

_project_root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _project_root)
sys.path.insert(0, _backend_dir)

from backend.plugins.base_tool import BaseTool
from backend.plugins.registry import ToolRegistry
from backend.core.think_pipeline.context import ThinkContext
from backend.core.think_pipeline.pipeline import ThinkPipeline
from backend.core.think_pipeline.llm_chat_stage import LLMChatStage
from backend.core.think_pipeline.tool_exec_stage import ToolExecStage


# ═══════════════════════════════════════════════════════════════
# 测试工具
# ═══════════════════════════════════════════════════════════════

class SearchMemoryTool(BaseTool):
    name = "search_memory"
    description = "搜索 AI 的长期记忆，查找与关键词相关的历史对话"
    inputSchema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "limit": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    }

    def execute(self, **kwargs) -> dict:
        query = kwargs.get("query", "")
        return {"data": f"[记忆] 关于「{query}」: 上周三用户聊了 AI 架构重构，讨论了 MCP 协议和 ReAct 模式。"}


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "读取指定文件内容"
    inputSchema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
        },
        "required": ["path"],
    }

    def execute(self, **kwargs) -> dict:
        path = kwargs.get("path", "")
        return {"data": f"[文件] {path} 内容: 「用户备忘录：周五前完成架构文档。」"}


# ═══════════════════════════════════════════════════════════════
# Mock LLM（不依赖 API Key）
# ═══════════════════════════════════════════════════════════════

class MockLLM:
    """按场景返回预设响应，模拟 DeepSeek function calling"""

    def __init__(self, scenario: str):
        self.scenario = scenario
        self.call_count = 0
        self.model = "mock"
        self.base_url = "mock://test"

    async def chat_async(self, messages, temperature=0.7, tools=None):
        self.call_count += 1
        call = self.call_count
        scenario = self.scenario

        # 检查最后一条用户消息是否是兜底提示
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = str(m.get("content", ""))
                break

        if "用完了所有工具调用轮次" in last_user:
            return self._text_response("抱歉，我尽力查了但信息不够完整。根据已有的记忆片段，上周三我们主要讨论了架构相关的内容。")

        if scenario == "single_tool":
            if call == 1:
                return self._tool_response("search_memory", {"query": "上周三聊了什么"})
            else:
                return self._text_response("根据记忆，上周三我们讨论了 AI 架构重构，聊到了 MCP 协议和 ReAct 模式！")

        elif scenario == "multi_tool":
            if call == 1:
                return self._tool_response("search_memory", {"query": "用户备忘录"})
            elif call == 2:
                return self._tool_response("read_file", {"path": "/memo/architecture.md"})
            else:
                return self._text_response("查到了！你的备忘录里写着周五前要完成架构文档。记忆中也找到了相关讨论。")

        elif scenario == "no_tool":
            if call == 1:
                return self._text_response("你好呀！今天心情怎么样~")

        elif scenario == "max_rounds":
            return self._tool_response("search_memory", {"query": f"查询{call}"})

        elif scenario == "error_tool":
            if call == 1:
                return self._tool_response("nonexistent_tool", {"arg": "test"})
            elif call == 2:
                return self._text_response("抱歉，没有找到可用的工具来处理你的请求。")

        return self._text_response("fallback 回复")

    def _text_response(self, content: str) -> dict:
        return {
            "choices": [{
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }]
        }

    def _tool_response(self, name: str, args: dict) -> dict:
        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": f"call_{self.call_count}",
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(args, ensure_ascii=False),
                        },
                    }],
                },
                "finish_reason": "tool_calls",
            }]
        }

    async def ask_with_system_async(self, system_prompt: str, user_input: str, temperature=0.7):
        return "mock response"


# ═══════════════════════════════════════════════════════════════
# 测试运行器
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是 yume，一个 AI 助手。你可以使用工具来搜索记忆和读取文件。

重要规则：
1. 涉及过去的事 → search_memory
2. 需要查看文件 → read_file
3. 简单问候直接回复
4. 工具结果出来后基于结果回答
5. 如果没有合适的工具，诚实告诉用户"""


class NoopFinalizeStage:
    """不依赖记忆系统的空收尾阶段"""
    async def process(self, ctx: ThinkContext) -> ThinkContext:
        return ctx


async def run_scenario(scenario: str, label: str, max_rounds: int = 5) -> bool:
    """运行单个 ReAct 场景，返回是否通过"""
    print(f"\n{'─' * 60}")
    print(f"[{label}]")

    llm = MockLLM(scenario)
    registry = ToolRegistry()
    registry.register(SearchMemoryTool())
    registry.register(ReadFileTool())

    pipeline = ThinkPipeline(
        setup_stages=[],
        llm_stage=LLMChatStage(llm=llm, registry=registry),
        tool_stage=ToolExecStage(registry=registry),
        finalize_stage=NoopFinalizeStage(),
    )

    ctx = ThinkContext(
        user_input="上周三我们聊了什么？",
        system_prompt=SYSTEM_PROMPT,
        max_react_rounds=max_rounds,
    )
    ctx = pipeline._build_initial_messages(ctx)

    try:
        ctx = await pipeline.execute(ctx)
    except Exception as e:
        print(f"  X 异常: {e}")
        return False

    print(f"  轮次: {ctx.react_round}/{ctx.max_react_rounds}")
    print(f"  回复: {ctx.response_text[:120]}")
    print(f"  错误: {ctx.error}")

    # 验证
    if scenario == "single_tool":
        ok = ctx.react_round >= 1 and len(ctx.response_text) > 0 and not ctx.error
    elif scenario == "multi_tool":
        ok = ctx.react_round >= 2 and len(ctx.response_text) > 0 and not ctx.error
    elif scenario == "no_tool":
        ok = ctx.react_round == 0 and len(ctx.response_text) > 0 and not ctx.error
    elif scenario == "max_rounds":
        ok = ctx.react_round >= max_rounds - 1 and not ctx.error
    elif scenario == "error_tool":
        ok = len(ctx.response_text) > 0 and not ctx.error  # LLM 应自修复
    else:
        ok = not ctx.error

    print(f"  {'[PASS] 通过' if ok else 'X 失败'}")
    return ok


async def run_live_scenario(llm, registry, user_input: str, label: str) -> bool:
    """使用真实 LLM 运行场景"""
    print(f"\n{'─' * 60}")
    print(f"[{label}] 用户: {user_input}")

    pipeline = ThinkPipeline(
        setup_stages=[],
        llm_stage=LLMChatStage(llm=llm, registry=registry),
        tool_stage=ToolExecStage(registry=registry),
        finalize_stage=NoopFinalizeStage(),
    )

    ctx = ThinkContext(
        user_input=user_input,
        system_prompt=SYSTEM_PROMPT,
        max_react_rounds=5,
    )
    ctx = pipeline._build_initial_messages(ctx)

    try:
        ctx = await pipeline.execute(ctx)
    except Exception as e:
        print(f"  X 异常: {e}")
        return False

    print(f"  轮次: {ctx.react_round}")
    print(f"  回复: {ctx.response_text[:200]}")
    print(f"  错误: {ctx.error}")
    ok = not ctx.error and len(ctx.response_text) > 0
    print(f"  {'[PASS] 通过' if ok else 'X 失败'}")
    return ok


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

async def main():
    use_live = "--live" in sys.argv

    print("╔══════════════════════════════════════════════╗")
    print("║  Phase 2: ReAct 循环原型验证                  ║")
    print(f"║  模式: {'真实 LLM' if use_live else 'Mock LLM'}                             ║")
    print("╚══════════════════════════════════════════════╝")

    if use_live:
        try:
            from backend.config import validate_config
            validate_config()
        except Exception:
            pass
        try:
            from backend.core.llm.llm_factory import LLMFactory
            llm = LLMFactory.get_default()
            print(f"[OK] LLM 就绪: {llm.model} @ {llm.base_url}")
        except Exception as e:
            print(f"[SKIP] LLM 初始化失败: {e}")
            return

        registry = ToolRegistry()
        registry.register(SearchMemoryTool())
        registry.register(ReadFileTool())

        results = [
            await run_live_scenario(llm, registry, "上周三我们聊了什么？", "场景1: 单工具搜索"),
            await run_live_scenario(llm, registry, "你好呀 yume~", "场景2: 不需要工具"),
            await run_live_scenario(llm, registry, "帮我查一下北京今天的天气", "场景3: 无对应工具"),
        ]
    else:
        results = [
            await run_scenario("single_tool", "场景1: 单工具 → 回复"),
            await run_scenario("multi_tool", "场景2: 多工具链 search→read→回复"),
            await run_scenario("no_tool", "场景3: 无需工具 → 直接回复"),
            await run_scenario("max_rounds", "场景4: max_rounds=2 触发兜底", max_rounds=2),
            await run_scenario("error_tool", "场景5: LLM调用不存在工具 → 自修复"),
        ]

    passed = sum(results)
    total = len(results)
    print(f"\n{'═' * 60}")
    print(f"结果: {passed}/{total} 通过")
    if passed < total:
        print("[FAIL] 部分场景失败，请检查输出")
    else:
        print("[PASS] 全部通过")


if __name__ == "__main__":
    asyncio.run(main())
