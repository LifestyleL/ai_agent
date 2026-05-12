"""
PromptBuilder — 将 Persona 纯数据格式化为 LLM Prompt

分离数据与格式化逻辑。依赖方通过 DI 容器获取 PromptBuilder，
避免 Persona 数据类包含格式化代码。
"""

from .persona import Persona


class PromptBuilder:
    """基于 Persona 数据构建 System Prompt 和 Instinct Prompt"""

    def __init__(self, persona: Persona):
        self._persona = persona

    def build_system_prompt(self) -> str:
        """拼接到 LLM system prompt 里"""
        p = self._persona
        habits = "\n".join(f"  - {h}" for h in p.speak_style.get("habit", []))
        likes = "、".join(p.likes)
        dislikes = "、".join(p.dislikes)

        persona_parts = []
        if p.tone:
            persona_parts.append(f"语气：{p.tone}")
        if p.emotion_expression:
            persona_parts.append(f"情绪表达：{p.emotion_expression}")
        if p.dream:
            persona_parts.append(f"梦想：{p.dream}")
        persona_str = "\n".join(persona_parts)

        return f"""你是{p.name}。

性格：{p.personality}

{persona_str}

说话风格：
  句子长度：{p.speak_style.get("length", "")}
  语气：{p.speak_style.get("tone", "")}
  习惯：
{habits}
  累了的时候：{p.speak_style.get("when_tired", "")}
  开心的时候：{p.speak_style.get("when_happy", "")}
  无聊的时候：{p.speak_style.get("when_bored", "")}

你喜欢：{likes}
你不喜欢：{dislikes}

记住你就是{p.name}。"""

    def build_instinct_prompt(self, urge_type: str, comfort_snapshot: str) -> str:
        """本能冲动时用的 prompt 片段"""
        if urge_type == "escape":
            context = "你现在状态不太好，想做点别的，或者歇一歇。"
        else:  # initiative
            context = "你现在状态很好，想做点什么，或者想跟人说说话。"

        return f"""{self.build_system_prompt()}

{context}
当前内在感受：{comfort_snapshot}

用一句话自然地表达你现在想做的事或想说的话。不要解释为什么。"""

    def build_stream_system_prompt(self) -> str:
        """构建流式输出的 system prompt（精简版）"""
        p = self._persona
        return f"""你是{p.name}。{p.personality}

说话风格：{p.speak_style.get("length", "")}，{p.speak_style.get("tone", "")}
- {chr(10).join(f"  - {h}" for h in p.speak_style.get("habit", [])[:2])}

记住你就是{p.name}。请用自然的口吻回答。"""
