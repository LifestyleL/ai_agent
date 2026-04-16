"""
=========================================
Qwen & DeepSeek 架构黄金法则 (V2.0)
=========================================
1. 【Qwen 是自我】只负责感受、说话、指挥。它的上下文必须全在内存(RAM)里，主链路绝对禁止同步读盘。
2. 【DeepSeek 是手脚】没有嘴，只干活。它不需要理解复杂的记忆分类，只调用 5 个极简原子工具。
3. 【短期记忆机制】Qwen 直接从内存列表 `short_term_history` 读取上下文。磁盘上的 `short_memories.md` 仅作为异步备份，主流程不读它。
4. 【工具路由收归代码】复杂的判断（如：有日期没日期用哪个搜索）由 Python 代码处理，DeepSeek 只管无脑传参。
=========================================
"""

import time
import random
import threading
from core.llm.llm_api import LLMAPI
import config
from services.live2d.live2d_manager import Live2DManager
from services.modules.tts.tts_service import TTSService
from core.agent.agent_voice import Voice
from core.memory_core import MemoryCore
from core.llm.llm_collaborator import create_collaborator
from core.event.event_bus import event_bus, EventType, Event
from core.event.drive_model import get_drive_model  # 替换舒适度模型
from core.event.persona import get_persona
from core.event import instinct_handler  # 导入以注册事件处理器
from core.event import mumble_handler  # 导入嘟囔处理器
from core.event import autonomous_worker  # 导入自主工作者
from datetime import datetime
 

# 配置（从config.py读取）
IDLE_TIMEOUT = config.AGENT_IDLE_TIMEOUT          # 多久没说话开始独白（秒）
IDLE_INTERVAL = (config.AGENT_IDLE_INTERVAL_MIN, config.AGENT_IDLE_INTERVAL_MAX)   # 独白间隔范围（秒）

class YumeDriver:
    def __init__(self):
        # --- 内存级上下文 (RAM 驻留，不再二次读盘) ---
        self.mem_personality = ""      # 人设
        self.mem_long_term = ""        # 长期记忆
        self.mem_mood_template = ""    # 情绪模板

        self.short_term_history = []   # 短期记忆列表 (格式: [{"role": "user", "content": "..."}])
        self.max_history_tokens = 1500 # 短期记忆最大 token 预算（粗略用字符数除以2估算）

        # 启动时冷加载（只读这一次）
        self._init_memory_context()

        # 创建协作管理器（千问+DeepSeek双模型）
        self.collaborator = create_collaborator()
        # 注入内存上下文（零I/O）
        self.collaborator.set_memory_context(
            personality=self.mem_personality,
            long_term=self.mem_long_term,
            mood_template=self.mem_mood_template,
            short_term_history=self.short_term_history
        )

        # 获取千问模型用于人设对话和独白生成
        llm_qwen = self.collaborator.llm_qwen

        self.live2d = Live2DManager()

        # 尝试初始化TTS，如果失败则使用模拟TTS
        try:
            tts_instance = TTSService()
            print("[TTS] TTS服务初始化成功")
        except Exception as e:
            print(f"[TTS] TTS服务初始化失败: {e}")
            print("[TTS] 将使用模拟TTS，系统可运行但无语音")
            # 创建模拟TTS对象
            class MockTTS:
                def __init__(self):
                    self._is_connected = False
                def _init_realtime_tts(self):
                    # 模拟初始化，什么也不做
                    pass
                def _synthesize_with_retry(self, text, emotion):
                    # 返回空音频和口型数据
                    print(f"[模拟TTS] 文本: {text} (情绪: {emotion})")
                    return b'', [{'t': 0.0, 'v': 0.0}]
            tts_instance = MockTTS()

        self.voice = Voice(
            tts=tts_instance,
            live2d=self.live2d,
            collaborator=self.collaborator  # 使用协作管理器生成人设独白
        )

        self.is_running = False
        self.last_activity = time.time()
        self._speak_lock = threading.Lock()  # 保证嘴巴同一时间只说一句话
        self._thinking = False  # 思考中标志，防止独白干扰

        # 驱动模型（替代舒适度模型）
        self.drive_model = get_drive_model()
        print("[DriveModel] 驱动模型已加载")

        # 人设
        self.persona = get_persona()
        print(f"[Persona] 人设已加载: {self.persona.name}")

        # 初始化本能处理器的LLM实例
        instinct_handler.init_instinct_handler(llm_qwen)

        # 注册思考中间步骤事件处理器
        self._setup_event_handlers()

    # ----------------------------------------

    def _init_memory_context(self):
        """启动时冷加载所有记忆文件到内存，主链路0 I/O"""
        print("[System] 正在冷加载记忆至内存...")
        self.mem_personality = MemoryCore.load_files(["personality.md"])
        self.mem_long_term = MemoryCore.get_random_long_term_memory(3)  # 复用现有方法
        self.mem_mood_template = MemoryCore.load_files(["mood_blank.md"])
        print("[System] 记忆加载完毕，主链路 0 I/O。")

    # ----------------------------------------

    def _trim_short_term_history(self):
        """粗略估算并裁剪短期历史，防止超出上下文"""
        total_chars = sum(len(m["content"]) for m in self.short_term_history)
        while total_chars > self.max_history_tokens * 2 and len(self.short_term_history) > 4:
            self.short_term_history.pop(0)
            total_chars = sum(len(m["content"]) for m in self.short_term_history)

        # 更新内存缓存
        MemoryCore.set_short_term_memory_cache(self.short_term_history)

    def _lazy_save_to_disk(self, user_text: str, ai_reply: str):
        """延迟异步写入磁盘，绝对不阻塞主回复流（线程版）"""
        def save_task():
            time.sleep(3)  # 延迟 3 秒，把网络和算力优先让给 TTS
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            record = f"## {now}\n**用户**：{user_text}\n**yume**：{ai_reply}"
            MemoryCore.append_to_file("short_memories.md", record)
            print(f"[Disk] 异步落盘完成: {user_text[:30]}...")

        thread = threading.Thread(target=save_task, daemon=True)
        thread.start()

    # ----------------------------------------

    def _detect_activity_type(self, text: str) -> str:
        """
        根据用户输入内容检测活动类型

        Args:
            text: 用户输入的文本

        Returns:
            活动类型字符串
        """
        # 简单关键词检测（可后续改进为LLM判断）
        text_lower = text.lower()

        # 检测重复性任务关键词
        repetitive_keywords = ["重复", "再做一遍", "继续做", "继续刚才", "继续之前", "继续", "接着", "连续", "一直"]
        if any(keyword in text_lower for keyword in repetitive_keywords):
            return "repetitive_task"

        # 检测创造性任务关键词
        creative_keywords = ["创作", "写诗", "写文章", "写故事", "画", "设计", "创意", "想象", "构思"]
        if any(keyword in text_lower for keyword in creative_keywords):
            return "creative_task"

        # 检测强制任务关键词
        forced_keywords = ["必须", "一定", "非得", "非要", "强制", "强迫", "逼", "命令"]
        if any(keyword in text_lower for keyword in forced_keywords):
            return "forced_task"

        # 默认：用户聊天
        return "user_chat"

    # ----------------------------------------
    # 处理用户交互
    # ----------------------------------------
    def handle_user_input(self, text: str):
        if not text.strip():
            return
            
        # 1. 刷新时间戳 → 打断独白倒计时
        self.last_activity = time.time()

        # 1.5 检测活动类型（保留用于日志，驱动模型通过事件自动更新）
        activity_type = self._detect_activity_type(text)
        print(f"[Activity] 检测到活动类型: {activity_type}")

        # 2. 抢锁 → 独白不能插嘴
        self._speak_lock.acquire()
        
        try:
            print(f"[Brain] [Agent] 收到输入: {text}")

            # 发布用户输入事件
            event_bus.publish(
                EventType.USER_INPUT_RECEIVED,
                source="YumeDriver.handle_user_input",
                text=text,
                timestamp=time.time()
            )

            # 🌟 3. 调用协作管理器进行双模型协作思考
            # 发布思考开始事件
            event_bus.publish(
                EventType.THINKING_STARTED,
                source="YumeDriver.handle_user_input",
                text=text,
                timestamp=time.time()
            )

            # 设置思考标志，防止独白干扰
            self._thinking = True
            print("[Thinking] [Agent] 思考中，暂停闲置独白计时")

            reply_dicts = self.collaborator.collaborate(text)

            # 异步落盘：保存用户输入和AI回复到短期记忆（不阻塞主链路）
            if reply_dicts:
                self._lazy_save_to_disk(text, reply_dicts[0].get("text", ""))

            # 发布思考完成事件
            event_bus.publish(
                EventType.THINKING_COMPLETED,
                source="YumeDriver.handle_user_input",
                text=text,
                reply_count=len(reply_dicts),
                timestamp=time.time()
            )

            for reply_dict in reply_dicts:
                text_reply = reply_dict.get("text", "").strip()
                emotion = reply_dict.get("emotion", "neutral")
                action = reply_dict.get("action", "")

                if not text_reply:
                    print("[WARN] [Agent] 大脑返回空文本")
                    continue

                print(f"💬 [Agent] 回复: {text_reply}")

                # 4. 驱动 Live2D 表情
                if self.live2d:
                    self.live2d.set_emotion_mode(emotion)

                # 5. 如果有动作，可以打印（后续如果要联动动作库在这里加）
                if action:
                    print(f"[Action] [动作] {action}")

                # 6. 交给 Voice 去发音并推给前端
                print(f"[Audio] [Agent] 开始语音合成: '{text_reply[:30]}...'")
                # 发布TTS请求事件
                event_bus.publish(
                    EventType.TTS_REQUESTED,
                    source="YumeDriver.handle_user_input",
                    text=text_reply[:100],  # 只记录前100字符
                    emotion=emotion,
                    timestamp=time.time()
                )
                self.voice.speak(text_reply, emotion=emotion)
                # 等待当前TTS完成，避免多个回复重叠
                if not self.voice._tts_done_event.wait(timeout=30):
                    print("[WARN] [Agent] TTS等待超时，继续下一个回复")
                    # 发布TTS超时事件
                    event_bus.publish(
                        EventType.TTS_FAILED,
                        source="YumeDriver.handle_user_input",
                        text=text_reply[:50],
                        error="等待超时30秒",
                        timestamp=time.time()
                    )
                else:
                    print("[OK] [Agent] TTS完成")
                    # 发布TTS完成事件
                    event_bus.publish(
                        EventType.TTS_COMPLETED,
                        source="YumeDriver.handle_user_input",
                        text=text_reply[:50],
                        emotion=emotion,
                        timestamp=time.time()
                    )
            
        except Exception as e:
            print(f"[ERROR] 处理用户输入出错: {e}")
            # 发布错误事件
            event_bus.publish(
                EventType.ERROR_OCCURRED,
                source="YumeDriver.handle_user_input",
                error=str(e),
                timestamp=time.time()
            )
            # 如果与TTS相关，发布TTS失败事件
            if "tts" in str(e).lower() or "voice" in str(e).lower() or "speak" in str(e).lower():
                event_bus.publish(
                    EventType.TTS_FAILED,
                    source="YumeDriver.handle_user_input",
                    error=str(e),
                    timestamp=time.time()
                )
            import traceback
            traceback.print_exc()
        finally:
            # 7. 清除思考标志，恢复闲置独白计时
            self._thinking = False
            print("[OK] [Agent] 思考完成，恢复闲置独白计时")

            # 8. 发布用户输入处理完成事件
            event_bus.publish(
                EventType.USER_INPUT_PROCESSED,
                source="YumeDriver.handle_user_input",
                text=text[:100] if text else "",
                timestamp=time.time()
            )

            # 9. 必须释放锁，还给它独白权
            self._speak_lock.release()

    # ----------------------------------------
    # 启动
    # ----------------------------------------
    def start(self):
        self.is_running = True
        self.last_activity = time.time()

        # 启动驱动模型
        self.drive_model.start()

        print("[OK] Agent 大脑已在后台待命")

    # ----------------------------------------
    # 事件处理器
    # ----------------------------------------
    def _setup_event_handlers(self):
        """设置事件处理器"""
        from core.event.event_bus import event_bus, EventType, event_handler

        # 思考中间步骤事件处理器 - 实时播放思考过程互动
        @event_handler(EventType.THINKING_INTERMEDIATE)
        def handle_thinking_intermediate(event):
            # 只有在处理用户输入时才实时播放思考过程互动
            if not self._thinking:
                return

            thought_text = event.data.get("thought", "")
            if not thought_text.strip():
                return

            print(f"[ThinkingInteraction] 实时播放思考过程互动: '{thought_text}'")

            # 直接调用语音合成的底层方法，不设置完成事件（非阻塞）
            try:
                # 使用 _speak_segment 而不是 speak，避免设置完成事件
                self.voice._speak_segment(thought_text, emotion="neutral")
            except Exception as e:
                print(f"[Warn] 实时播放思考过程互动失败: {e}")

        print("[EventHandlers] 思考过程互动事件处理器已注册")

        # 发现事件处理器 - 处理后台搜索到的知识
        @event_handler(EventType.DISCOVERY_MADE)
        def handle_discovery(event):
            topic = event.data.get("topic", "")
            content = event.data.get("content", "")

            if not topic or not content:
                print(f"[Discovery] 发现事件数据不完整: topic={topic}, content={content[:50]}")
                return

            print(f"[Discovery] 处理发现: {topic} - {content[:100]}...")

            # 构建提示词让Qwen用人设语气说出来
            prompt = f"(你刚才自己偷偷查了下{topic})\n查到了：{content}\n用你自己的话感叹或分享一句，不要说你是去查资料的。"

            try:
                # 调用千问生成回复
                text = self.collaborator.llm_qwen.ask(prompt)
                if not text or text.isspace():
                    print("[Discovery] 千问返回空回复")
                    return

                print(f"[Discovery] 千问生成回复: {text}")

                # 发布TTS请求
                event_bus.publish(
                    EventType.TTS_REQUESTED,
                    source="YumeDriver.handle_discovery",
                    text=text,
                    emotion="neutral",  # 默认中性情绪，可以后续优化
                    timestamp=time.time()
                )

            except Exception as e:
                print(f"[Discovery] 处理发现异常: {e}")

        print("[EventHandlers] 发现事件处理器已注册")

        # 冲浪回顾事件处理器 - 处理冲浪草稿纸回顾
        @event_handler(EventType.SURFING_REVIEW_NEEDED)
        def handle_surfing_review(event):
            print("[SurfingReview] 开始处理冲浪回顾...")

            # 读取冲浪草稿纸内容
            surfing_content = MemoryCore.load_files(["surfing_memories.md"])
            if not surfing_content or surfing_content.strip() == "":
                print("[SurfingReview] 冲浪草稿纸为空，无需回顾")
                return

            print(f"[SurfingReview] 草稿纸内容长度: {len(surfing_content)} 字符")

            # 构建提示词给Qwen
            prompt = f"""你最近偷偷查了一些东西，列在下面。
请判断哪些让你觉得"哇这个好有意思我想记住"。

规则：
- 只有真正触动你的才选，无聊的直接忽略
- 如果都不想记，回复"无"
- 如果有想记的，用你的话重新写一遍，格式：
  ## 我的冲浪发现
  - [你自己的感想和记忆]

你查到的东西：
{surfing_content}
"""
            try:
                # 调用千问生成回复
                qwen_response = self.collaborator.llm_qwen.ask(prompt)
                if not qwen_response or qwen_response.isspace():
                    print("[SurfingReview] 千问返回空回复")
                    # 清空草稿纸
                    MemoryCore.clear_file("surfing_memories.md", backup=False)
                    return

                print(f"[SurfingReview] 千问回复: {qwen_response[:100]}...")

                # 检查是否返回"无"
                if qwen_response.strip() == "无":
                    print("[SurfingReview] 千问表示没有想记住的内容")
                else:
                    # 写入长期记忆
                    MemoryCore.append_to_file("memories.md", "\n\n" + qwen_response.strip())
                    print("[SurfingReview] 已写入长期记忆")

                # 无论结果如何，清空草稿纸
                MemoryCore.clear_file("surfing_memories.md", backup=False)
                print("[SurfingReview] 冲浪草稿纸已清空")

            except Exception as e:
                print(f"[SurfingReview] 冲浪回顾异常: {e}")
                # 异常时也尝试清空草稿纸
                try:
                    MemoryCore.clear_file("surfing_memories.md", backup=False)
                except:
                    pass

        print("[EventHandlers] 冲浪回顾事件处理器已注册")




