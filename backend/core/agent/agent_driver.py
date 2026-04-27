"""
=========================================
双 LLM 记忆查询架构 (V4.0)
=========================================
1. DeepSeek 双温度变体：thinker(0.2), speaker(0.7)
2. 记忆系统：MemoryCore 统一管理（纯文件存储，无 FAISS）
3. 主 LLM 无工具定义，纯角色对话；需要深挖记忆时启动查询子线程
4. TTS 播报：统一队列，后台消费线程
5. Live2D：前端 SDK 自主执行动画，后端只发高层指令
=========================================
"""

import time
import threading
import asyncio
from datetime import datetime, timedelta
from core.llm.llm_api import LLMAPI
import config
from services.tts.tts_service import TTSService
from core.agent.agent_voice import Voice
from core.agent.tts_manager import TTSManager
from core.agent.frontend_bridge import FrontendBridge
from core.memory.memory_core import MemoryCore
from core.event.event_bus import event_bus, EventType, Event
from core.behavior.drive_model import get_drive_model
from core.behavior.persona import get_persona
from core.behavior import instinct_handler
from core.behavior import mumble_handler
from core.behavior import autonomous_worker
from typing import Dict, Any


IDLE_TIMEOUT = config.AGENT_IDLE_TIMEOUT
IDLE_INTERVAL = (config.AGENT_IDLE_INTERVAL_MIN, config.AGENT_IDLE_INTERVAL_MAX)

_global_tts_queue = None


class YumeDriver:

    def __init__(self):
        # --- LLM 实例（双温度变体） ---
        self.llm_thinker = LLMAPI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            model=config.DEEPSEEK_MODEL
        )
        self.llm_speaker = LLMAPI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            model=config.DEEPSEEK_MODEL
        )

        # --- 统一记忆系统（V4.0：纯文件存储，无 FAISS） ---
        print("[MemorySystem] V4.0 初始化统一记忆核心...")
        self.memory_core = MemoryCore(llm_api=self.llm_thinker)
        print("[MemorySystem] V4.0 记忆核心就绪")

        # --- 前端通信桥接 ---
        self.frontend = FrontendBridge(self)

        # --- TTS ---
        try:
            tts_instance = TTSService()
            print("[TTS] TTS服务初始化成功")
        except Exception as e:
            print(f"[TTS] TTS服务初始化失败: {e}")
            print("[TTS] 将使用模拟TTS，系统可运行但无语音")
            class MockTTS:
                def __init__(self):
                    self._is_connected = False
                def _init_realtime_tts(self):
                    pass
                def _synthesize_with_retry(self, text, emotion):
                    print(f"[模拟TTS] 文本: {text} (情绪: {emotion})")
                    return b'', [{'t': 0.0, 'v': 0.0}]
            tts_instance = MockTTS()

        self.voice = Voice(tts=tts_instance, llm=self.llm_speaker)

        # TTS 管理器
        self.tts_manager = TTSManager(voice=self.voice, event_bus=event_bus)
        global _global_tts_queue
        _global_tts_queue = self.tts_manager.tts_queue

        # --- 生命周期状态 ---
        self.is_running = False
        self.last_activity = time.time()
        self._speak_lock = threading.Lock()
        self._thinking = False
        self._query_threads: list = []  # 追踪查询子线程

        # --- 驱动模型 & 人设 ---
        self.drive_model = get_drive_model()
        print("[DriveModel] 驱动模型已加载")
        self.persona = get_persona()
        print(f"[Persona] 人设已加载: {self.persona.name}")

        instinct_handler.init_instinct_handler(self.llm_speaker)

        # --- 自驱动引擎 ---
        try:
            from core.spontaneous.engine import SpontaneousEngine
            self.spontaneous_engine = SpontaneousEngine(
                memory_core=self.memory_core,
                llm=self.llm_speaker
            )
            self.spontaneous_engine.set_speech_callback(self._on_spontaneous_speech)
            print("[SpontaneousEngine] 自驱动引擎初始化成功")
        except Exception as e:
            print(f"[SpontaneousEngine] 初始化失败: {e}")
            self.spontaneous_engine = None

        self._setup_event_handlers()

    # ============================================================
    # 事件处理器
    # ============================================================

    def _setup_event_handlers(self):
        from core.event.event_bus import EventType, event_handler

        @event_handler(EventType.THINKING_INTERMEDIATE)
        def handle_thinking_intermediate(event):
            if not self._thinking:
                return
            thought_text = event.data.get("thought", "")
            if not thought_text.strip():
                return
            print(f"[ThinkingInteraction] 实时播放思考过程互动: '{thought_text}'")
            try:
                self.voice._speak_segment(thought_text, emotion="neutral")
            except Exception as e:
                print(f"[Warn] 实时播放思考过程互动失败: {e}")
        print("[EventHandlers] 思考过程互动事件处理器已注册")

        @event_handler(EventType.DISCOVERY_MADE)
        def handle_discovery(event):
            topic = event.data.get("topic", "")
            content = event.data.get("content", "")
            if not topic or not content:
                return
            print(f"[Discovery] 处理发现: {topic} - {content[:100]}...")
            prompt = f"(你刚才自己偷偷查了下{topic})\n查到了：{content}\n用你自己的话感叹或分享一句，不要说你是去查资料的。"
            try:
                text = self.llm_speaker.ask(prompt)
                if text and not text.isspace():
                    self.tts_manager.enqueue_text(text, "neutral")
            except Exception as e:
                print(f"[Discovery] 处理发现异常: {e}")
        print("[EventHandlers] 发现事件处理器已注册")

        @event_handler(EventType.SURFING_REVIEW_NEEDED)
        def handle_surfing_review(event):
            print("[SurfingReview] 开始处理冲浪回顾...")
            surfing_content = MemoryCore.load_files(["surfing_memories.md"])
            if not surfing_content or surfing_content.strip() == "":
                return
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
                speaker_response = self.llm_speaker.ask(prompt)
                if speaker_response and speaker_response.strip() != "无" and not speaker_response.isspace():
                    print("[SurfingReview] 已写入长期记忆")
            except Exception as e:
                print(f"[SurfingReview] 冲浪回顾异常: {e}")
        print("[EventHandlers] 冲浪回顾事件处理器已注册")

    # ============================================================
    # 生命周期
    # ============================================================

    def start(self):
        self.is_running = True
        self.last_activity = time.time()
        self.drive_model.start()
        if self.spontaneous_engine:
            try:
                self.spontaneous_engine.start()
                print("[SpontaneousEngine] 自驱动引擎已启动")
            except Exception as e:
                print(f"[SpontaneousEngine] 启动失败: {e}")
        print("[OK] Agent 大脑已在后台待命")

    def shutdown(self):
        if hasattr(self, 'spontaneous_engine') and self.spontaneous_engine:
            try:
                self.spontaneous_engine.stop()
                print("[SpontaneousEngine] 自驱动引擎已停止")
            except Exception as e:
                print(f"[SpontaneousEngine] 停止失败: {e}")
        self.tts_manager.shutdown()
        try:
            if hasattr(self, 'voice') and hasattr(self.voice, 'tts'):
                self.voice.tts.close()
        except Exception as e:
            print(f"[WARN] TTS 连接关闭异常: {e}")

    # ============================================================
    # 用户输入处理
    # ============================================================

    def handle_user_input(self, text: str):
        user_input_time = time.time() * 1000
        print(f"[延迟诊断] user_input_received 时间戳: {user_input_time:.2f} ms (文本: '{text[:30]}...')")

        if not text.strip():
            return

        # 跨天懒检查 + 日记归档
        self.memory_core.check_cross_day_diary()

        # 深度回忆 Prompt 注入
        recall_injection, recall_count = self.memory_core.build_recall_injection()

        self.last_activity = time.time()

        if self.spontaneous_engine:
            self.spontaneous_engine.on_user_activity(text)

        self.tts_manager.current_emotion = "neutral"

        activity_type = self.memory_core.detect_activity_type(text)
        print(f"[Activity] 检测到活动类型: {activity_type}")

        self._speak_lock.acquire()
        try:
            print(f"[Brain] [Agent] 收到输入: {text}")

            event_bus.publish(
                EventType.USER_INPUT_RECEIVED,
                source="YumeDriver.handle_user_input",
                text=text,
                timestamp=time.time()
            )

            # 状态机接管
            if hasattr(self, 'state_machine') and self.state_machine:
                try:
                    from backend.core.state_machine.state_machine import Event
                    try:
                        loop = asyncio.get_event_loop()
                    except RuntimeError:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                    asyncio.create_task(self.state_machine.trigger(Event.USER_INPUT, {
                        "user_input": text,
                        "recall_injection": recall_injection
                    }))
                    print("[状态机] 已触发 USER_INPUT 事件")
                except Exception as e:
                    print(f"[WARN] 状态机触发失败: {e}")
            else:
                print("[WARN] 状态机未挂载，无法接管用户输入")

            event_bus.publish(
                EventType.THINKING_STARTED,
                source="YumeDriver.handle_user_input",
                text=text,
                timestamp=time.time()
            )

            self._thinking = True
            print("[Thinking] [Agent] 思考中，暂停闲置独白计时")

        except Exception as e:
            print(f"[ERROR] 处理用户输入出错: {e}")
            event_bus.publish(
                EventType.ERROR_OCCURRED,
                source="YumeDriver.handle_user_input",
                error=str(e),
                timestamp=time.time()
            )
            import traceback
            traceback.print_exc()
        finally:
            self._thinking = False
            print("[OK] [Agent] 思考完成，恢复闲置独白计时")
            event_bus.publish(
                EventType.USER_INPUT_PROCESSED,
                source="YumeDriver.handle_user_input",
                text=text[:100] if text else "",
                timestamp=time.time()
            )
            self._speak_lock.release()

    # ============================================================
    # 回调 & 委托方法
    # ============================================================

    def _on_spontaneous_speech(self, text: str, context: Dict[str, Any]):
        """自驱动引擎回调 —— 委托给 TTS 管理器，并发送 Live2D 指令"""
        self.tts_manager.on_spontaneous_speech(text, context)
        emotion = context.get("emotion", "neutral")
        self.frontend.send_live2d_cmd("emotion", emotion=emotion)
        if self.spontaneous_engine:
            self.spontaneous_engine.on_ai_spoke(text)

    def speak_final_text(self, text: str):
        """状态机播报入口 —— 委托给 TTS 管理器"""
        self.tts_manager.speak_final_text(text)

    def send_buffer_text(self, text: str):
        """发送缓冲语到前端（防止冷场）"""
        self.tts_manager.enqueue_text(text, "neutral")
        self.frontend.send_text_to_frontend(text, "thinking")
