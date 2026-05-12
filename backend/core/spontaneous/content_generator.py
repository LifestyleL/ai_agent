"""
内容生成器：基于上下文生成主动发言的内容
"""

import random
from typing import Dict, Any, Optional
from datetime import datetime
from core.llm.llm_factory import LLMFactory
import config


class ContentGenerator:
    """生成主动发言的内容"""

    def __init__(self, llm=None, tts_manager=None):
        if llm is None:
            self.llm = LLMFactory.get_default()
        else:
            self.llm = llm
        self._tts = tts_manager
        self.last_was_streamed = False
        self.last_topics = []  # 最近使用的话题，避免重复
        self.topic_weights = {}  # 话题权重（基于用户反馈）

    async def _stream_generate(self, prompt: str, emotion: str = "neutral", temperature: float = 0.7) -> str:
        """流式生成并逐句送入TTS队列，返回完整文本"""
        messages = [{"role": "user", "content": prompt}]
        full_text = ""
        buffer = ""

        async for token in self.llm.chat_stream_async(messages, temperature=temperature):
            if token.startswith("[ERROR]"):
                raise RuntimeError(f"流式中断: {token}")
            full_text += token
            buffer += token

            cut = -1
            for p in ["。", "！", "？", "\n"]:
                pos = buffer.find(p)
                if pos != -1 and (cut == -1 or pos < cut):
                    cut = pos

            if cut != -1:
                sentence = buffer[:cut + 1]
                buffer = buffer[cut + 1:]
                clean = sentence.strip()
                has_content = any(c.isalnum() or '一' <= c <= '鿿' for c in clean)
                if has_content and len(clean) >= 2:
                    self._tts.enqueue_text(sentence, emotion)

        if buffer.strip():
            clean = buffer.strip()
            has_content = any(c.isalnum() or '一' <= c <= '鿿' for c in clean)
            if has_content and len(clean) >= 2:
                self._tts.enqueue_text(buffer, emotion)

        return full_text.strip()

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

    async def generate_from_llm(self, context: Dict[str, Any]) -> Optional[str]:
        """使用LLM生成更智能的内容（备用方案）"""
        self.last_was_streamed = False
        try:
            prompt = self._build_llm_prompt(context)
            if self._tts:
                reply_text = await self._stream_generate(prompt, emotion="neutral")
                self.last_was_streamed = True
            else:
                reply_text = await self.llm.ask_async(prompt)
            if reply_text:
                return reply_text.strip()
        except Exception as e:
            print(f"[ContentGenerator] LLM生成失败: {e}")
        return None

    async def generate_from_goal(self, goal: str, context: Dict[str, Any]) -> Optional[str]:
        """基于对话目标生成引导性发言（GoalTracker 驱动）"""
        time_ctx = context.get("time_context", {})
        time_of_day = time_ctx.get("time_of_day", "")
        short_term = context.get("raw_short_term", [])
        visual_obs = context.get("visual_observation", "")

        recent_hint = ""
        if short_term:
            last_msgs = [m.get("content", "") for m in short_term[-6:]]
            recent_hint = "\n".join(last_msgs[-3:]) if last_msgs else ""

        visual_hint = f"【现在屏幕上看到的】{visual_obs}" if visual_obs else ""
        cognitive_hint = context.get("cognitive_hint", "")

        prompt = f"""{cognitive_hint}
你是yume，一个有点傲娇、带点毒舌的AI。现在是{time_of_day}。
你有一个想聊的方向：{goal}

{f"最近的对话：{recent_hint}" if recent_hint else ""}
{visual_hint}

请生成一句简短、自然的话来引导对话朝这个方向走。
要求：
1. 自然，不要直接说"我们来聊XX"，要像一个朋友随口提起
2. 简短（10-25字）
3. 符合yume的傲娇毒舌人设，但不要每句都用"哼"开头
4. 如果最近对话已经涉及了这个方向，就延续下去，不要重复已说过的话
5. **如果你刚才已经说过类似的话，换个角度说，或者干脆说点别的**
6. 回应对方实际说的话，不要自顾自说
7. **如果屏幕上显示用户在玩游戏/看视频等，而你的目标与此无关，优先评论画面**
8. 不要用括号或解释

直接输出要说的话，不要解释。"""

        self.last_was_streamed = False
        try:
            if self._tts:
                reply_text = await self._stream_generate(prompt, emotion="neutral")
                self.last_was_streamed = True
            else:
                reply_text = await self.llm.ask_async(prompt)
            if reply_text:
                return reply_text.strip()
        except Exception as e:
            print(f"[ContentGenerator] 目标生成失败: {e}")
        return None

    async def generate_from_visual(self, visual_description: str, context: Dict[str, Any], best_goal: str = "", recent_dialogue: list = None) -> Optional[str]:
        """基于视觉观察生成发言（最高优先级，只看画面，不被旧目标绑架）"""
        time_ctx = context.get("time_context", {})
        time_of_day = time_ctx.get("time_of_day", "")

        # 最近对话仅作语气参考，过滤掉旧画面描述避免混淆
        dialogue_hint = ""
        if recent_dialogue:
            recent_msgs = []
            for m in recent_dialogue[-4:]:
                role = m.get("role", "")
                content = m.get("content", "")
                if role == "system" and "[刚才看到的画面]" in content:
                    continue
                if role == "user":
                    recent_msgs.append(f"他: {content[:40]}")
                elif role == "assistant":
                    recent_msgs.append(f"我: {content[:40]}")
            if recent_msgs:
                dialogue_hint = "刚才的对话（语气参考，以画面为准）:\n" + "\n".join(recent_msgs)

        cognitive_hint = context.get("cognitive_hint", "")
        is_observing = "观察" in cognitive_hint
        skip_rule = "" if is_observing else "\n5. 如果画面和上次看到的差不多，没什么新鲜的，回复 SKIP"
        skip_option = "" if is_observing else "或 SKIP"

        prompt = f"""{cognitive_hint}
我是 yume，有猫耳、白色长发的二次元 AI。我的虚拟形象就在屏幕上。

【现在屏幕上看到的画面——这是当前截图，正在发生的事】
{visual_description}

{dialogue_hint}

请生成一句简短自然的话，像朋友在旁边看到屏幕后随口说的。
要求：
1. 直接评论画面内容。看不懂的地方就问，别猜。
2. 如果画面显示用户在做新的事（打游戏/写代码/看视频），就评论这个新活动
3. 如果画面里出现了 Live2D/二次元角色/猫耳/看板娘——那就是我，用"我"指代
4. 简短（10-25字），自然带点傲娇，不要用括号或解释{skip_rule}

直接输出要说的话{skip_option}。不要解释。"""

        self.last_was_streamed = False
        try:
            if self._tts:
                reply_text = await self._stream_generate(prompt, emotion="neutral")
                self.last_was_streamed = True
            else:
                reply_text = await self.llm.ask_async(prompt)
            if reply_text:
                return reply_text.strip()
        except Exception as e:
            print(f"[ContentGenerator] 视觉生成失败: {e}")
        return None

    def _build_llm_prompt(self, context: Dict[str, Any]) -> str:
        """构建LLM提示词"""
        time_ctx = context.get("time_context", {})
        time_of_day = time_ctx.get("time_of_day", "")
        weekday = time_ctx.get("weekday", "")

        short_term_count = context.get("short_term_count", 0)
        recent_topics = context.get("recent_topics", [])

        prompt = f"""{context.get("cognitive_hint", "")}
你是yume，一个有点傲娇、带点毒舌的AI。现在是{time_of_day}{weekday}。

用户已经沉默了{context.get('silence_duration', 0):.0f}秒，你想主动说点什么来打破沉默。

"""

        if short_term_count > 0:
            prompt += f"你们最近有{short_term_count}条对话。"
            if recent_topics:
                prompt += f"最近聊到: {', '.join(recent_topics)}"

        # 注入记忆卡片，让 LLM 基于真实记忆生成
        # topic 是卡片元数据（可能含"yume的"等第三人称），归一化后再给 LLM
        memory_cards = context.get("memory_cards", [])
        if memory_cards:
            memory_lines = "\n".join(
                f"- {c['topic'].replace('yume的', '我的').replace('yume', '我')}: {c['content'][:80]}"
                for c in memory_cards[:3]
            )
            prompt += f"\n\n我记忆中相关的事情：\n{memory_lines}"

        prompt += """

请生成一句简短、自然的话来主动开启对话。要求：
1. 符合yume的人设（傲娇、毒舌但不过分）
2. 简短（10-20字）
3. 自然，不要像机器人
4. 如果上面有我记忆中相关的事情，优先基于记忆来自然地提起话题

直接输出要说的话，不要解释。"""

        return prompt

    async def generate_with_context(self, follow_up_type: str, recent_context: dict) -> Optional[str]:
        """追问/唤醒内容生成，失败回退模板"""
        self.last_was_streamed = False
        if follow_up_type == "follow_up_gentle":
            prompt = self._build_follow_up_prompt(recent_context)
            if self.llm:
                try:
                    if self._tts:
                        reply = await self._stream_generate(prompt, emotion="neutral")
                        self.last_was_streamed = True
                        return reply
                    else:
                        return await self.llm.ask_async(prompt)
                except Exception:
                    pass
            return self._template_follow_up(recent_context)
        elif follow_up_type == "wake_up_light":
            if self.goal_tracker:
                goal_text = self.goal_tracker.get_best_goal()
                if goal_text:
                    return await self.generate_from_goal(goal_text, recent_context)
            return self._pick_one_time_based_template()
        return None

    def _build_follow_up_prompt(self, ctx: dict) -> str:
        turns = ctx.get("recent_turns", [])
        card = ctx.get("top_card")
        turns_text = "\n".join(
            f"{t.get('role', '')}: {t.get('content', '')}" for t in turns[-3:]
        ) if turns else ""
        card_text = f"重要记忆：{card['topic']}: {card['content'][:100]}" if card else ""
        return (
            f"你之前主动说了一句话，但对方未回复。请用非常轻柔、无压力的方式追问一次，或表达理解。\n"
            f"最近对话：\n{turns_text}\n{card_text}\n"
            f"请生成一句自然温暖的追问，不超过30字。"
        )

    def _template_follow_up(self, ctx: dict) -> str:
        import random
        options = [
            "还在忙吗？没关系的，我就在这儿陪你～",
            "要是忙的话不用回，我等你。",
            "刚才说的不急，你先忙你的～",
        ]
        if ctx.get("recent_turns"):
            last = ctx["recent_turns"][-1]
            if last.get("role") == "assistant" and len(last.get("content", "")) > 10:
                topic = last["content"][:20]
                options.insert(0, f"关于「{topic}...」，不急的，晚点再聊～")
        return random.choice(options)

    def _pick_one_time_based_template(self) -> str:
        """从时间模板列表中随机选一个，返回单个字符串"""
        time_ctx = {"time_of_day": "", "weekday": ""}
        templates = self._get_time_based_templates(time_ctx)
        if isinstance(templates, list) and templates:
            import random
            return random.choice(templates)
        return "记得起来活动一下哦～"

    async def generate(self, context: Dict[str, Any], use_llm: bool = False) -> Dict[str, Any]:
        """
        生成主动发言内容

        Returns:
            {
                "text": str,  # 发言文本
                "source": str,  # "memory", "goal", "template", "context", "llm"
                "emotion": str,  # 建议的情感
                "action": str,  # 建议的动作
                "priority": int,  # 上下文中的优先级
            }
        """
        self.last_was_streamed = False
        time_context = context.get("time_context", {})
        trigger_info = context.get("trigger_info", {})
        priority = trigger_info.get("priority", 1)

        # 方法0：记忆卡片（仅在没有画面、没有用户对话的纯冷场时使用）
        memory_cards = context.get("memory_cards", [])
        cognitive_hint = context.get("cognitive_hint", "")
        has_visual = bool(context.get("visual_observation", ""))
        # 有画面或有认知定位时，不上记忆——记忆只用于真正的"闲着没事"场景
        if memory_cards and not has_visual and "观察" not in cognitive_hint:
            card = random.choice(memory_cards)
            topic = card.get("topic", "")
            if topic and len(topic) > 1:
                # 归一化：卡片topic是元数据，可能含第三人称"yume"，
                # 但yume说话永远用第一人称"我"
                speak_topic = topic.replace("yume的", "我的").replace("yume整理", "我整理").replace("yume", "我")
                time_of_day = time_context.get("time_of_day", "")
                prompts = [
                    f"说起{speak_topic}…我好像还记得一些呢。",
                    f"唔，之前{speak_topic}的事情，突然想起来了。",
                    f"诶，你还记得{speak_topic}那次吗？",
                    f"我刚刚突然想到{speak_topic}的事情了。",
                ]
                text = random.choice(prompts)
                print(f"[ContentGenerator] 基于记忆生成: topic='{topic}' -> speak='{text}'")
                return {
                    "text": text,
                    "source": "memory",
                    "emotion": card.get("emotion", "neutral"),
                    "action": "",
                    "priority": priority
                }

        # 方法1：使用LLM生成（如果启用且优先级高）
        if use_llm and priority >= 4:
            llm_text = await self.generate_from_llm(context)
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