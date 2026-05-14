"""
Phase 1 验证：单工具 MCP 化 + LLM 感知实验

测试闭环：用户提问 → LLM 返回 tool_call → 执行工具 → 结果注入 → LLM 最终回复

3 个场景：
  1. 正确调用："上周三我们聊了什么" → search_memory → 基于记忆回复
  2. 不需要工具："你好" → LLM 直接回复
  3. 幻觉工具名："帮我查天气" → 返回 error → LLM 自修复

用法:
  cd backend
  python tests/manual/test_mcp_tool_call.py
"""

import asyncio
import json
import sys
import os
import time

# path 注入必须在 import backend.* 之前
# 需要两个路径：
#   f:/AI/ai_agent/          → from backend.plugins.xxx
#   f:/AI/ai_agent/backend/  → from config (内部模块直接 import config)
_project_root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _project_root)
sys.path.insert(0, _backend_dir)

from backend.plugins.base_tool import BaseTool
from backend.plugins.registry import ToolRegistry
from backend.plugins.tool_result import ToolResult


# ═══════════════════════════════════════════════════════════════
# search_memory 工具适配器
# ═══════════════════════════════════════════════════════════════

class SearchMemoryTool(BaseTool):
    name = "search_memory"
    description = "搜索 AI 的长期记忆，查找与关键词相关的历史对话记录。当你需要回忆过去聊过的内容时使用此工具。"
    inputSchema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词或问句，如 '源喜欢的食物' 或 '上周聊了什么'",
            },
            "limit": {
                "type": "integer",
                "description": "返回结果条数，默认 5",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    def __init__(self, context_builder=None):
        self._context_builder = context_builder

    def execute(self, **kwargs) -> dict:
        query = kwargs.get("query", "")
        limit = kwargs.get("limit", 5)

        if self._context_builder:
            raw = self._context_builder.search_memory(keyword=query, limit=limit)
            if raw and "未找到" not in raw:
                return {"data": raw, "total_count": 0, "truncated": len(raw) > 2000}
            return {"data": "", "total_count": 0, "truncated": False}

        # fallback 模拟数据（不依赖完整记忆系统）
        sample = f"[模拟记忆] 关于「{query}」: 上周三（5月7日）用户和 yume 聊了 AI 架构重构，讨论了 MCP 协议和 ReAct 模式。用户说 '要把工具系统标准化'。"
        return {"data": sample, "total_count": 1, "truncated": False}


# ═══════════════════════════════════════════════════════════════
# LLM + Tool 交互循环
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是 yume，一个 AI 助手。你有工具可以用来搜索长期记忆。

重要规则：
1. 如果用户的问题涉及过去发生的事情、历史记录、记忆，你必须使用 search_memory 工具查询。
2. 如果你不确定是否需要搜索，宁可搜索也不要猜测。
3. 工具返回结果后，基于结果自然回答用户。
4. 如果工具返回错误或空结果，诚实告诉用户。
5. 对于简单的问候、闲聊，直接回复，不需要调用工具。"""


async def run_mcp_loop(llm, registry, user_message: str, label: str):
    """执行一次完整的 MCP 交互循环"""
    print(f"\n{'─' * 60}")
    print(f"[{label}] 用户: {user_message}")
    print(f"{'─' * 60}")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    tools_def = registry.list_tools()

    # 把工具定义放进 system 消息（让模型知道有哪些工具可用）
    if tools_def:
        messages[0]["content"] += f"\n\n可用工具：\n{json.dumps(tools_def, ensure_ascii=False, indent=2)}"

    messages.append({"role": "user", "content": user_message})

    t0 = time.time()

    # 最多 3 轮（工具调用 + 可能重搜 + 最终回复）
    final_content = ""
    for step in range(3):
        response = await llm.chat_async(messages, temperature=0.3, tools=tools_def)

        if "error" in response:
            print(f"  LLM 错误: {response['error']}")
            # debug: 打印最后一条消息的类型和长度
            if messages:
                last = messages[-1]
                print(f"  [debug] last msg role={last.get('role')}, content_len={len(str(last.get('content','')))}")
            return ""

        choice = response["choices"][0]
        msg = choice.get("message", {})
        final_content = msg.get("content", "")

        # 检查是否有 tool_calls
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            for tc in tool_calls:
                func = tc.get("function", {})
                tool_name = func.get("name", "")
                try:
                    params = json.loads(func.get("arguments", "{}"))
                except json.JSONDecodeError:
                    params = {}

                print(f"  → LLM 调用工具: {tool_name}({json.dumps(params, ensure_ascii=False)[:100]})")

                result: ToolResult = registry.call_tool(tool_name, params)
                print(f"  → 工具结果: result_type={result.result_type}, success={result.success}")
                if result.data:
                    data_preview = str(result.data)[:120]
                    print(f"  → 数据预览: {data_preview}...")

                # DeepSeek thinking mode：reasoning_content 必须传回
                assistant_msg = {
                    "role": "assistant",
                    "tool_calls": [tc],
                }
                # 保留 reasoning_content（DeepSeek 思维链模式要求传回）
                if "reasoning_content" in msg:
                    assistant_msg["reasoning_content"] = msg["reasoning_content"]
                if final_content:
                    assistant_msg["content"] = final_content

                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc.get("id", "unknown"),
                    "content": result.to_message()[:2000],
                }
                messages.append(assistant_msg)
                messages.append(tool_msg)
        else:
            elapsed = time.time() - t0
            print(f"  → LLM 回复 ({elapsed:.1f}s): {final_content[:200]}")
            return final_content

    # 第 2 轮后仍未得到最终回复
    print(f"  → 最终回复: {final_content[:200]}")
    return final_content


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

async def main():
    print("╔══════════════════════════════════════════════╗")
    print("║  Phase 1: MCP 工具调用闭环验证                ║")
    print("╚══════════════════════════════════════════════╝")

    # ── 初始化 LLM ──
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
        print("请配置 DEEPSEEK_API_KEY 后重试")
        return

    # ── 初始化 ToolRegistry ──
    registry = ToolRegistry()

    # 尝试用真实记忆系统
    context_builder = None
    try:
        from backend.core.memory.memory_facade import MemoryFacade
        memory = MemoryFacade(llm_api=None)
        context_builder = memory._context_builder
        print(f"[OK] 记忆系统就绪，已加载卡片")
    except Exception as e:
        print(f"[INFO] 记忆系统不可用，使用模拟数据: {e}")

    registry.register(SearchMemoryTool(context_builder))
    print(f"[OK] 工具已注册: {[t['function']['name'] for t in registry.list_tools()]}")

    # ── 场景 1：正确调用工具 ──
    await run_mcp_loop(llm, registry,
        "上周三我们聊了什么？我不太记得了",
        "场景1: 记忆搜索")

    # ── 场景 2：不需要工具 ──
    await run_mcp_loop(llm, registry,
        "你好呀 yume~",
        "场景2: 简单问候")

    # ── 场景 3：幻觉工具名 ──
    await run_mcp_loop(llm, registry,
        "帮我查一下北京今天的天气",
        "场景3: 无对应工具")

    print(f"\n{'═' * 60}")
    print("验证完成。")


if __name__ == "__main__":
    asyncio.run(main())
