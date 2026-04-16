import json
import re
from typing import Dict, List, Any, Optional
from llm.llm_api import LLMAPI
from memory import ConversationMemory
from tools.base import BaseTool
from decision_engine import DecisionEngine
from executor import Executor
from prompts import DECISION_PROMPT, PERSONA_PROMPT, REASONING_PROMPT

class Agent:
    """重构后的Agent：引入决策层和执行器"""

    def __init__(self, llm_api: LLMAPI, memory: ConversationMemory,
                 tools: List[BaseTool] = None):
        self.llm = llm_api
        self.memory = memory
        self.tools = {tool.name: tool for tool in (tools or [])}

        # 初始化决策引擎
        self.decision_engine = DecisionEngine(llm_api, DECISION_PROMPT)

        # 初始化执行器
        self.executor = Executor(
            llm_api,
            PERSONA_PROMPT,
            REASONING_PROMPT,
            self.tools
        )

    def run(self, user_input: str) -> Dict[str, Any]:
        """运行Agent"""
        # 1. 获取上下文
        context = self._get_context()

        # 2. 决策
        decision = self.decision_engine.decide(context, user_input)

        # 3. 执行
        result = self.executor.execute(decision, context, user_input)

        # 4. 更新记忆
        self.memory.add_message("user", user_input)
        self.memory.add_message("assistant", result["reply"])

        # 5. 提取和存储事实（可选）
        self._extract_and_store_facts(user_input, result["reply"])

        return result

    def _get_context(self) -> str:
        """获取上下文信息"""
        # 获取最近对话
        recent_context = self.memory.get_recent_context()
        context_lines = []
        for msg in recent_context[-6:]:  # 最近3轮对话
            role = "用户" if msg["role"] == "user" else "助手"
            context_lines.append(f"{role}: {msg['content']}")

        # 获取相关记忆
        relevant_knowledge = self.memory.search_knowledge(" ".join(context_lines))
        similar_hits = self.memory.find_similar_facts(" ".join(context_lines), threshold=0.6, limit=3)

        memory_lines = []
        if relevant_knowledge:
            memory_lines.extend(relevant_knowledge)
        if similar_hits:
            memory_lines.extend([
                f"{h['key']}:{h['value']}" if h["type"] == "user_info" else h["value"]
                for h in similar_hits
            ])

        context = "\n".join(context_lines + memory_lines) if (context_lines or memory_lines) else "无"
        return context

    def _extract_and_store_facts(self, user_input: str, response: str):
        """提取并存储事实"""
        # 提取用户名字
        name_pattern = r"我叫(\w+)|我是(\w+)"
        match = re.search(name_pattern, user_input)
        if match:
            name = match.group(1) or match.group(2)
            fact = f"用户名字: {name}"
            added = self.memory.add_fact(fact)
            if not added:
                print(f"未添加事实（可能已存在）: {fact}")
                
                

