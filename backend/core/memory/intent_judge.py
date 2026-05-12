"""
前置 LLM 意图判断器

在规则检测之前，用一次快速 LLM 调用判断用户输入是否需要查询记忆，
返回建议的搜索关键词和搜索域。

失败或超时时自动回退到规则检测，不影响主流程。
"""

import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

INTENT_JUDGE_PROMPT = """判断用户输入是否需要查询 AI 的记忆库。返回纯 JSON（不要 markdown 代码块）。

规则：
- 问候/闲聊/情感表达 → needs_search: false
- 询问过去的事/具体日期/事件 → needs_search: true，提取关键词
- "记住/记一下/记下来" → write_request: true
- "之前/上次/那天/当时" → needs_search: true
- 时间推演词（最近/上周/变化/进展）→ domains 含 "temporal"

返回格式：
{{"needs_search": bool, "keywords": ["词1","词2"], "write_request": bool, "domains": ["cards"/"diary"/"temporal"]}}

用户输入：{user_input}"""


class IntentJudge:
    """前置 LLM 意图判断器"""

    def __init__(self, llm_api):
        self._llm = llm_api

    def judge(self, user_input: str) -> Optional[Dict[str, Any]]:
        """快速判断意图，失败返回 None（调用方回退规则检测）"""
        if not user_input or not user_input.strip():
            return None
        if not self._llm:
            return None

        prompt = INTENT_JUDGE_PROMPT.format(user_input=user_input[:300])
        messages = [{"role": "user", "content": prompt}]

        try:
            response = self._llm.chat(messages, temperature=0.1)
            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                return None

            content = content.strip()
            # 剥离可能的 markdown 代码块
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            result = json.loads(content)
            logger.info("[IntentJudge] needs_search=%s keywords=%s domains=%s",
                        result.get("needs_search"), result.get("keywords"), result.get("domains"))
            return result
        except json.JSONDecodeError:
            logger.debug("[IntentJudge] JSON 解析失败，回退规则检测")
            return None
        except Exception as e:
            logger.debug("[IntentJudge] LLM 调用失败: %s，回退规则检测", e)
            return None
