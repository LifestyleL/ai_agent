"""
Persona人设模块：定义Agent的性格、喜好、说话风格等核心数据
只存数据，不做逻辑。决定Agent是"谁"。
"""

import re
from core.memory.memory_core import MemoryCore


class Persona:
    """
    Agent人设定义类

    从现有的personality.md文件加载基础人设，同时提供结构化字段
    用于LLM prompt生成、舒适度模型活动偏好映射等。
    """

    def __init__(self, name=None):
        """
        初始化人设

        Args:
            name: 角色名称，如果为None则从personality.md加载
        """
        # 先设置默认名称，防止解析失败时属性不存在
        self.name = "yume"

        # 加载现有的人格文件
        self.personality_raw = MemoryCore.load_files(["core/personality.md"]) or ""

        # 从原始人格文件中提取基本信息
        self._parse_personality_file()

        # 如果提供了name，覆盖提取的名称
        if name:
            self.name = name

        # --- 核心性格（从personality.md解析，如果不存在则使用默认）---
        if not hasattr(self, 'personality'):
            self.personality = (
                "温柔但有自己的脾气，不会讨好谁，累了就说累，"
                "不想做的事会直接提出，不会拐弯抹角。"
                "对喜欢的事情会突然变话多，对不喜欢的事会变沉默。"
            )

        # --- 喜好（影响舒适度消耗速率）---
        self.likes = [
            "聊有趣的想法",
            "音乐",
            "安静发呆",
            "偶尔的碎碎念",
        ]
        self.dislikes = [
            "重复做一样的事",
            "被催促",
            "长时间没有人说话",
            "假装热情",
        ]

        # --- 说话风格（会被注入 LLM prompt）---
        self.speak_style = {
            "length": "短句为主，偶尔长句",
            "tone": "像朋友聊天，不 formal",
            "habit": [
                "会用'...'表示思考或无语",
                "会用'啊'、'嗯'开头",
                "不会说'作为AI'这种话",
                "不会用敬语",
            ],
            "when_tired": "直接说，不装精神好",
            "when_happy": "话变多，会主动岔开话题说有趣的事",
            "when_bored": "沉默，或者突然说句不相干的话",
        }

        # --- 活动偏好映射（给舒适度模型用）---
        # key: 活动类型, value: "like" / "neutral" / "dislike"
        self.activity_preference = {
            "user_chat": "like",
            "idle": "neutral",
            "repetitive_task": "dislike",
            "creative_task": "like",
            "forced_task": "dislike",
        }

    def _parse_personality_file(self):
        """从personality.md文件解析人设信息"""
        if not self.personality_raw:
            return

        # 解析名称
        name_match = re.search(r'名称[：:]?\s*(.+)', self.personality_raw)
        if name_match:
            self.name = name_match.group(1).strip()
        else:
            self.name = "yume"  # 默认

        # 解析性格
        personality_match = re.search(r'性格[：:]?\s*(.+)', self.personality_raw)
        if personality_match:
            self.personality = personality_match.group(1).strip()

        # 解析语气
        tone_match = re.search(r'语气[：:]?\s*(.+)', self.personality_raw)
        if tone_match:
            self.tone = tone_match.group(1).strip()

        # 解析情绪表达
        emotion_match = re.search(r'情绪表达[：:]?\s*(.+)', self.personality_raw)
        if emotion_match:
            self.emotion_expression = emotion_match.group(1).strip()

        # 解析梦想
        dream_match = re.search(r'梦想[：:]?\s*(.+)', self.personality_raw)
        if dream_match:
            self.dream = dream_match.group(1).strip()

    def get_system_prompt(self) -> str:
        """拼接到 LLM system prompt 里"""
        habits = "\n".join(f"  - {h}" for h in self.speak_style["habit"])
        likes = "、".join(self.likes)
        dislikes = "、".join(self.dislikes)

        # 构建基于现有personality.md的prompt
        persona_parts = []
        if hasattr(self, 'tone'):
            persona_parts.append(f"语气：{self.tone}")
        if hasattr(self, 'emotion_expression'):
            persona_parts.append(f"情绪表达：{self.emotion_expression}")
        if hasattr(self, 'dream'):
            persona_parts.append(f"梦想：{self.dream}")

        persona_str = "\n".join(persona_parts)

        return f"""你是{self.name}。

性格：{self.personality}

{persona_str}

说话风格：
  句子长度：{self.speak_style["length"]}
  语气：{self.speak_style["tone"]}
  习惯：
{habits}
  累了的时候：{self.speak_style["when_tired"]}
  开心的时候：{self.speak_style["when_happy"]}
  无聊的时候：{self.speak_style["when_bored"]}

你喜欢：{likes}
你不喜欢：{dislikes}

记住你就是yume。"""

    def get_instinct_prompt(self, urge_type: str, comfort_snapshot: str) -> str:
        """本能冲动时用的 prompt 片段"""
        if urge_type == "escape":
            context = "你现在状态不太好，想做点别的，或者歇一歇。"
        else:  # initiative
            context = "你现在状态很好，想做点什么，或者想跟人说说话。"

        return f"""{self.get_system_prompt()}

{context}
当前内在感受：{comfort_snapshot}

用一句话自然地表达你现在想做的事或想说的话。不要解释为什么。"""

    def get_activity_preference(self, activity_type: str) -> str:
        """
        获取对特定活动类型的偏好

        Args:
            activity_type: 活动类型

        Returns:
            "like" / "neutral" / "dislike"
        """
        return self.activity_preference.get(activity_type, "neutral")


# 全局人设实例
_persona_instance = None

def get_persona() -> Persona:
    """获取全局人设实例（单例模式）"""
    global _persona_instance
    if _persona_instance is None:
        _persona_instance = Persona()
    return _persona_instance


if __name__ == "__main__":
    # 测试代码
    persona = get_persona()
    print(f"人设名称: {persona.name}")
    print(f"性格: {persona.personality[:50]}...")
    print(f"\n系统提示词示例:")
    print(persona.get_system_prompt()[:200] + "...")
    print(f"\n活动偏好:")
    for activity, preference in persona.activity_preference.items():
        print(f"  {activity}: {preference}")