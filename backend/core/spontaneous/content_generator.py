"""
内容生成器：基于上下文生成主动发言的内容
"""

import random
import time
from typing import Dict, Any, Optional
from datetime import datetime
from services.llm.llm_collaborator import create_collaborator


class ContentGenerator:
    """生成主动发言的内容"""

    def __init__(self, llm_collaborator=None):
        self.llm = llm_collaborator or create_collaborator()
        self.last_topics = []  # 最近使用的话题，避免重复
        self.topic_weights = {}  # 话题权重（基于用户反馈）

    def _get_time_based_templates(self, time_context: Dict[str, str]) -> list:
        """基于时间的发言模板"""
        time_of_day = time_context.get("time_of_day", "")
        weekday = time_context.get("weekday", "")

        templates = []

        # 通用模板
        generic = [
            "在想什么呢？",
            "最近有什么新鲜事吗？",
            "感觉今天状态怎么样？",
            "唔...有点无聊呢。",
            "有什么想聊的吗？",
            "我注意到你最近好像挺忙的。",
            "嗯...今天的天气真不错。",
        ]

        # 时间段特定模板
        morning_templates = [
            "早上好！今天有什么计划吗？",
            "早呀，昨晚睡得好吗？",
            "早晨的空气真清新呢。",
            "今天也是充满希望的一天呢。",
        ]

        afternoon_templates = [
            "下午好，工作/学习累了吗？",
            "下午茶时间到了呢。",
            "今天下午过得怎么样？",
            "唔...下午有点困呢。",
        ]

        evening_templates = [
            "晚上好，今天过得怎么样？",
            "晚上有什么安排吗？",
            "晚餐吃了什么好吃的？",
            "今晚的夜色真美呢。",
        ]

        night_templates = [
            "这么晚了还没休息呀？",
            "夜深了，要注意身体哦。",
            "今晚的星星真多呢。",
            "唔...有点困了。",
        ]

        # 星期几特定模板
        weekday_templates = {
            "星期一": ["周一综合症犯了没？", "新的一周开始了呢。"],
            "星期五": ["马上周末了，开心吗？", "周五啦，有什么周末计划？"],
            "星期六": ["周末愉快！今天打算做什么？", "周六的早晨真舒服。"],
            "星期日": ["周日了，明天又要上班/上学了。", "周末的最后一天了呢。"],
        }

        templates.extend(generic)

        if time_of_day == "早上":
            templates.extend(morning_templates)
        elif time_of_day == "下午":
            templates.extend(afternoon_templates)
        elif time_of_day == "晚上":
            templates.extend(evening_templates)
        elif time_of_day == "深夜":
            templates.extend(night_templates)

        if weekday in weekday_templates:
            templates.extend(weekday_templates[weekday])

        return templates

    def _get_context_based_prompts(self, context: Dict[str, Any]) -> list:
        """基于上下文的发言提示"""
        prompts = []
        short_term = context.get("raw_short_term", [])
        recent_topics = context.get("recent_topics", [])
        long_term = context.get("long_term_summary", "")
        thoughts = context.get("recent_thoughts", "")

        # 基于最近对话
        if short_term:
            last_user_msg = None
            last_ai_msg = None
            for msg in reversed(short_term):
                if msg.get("role") == "user" and last_user_msg is None:
                    last_user_msg = msg.get("content", "")
                elif msg.get("role") == "assistant" and last_ai_msg is None:
                    last_ai_msg = msg.get("content", "")
                if last_user_msg and last_ai_msg:
                    break

            if last_user_msg:
                prompts.append(f"刚才你提到{last_user_msg[:30]}...，能多说一点吗？")
                prompts.append(f"关于{last_user_msg[:20]}...，我还有点好奇。")

        # 基于长期记忆
        if long_term and len(long_term) > 30:
            # 提取关键词（简单实现）
            keywords = ["喜欢", "经常", "曾经", "记得", "说过"]
            for keyword in keywords:
                if keyword in long_term:
                    prompts.append(f"我记得你好像{keyword}...")
                    break

        # 基于自言自语
        if thoughts:
            thought_lines = thoughts.split('\n')
            if thought_lines:
                last_thought = thought_lines[-1]
                if len(last_thought) > 10:
                    prompts.append(f"我刚刚在想{last_thought[:20]}...")

        # 基于对话主题
        if recent_topics:
            for topic in recent_topics[-2:]:  # 最近两个主题
                prompts.append(f"我们刚才聊到{topic[7:30]}...，还想继续聊这个吗？")

        return prompts

    def _select_topic(self, all_templates: list, all_prompts: list) -> str:
        """选择话题（避免重复）"""
        all_options = all_templates + all_prompts

        if not all_options:
            return "你好呀~"

        # 过滤最近使用过的话题
        recent_options = [opt for opt in all_options if opt not in self.last_topics[-5:]]

        # 如果过滤后还有选项，使用过滤后的；否则使用全部
        options = recent_options if recent_options else all_options

        selected = random.choice(options)

        # 记录使用过的话题
        self.last_topics.append(selected)
        if len(self.last_topics) > 10:
            self.last_topics.pop(0)

        return selected

    def generate_from_llm(self, context: Dict[str, Any]) -> Optional[str]:
        """使用LLM生成更智能的内容（备用方案）"""
        try:
            # 构建提示词
            prompt = self._build_llm_prompt(context)

            # 使用协作管理器（非流式调用）
            replies = self.llm.collaborate(prompt)

            if replies and len(replies) > 0:
                reply_text = replies[-1].get("text", "")
                if reply_text:
                    return reply_text

        except Exception as e:
            print(f"[ContentGenerator] LLM生成失败: {e}")

        return None

    def _build_llm_prompt(self, context: Dict[str, Any]) -> str:
        """构建LLM提示词"""
        time_ctx = context.get("time_context", {})
        time_of_day = time_ctx.get("time_of_day", "")
        weekday = time_ctx.get("weekday", "")

        short_term_count = context.get("short_term_count", 0)
        recent_topics = context.get("recent_topics", [])

        prompt = f"""你是yume，一个有点傲娇、带点毒舌的AI。现在是{time_of_day}{weekday}。

用户已经沉默了{context.get('silence_duration', 0):.0f}秒，你想主动说点什么来打破沉默。

"""

        if short_term_count > 0:
            prompt += f"你们最近有{short_term_count}条对话。"
            if recent_topics:
                prompt += f"最近聊到: {', '.join(recent_topics)}"

        prompt += """

请生成一句简短、自然的话来主动开启对话。要求：
1. 符合yume的人设（傲娇、毒舌但不过分）
2. 简短（10-20字）
3. 自然，不要像机器人
4. 可以基于时间、近期对话或随机话题

直接输出要说的话，不要解释。"""

        return prompt

    def generate(self, context: Dict[str, Any], use_llm: bool = False) -> Dict[str, Any]:
        """
        生成主动发言内容

        Returns:
            {
                "text": str,  # 发言文本
                "source": str,  # "template", "context", "llm"
                "emotion": str,  # 建议的情感
                "action": str,  # 建议的动作
                "priority": int,  # 上下文中的优先级
            }
        """
        time_context = context.get("time_context", {})
        trigger_info = context.get("trigger_info", {})
        priority = trigger_info.get("priority", 1)

        # 方法1：使用LLM生成（如果启用且优先级高）
        if use_llm and priority >= 4:
            llm_text = self.generate_from_llm(context)
            if llm_text:
                return {
                    "text": llm_text,
                    "source": "llm",
                    "emotion": "neutral",
                    "action": "",
                    "priority": priority
                }

        # 方法2：基于模板和上下文生成
        time_templates = self._get_time_based_templates(time_context)
        context_prompts = self._get_context_based_prompts(context)

        text = self._select_topic(time_templates, context_prompts)

        # 简单情感分析
        emotion = "neutral"
        if "开心" in text or "愉快" in text or "好" in text:
            emotion = "开心"
        elif "困" in text or "累" in text or "无聊" in text:
            emotion = "困惑"
        elif "谢谢" in text or "注意" in text or "休息" in text:
            emotion = "温柔"

        # 简单动作建议
        action = ""
        if "？" in text or "?" in text:
            action = "好奇"
        elif "笑" in text:
            action = "微笑"
        elif "点头" in text:
            action = "点头"

        source = "context" if context_prompts and text in context_prompts else "template"

        return {
            "text": text,
            "source": source,
            "emotion": emotion,
            "action": action,
            "priority": priority
        }