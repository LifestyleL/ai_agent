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
import json
import queue
import asyncio
import os
from datetime import datetime, timedelta
from pathlib import Path
from core.llm.llm_api import LLMAPI
import config
from deprecated.live2d.live2d_manager import Live2DManager
from services.tts.tts_service import TTSService
from core.agent.agent_voice import Voice
from core.memory.memory_core import MemoryCore
from core.emotion.emotion_engine import EmotionEngine
from core.vector_memory import VectorMemory
from services.llm.llm_collaborator import create_collaborator
from core.event.event_bus import event_bus, EventType, Event
from core.behavior.drive_model import get_drive_model  # 替换舒适度模型
from core.behavior.persona import get_persona
from core.behavior import instinct_handler  # 导入以注册事件处理器
from core.behavior import mumble_handler  # 导入嘟囔处理器
from core.behavior import autonomous_worker  # 导入自主工作者
from core.long_term_memory import LongTermMemoryManager
from core.deep_memory import DeepMemoryManager
from typing import Dict, Any
 

# 配置（从config.py读取）
IDLE_TIMEOUT = config.AGENT_IDLE_TIMEOUT          # 多久没说话开始独白（秒）
IDLE_INTERVAL = (config.AGENT_IDLE_INTERVAL_MIN, config.AGENT_IDLE_INTERVAL_MAX)   # 独白间隔范围（秒）

# 全局 TTS 队列（用于封死后门，强制所有声音走统一队列）
_global_tts_queue = None

class YumeDriver:
    # TTS 缓冲掩护语池（随机挑选一句，给工具调用/查记忆争取时间）
    _BUFFER_SENTENCES = [
        "让我想想……",
        "嗯……我想想啊……",
        "稍等一下，我回忆回忆……",
        "等等，让我想想这件事……",
        "这个嘛……我想想……",
    ]

    def __init__(self):
        # --- 内存级上下文 (RAM 驻留，不再二次读盘) ---
        self.mem_personality = ""      # 人设
        self.mem_long_term = ""        # 长期记忆
        self.mem_mood_template = ""    # 情绪模板

        self.short_term_history = []   # 短期记忆列表 (格式: [{"role": "user", "content": "..."}])
        self.max_history_tokens = config.SHORT_TERM_HISTORY_TOKENS # 短期记忆最大 token 预算（粗略用字符数除以2估算）

        # --- 初始化新的记忆系统（三层架构）---
        print("[MemorySystem] 初始化情绪引擎、向量记忆和记忆核心...")
        self.emotion_engine = EmotionEngine()
        self.vector_memory = VectorMemory()
        self.memory_core = MemoryCore(vector_memory=self.vector_memory)
        print("[MemorySystem] 记忆系统初始化完成")

        # 启动时冷加载（只读这一次）
        self._init_memory_context()

        # [V1→V3] 从 short_term.json 加载短期记忆到内存
        short_term_path = Path(__file__).parent.parent / "agent_memory" / "short_term.json"
        print(f"[V1→V3] 短期记忆文件路径: {short_term_path}")
        print(f"[V1→V3] 文件是否存在: {short_term_path.exists()}")
        if short_term_path.exists():
            try:
                with open(short_term_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                dialogues = data.get("dialogues", [])
                # 转换为 short_term_history 的格式
                self.short_term_history = []
                for d in dialogues:
                    role = d.get("role", "user")
                    content = d.get("content", "")
                    self.short_term_history.append({
                        "role": role,
                        "content": content
                    })
                print(f"[V1→V3] 已从 short_term.json 加载 {len(self.short_term_history)} 条短期记忆")
                if self.short_term_history:
                    print(f"[V1→V3] 第一条记忆: {self.short_term_history[0]['role']}: {self.short_term_history[0]['content'][:30]}...")
            except Exception as e:
                print(f"[V1→V3] 加载 short_term.json 失败: {e}")
                import traceback
                traceback.print_exc()
                self.short_term_history = []
        else:
            print("[V1→V3] short_term.json 不存在，短期记忆为空")
            self.short_term_history = []

        # 创建协作管理器（千问+DeepSeek双模型）
        self.collaborator = create_collaborator()
        # 注入内存上下文（零I/O）
        self.collaborator.set_memory_context(
            personality=self.mem_personality,
            long_term=self.mem_long_term,
            mood_template=self.mem_mood_template,
            short_term_history=self.short_term_history
        )

        # --- 初始化 V3.0 长期记忆与深度记忆 ---
        # 注意：deepseek_client 是协作管理器中的 DeepSeek 模型实例
        deepseek_client = None
        if hasattr(self.collaborator, 'llm_deepseek'):
            deepseek_client = self.collaborator.llm_deepseek
        elif hasattr(self.collaborator, 'get_deepseek_client'):
            deepseek_client = self.collaborator.get_deepseek_client()
        else:
            print("[WARN] 未找到 deepseek_client，长期记忆功能可能受限")

        self._long_term_mem = LongTermMemoryManager(llm_client=deepseek_client)
        self._deep_mem = DeepMemoryManager()
        self._last_active_date = datetime.now().strftime("%Y-%m-%d")  # 三叉戟：懒检查标志
        print("[MemorySystem] V3.0 长期记忆与深度记忆管理器初始化完成")

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

        # TTS 异步播放队列（主线程只入队，不阻塞）
        self._tts_queue = queue.Queue(maxsize=10)
        # 暴露给全局，用于封死后门，强制所有声音走统一队列
        global _global_tts_queue
        _global_tts_queue = self._tts_queue
        self._current_emotion = "neutral"  # 当前回复的情感

        # 启动后台消费线程
        self._tts_worker_thread = threading.Thread(target=self._tts_worker_loop, daemon=True)
        self._tts_worker_thread.start()
        print("[Agent Driver] TTS 后台消费线程已启动")

        self.is_running = False
        self.last_activity = time.time()
        self._speak_lock = threading.Lock()  # 保证嘴巴同一时间只说一句话
        self._thinking = False  # 思考中标志，防止独白干扰
        self.last_emotion_tag = None  # 上一次的情绪打标结果
        # 深度回忆缓存槽：上一轮后台查到的碎片，本轮注入 Prompt
        self._pending_recalls: list = []

        # 驱动模型（替代舒适度模型）
        self.drive_model = get_drive_model()
        print("[DriveModel] 驱动模型已加载")

        # 人设
        self.persona = get_persona()
        print(f"[Persona] 人设已加载: {self.persona.name}")

        # 初始化本能处理器的LLM实例
        instinct_handler.init_instinct_handler(llm_qwen)

        # 初始化自驱动引擎（用户沉默时主动发言）
        try:
            from core.spontaneous.engine import SpontaneousEngine
            self.spontaneous_engine = SpontaneousEngine(
                memory_core=self.memory_core,
                llm_collaborator=self.collaborator
            )
            # 设置发言回调：将主动发言送入TTS队列
            self.spontaneous_engine.set_speech_callback(self._on_spontaneous_speech)
            print("[SpontaneousEngine] 自驱动引擎初始化成功")
        except Exception as e:
            print(f"[SpontaneousEngine] 初始化失败: {e}")
            self.spontaneous_engine = None

        # 注册思考中间步骤事件处理器
        self._setup_event_handlers()

    # ----------------------------------------

    def _init_memory_context(self):
        """启动时冷加载所有记忆文件到内存，主链路0 I/O"""
        print("[System] 正在冷加载记忆至内存...")
        # [V1→V3] 使用 V3 标准方法读取
        self.mem_personality = self.memory_core.load_personality()
        self.mem_long_term = self.memory_core.get_random_long_term_memory_v3(3)  # V3日记获取
        self.mem_mood_template = self.memory_core.load_mood_templates()
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

    # [V1→V3] 已废弃：短期记忆写入已由 memory_core.add_short_term() 接管
    # def _lazy_save_to_disk(self, user_text: str, ai_reply: str):
    #     """延迟异步写入磁盘，绝对不阻塞主回复流（线程版）"""
    #     def save_task():
    #         time.sleep(3)  # 延迟 3 秒，把网络和算力优先让给 TTS
    #         now = datetime.now().strftime("%Y-%m-%d %H:%M")
    #         record = f"## {now}\n**用户**：{user_text}\n**yume**：{ai_reply}"
    #         # [V1→V3] 已废弃：写入已由 memory_core.add_short_term() 接管
    #         # MemoryCore.append_to_file("short_memories.md", record)
    #         print(f"[Disk] 异步落盘完成: {user_text[:30]}...")
    #
    #     thread = threading.Thread(target=save_task, daemon=True)
    #     thread.start()

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
        # 延迟诊断：用户输入接收时间戳
        user_input_time = time.time() * 1000  # 毫秒
        print(f"[延迟诊断] user_input_received 时间戳: {user_input_time:.2f} ms (文本: '{text[:30]}...')")

        if not text.strip():
            return

        # 【三叉戟 - 叉2：跨天懒检查】
        today = datetime.now().strftime("%Y-%m-%d")
        if self._last_active_date != today:
            self._last_active_date = today
            draft_path = "agent_memory/daily_draft.txt"
            # 检查昨天的草稿是否非空
            if os.path.isfile(draft_path) and os.path.getsize(draft_path) > 0:
                yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                # 后台异步执行，绝对不阻塞当前对话
                asyncio.create_task(self._diary_pipeline(yesterday))

        # 【深度回忆——Prompt 注入】
        recall_injection = ""
        recall_count = 0
        if self._pending_recalls:
            recall_count = len(self._pending_recalls)
            recall_injection = "\n\n【潜意识浮现】\n"
            for i, fragment in enumerate(self._pending_recalls, 1):
                recall_injection += f"{i}. {fragment}\n"
            recall_injection += "（如果你觉得这些模糊的感受与当前对话相关，可以自然地提出来）\n"
            # 注入后立即清空缓存槽
            self._pending_recalls = []

        # 将 recall_injection 注入到系统提示词中
        if recall_injection:
            # 注入到 collaborator 的长期记忆上下文中
            original_long_term = self.collaborator.mem_long_term if hasattr(self.collaborator, 'mem_long_term') else ""
            enhanced_long_term = f"{original_long_term}\n{recall_injection}" if original_long_term else recall_injection
            # 更新 collaborator 的内存上下文
            if hasattr(self.collaborator, 'mem_long_term'):
                self.collaborator.mem_long_term = enhanced_long_term
            elif hasattr(self.collaborator, 'set_memory_context'):
                # 如果 mem_long_term 不是公共属性，使用 set_memory_context
                self.collaborator.set_memory_context(
                    personality=self.mem_personality,
                    long_term=enhanced_long_term,
                    mood_template=self.mem_mood_template,
                    short_term_history=self.short_term_history
                )
            print(f"[深度回忆] 已注入 {recall_count} 条潜意识碎片到系统提示词")

        # 1. 刷新时间戳 → 打断独白倒计时
        self.last_activity = time.time()

        # 通知自驱动引擎用户活动
        if self.spontaneous_engine:
            self.spontaneous_engine.on_user_activity(text)

        # 重置当前情感（默认中性）
        self._current_emotion = "neutral"

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

            # --- 深层回忆检索（条件触发）---
            deep_memories_text = ""
            try:
                if self.last_emotion_tag is not None:
                    # 获取当前情绪状态
                    current_emotion = self.memory_core.get_current_emotion()
                    emotion_type = current_emotion.get("type", 0)
                    emotion_strength = int(current_emotion.get("strength", 0))
                    scene_type = self.last_emotion_tag.get("scene_type", "A")

                    # 调用条件触发检索
                    retrieved_memories = self.vector_memory.conditional_retrieve(
                        current_emotion_type=emotion_type,
                        current_emotion_strength=emotion_strength,
                        current_scene_type=scene_type,
                        query_text=text
                    )

                    if retrieved_memories:
                        # 格式化深层回忆字符串
                        memory_lines = ["【潜意识浮现的记忆】："]
                        for memory in retrieved_memories:
                            memory_lines.append(f"- {memory.get('content', '')}")
                            memory_lines.append("  （此刻你的心境与此记忆产生了共鸣...）")
                        deep_memories_text = "\n".join(memory_lines)

                        # 注入到 collaborator 的长期记忆上下文中
                        original_long_term = self.collaborator.mem_long_term if hasattr(self.collaborator, 'mem_long_term') else ""
                        enhanced_long_term = f"{original_long_term}\n\n{deep_memories_text}" if original_long_term else deep_memories_text
                        # 更新 collaborator 的内存上下文
                        if hasattr(self.collaborator, 'mem_long_term'):
                            self.collaborator.mem_long_term = enhanced_long_term
                        elif hasattr(self.collaborator, 'set_memory_context'):
                            # 如果 mem_long_term 不是公共属性，使用 set_memory_context
                            self.collaborator.set_memory_context(
                                personality=self.mem_personality,
                                long_term=enhanced_long_term,
                                mood_template=self.mem_mood_template,
                                short_term_history=self.short_term_history
                            )
                        print(f"[DeepMemory] 注入 {len(retrieved_memories)} 条深层回忆")
                    else:
                        print("[DeepMemory] 未触发深层回忆检索")
                else:
                    print("[DeepMemory] 尚无情绪标签，跳过深层回忆检索")
            except Exception as e:
                print(f"[DeepMemory] 深层回忆检索失败: {e}")

            # 流式消费：实现边出字边说话（文字入队，TTS后台合成）
            full_text_received = ""
            for chunk_data in self.collaborator.collaborate_stream(text):
                # 使用新的流式处理方法（只入队，不等待）
                should_break, full_text_received = self._process_stream_chunk(
                    chunk_data, full_text_received, text
                )
                if should_break:
                    break

            # 异步落盘：保存用户输入和AI回复到短期记忆（不阻塞主链路）
            if full_text_received.strip():
                # [V1→V3] 已废弃：短期记忆写入已由 memory_core.add_short_term() 接管
                # self._lazy_save_to_disk(text, full_text_received.strip())
                # 同时打印完整回复（便于调试）
                print(f"\n💬 [Agent] 完整回复: {full_text_received.strip()}")

                # 通知自驱动引擎AI已发言（用户输入触发的）
                if self.spontaneous_engine:
                    self.spontaneous_engine.on_ai_spoke(full_text_received.strip())


                # --- 异步执行新的记忆系统写入（不阻塞播放）---
                async def async_memory_write():
                    try:
                        # --- 草稿积累（V3.0 日记素材）---
                        try:
                            writer = self._long_term_mem.get_writer()
                            await writer.append_draft(f"用户：{text[:100]}")
                            await writer.append_draft(f"我：{full_text_received.strip()[:100]}")
                        except Exception as e:
                            print(f"[WARN] 草稿写入失败: {e}")
                            # 草稿写入失败绝不影响对话

                        # 1. 极简规则打标
                        # V3.0 暂不启用规则打标功能
                        # [V1→V3] 从情绪引擎读取真实情绪
                        real_emotion = self.memory_core.get_current_emotion() if self.memory_core else None
                        print(f"[V1→V3] 原始情绪数据: {real_emotion}")
                        if real_emotion and isinstance(real_emotion, dict):
                            # 调试：打印所有键
                            print(f"[V1→V3] 情绪数据键: {list(real_emotion.keys())}")
                            # 尝试不同可能的字段名
                            emotion_type = real_emotion.get("type",
                                          real_emotion.get("emotion_type",
                                          real_emotion.get("label",
                                          real_emotion.get("mood", 0))))
                            emotion_strength = real_emotion.get("strength", 1)
                            scene_type = real_emotion.get("scene",
                                         real_emotion.get("scene_type", "A"))
                            tag_result = {
                                "emotion_type": emotion_type,
                                "emotion_strength": emotion_strength,
                                "scene_type": scene_type
                            }
                            print(f"[V1→V3] 情绪标签: type={tag_result['emotion_type']}, strength={tag_result['emotion_strength']}, scene={tag_result['scene_type']}")
                        else:
                            tag_result = {"emotion_type": 0, "emotion_strength": 1, "scene_type": "A"}
                            print(f"[V1→V3] 使用默认情绪标签: {tag_result}")
                        # 存储情绪标签供下一轮深层回忆检索使用
                        self.last_emotion_tag = tag_result

                        # 2. 更新情绪状态
                        current_emotion = self.memory_core.update_and_get_emotion(
                            tag_result["emotion_type"],
                            tag_result["emotion_strength"]
                        )

                        # 3. 添加短期记忆
                        self.memory_core.add_short_term("user", text)
                        self.memory_core.add_short_term("assistant", full_text_received.strip())

                        # [V1→V3] 同步更新内存中的短期历史记录
                        self.short_term_history.append({"role": "user", "content": text})
                        self.short_term_history.append({"role": "assistant", "content": full_text_received.strip()})
                        # 保持短期历史记录长度限制
                        if len(self.short_term_history) > self.max_history_tokens * 2:  # 粗略估计
                            self.short_term_history = self.short_term_history[-self.max_history_tokens:]
                        # 更新 collaborator 上下文
                        self.collaborator.set_memory_context(
                            personality=self.mem_personality,
                            long_term=self.mem_long_term,
                            mood_template=self.mem_mood_template,
                            short_term_history=self.short_term_history
                        )

                        # 4. 触发长期记忆存储（内部会检查入库条件）
                        # 需要补充 scene_type 到 current_emotion 字典中
                        current_emotion["scene_type"] = tag_result["scene_type"]
                        # V3.0 暂不启用长期记忆存储功能

                        print(f"[Memory] 记忆写入完成 (情绪: {tag_result['emotion_type']}, 强度: {tag_result['emotion_strength']}, 场景: {tag_result['scene_type']})")

                        # 【深度回忆——被动触发】
                        # 获取当前情绪状态
                        emotion_strength = tag_result["emotion_strength"]
                        # 将 emotion_type 映射到标签
                        emotion_type_to_label = {
                            0: "平静",
                            1: "开心",
                            2: "难过",
                            3: "烦躁"
                        }
                        emotion_label = emotion_type_to_label.get(tag_result["emotion_type"], "平静")

                        # 门控条件：情绪强度 >= 5 才触发（与 V1 的门控逻辑一致）
                        if emotion_strength >= 5:
                            try:
                                recall_result = await self._deep_mem.subconscious_recall(
                                    query=text[:50],  # 只取前50字作为查询，足够语义匹配
                                    emotion_label=emotion_label
                                )
                                if recall_result:
                                    self._pending_recalls = recall_result
                                    print(f"[深度回忆] 捕获 {len(recall_result)} 条潜意识碎片，留待下轮注入")
                            except Exception as e:
                                print(f"[WARN] 深度回忆触发失败: {e}")
                                # 深度回忆失败绝不影响对话
                    except Exception as e:
                        print(f"[Memory] 记忆写入失败: {e}")

                # 启动后台线程执行异步记忆写入
                def memory_write_task():
                    try:
                        asyncio.run(async_memory_write())
                    except Exception as e:
                        print(f"[Memory] 异步记忆写入失败: {e}")

                memory_thread = threading.Thread(target=memory_write_task, daemon=True)
                memory_thread.start()

            return
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
    # 日记流水线（三叉戟 - 叉1）
    # ----------------------------------------
    async def _diary_pipeline(self, date_str: str):
        """日记流水线：生成日记 → 长期索引入库 → 深度碎片入库"""
        try:
            # 第一阶段：LLM 生成日记与碎片
            writer = self._long_term_mem.get_writer()
            result = await writer.generate_daily_diary(date_str)

            if not result or not result.get("diary_path"):
                return  # 草稿为空，跳过

            # 第二阶段：长期记忆索引入库
            await self._long_term_mem.index_today_diary(date_str)

            # 第三阶段：深度记忆碎片入库
            fragments_path = result.get("fragments_path", "")
            if fragments_path and os.path.isfile(fragments_path):
                await self._deep_mem.index_today_fragments(fragments_path)

            print(f"[日记流水线] {date_str} 归档完成：日记+碎片+双库索引")
        except Exception as e:
            print(f"[日记流水线] {date_str} 归档失败：{e}")
            # 绝不因流水线失败影响主对话

    # ----------------------------------------
    # 启动
    # ----------------------------------------
    def start(self):
        self.is_running = True
        self.last_activity = time.time()

        # 启动驱动模型
        self.drive_model.start()

        # 启动自驱动引擎
        if self.spontaneous_engine:
            try:
                self.spontaneous_engine.start()
                print("[SpontaneousEngine] 自驱动引擎已启动")
            except Exception as e:
                print(f"[SpontaneousEngine] 启动失败: {e}")

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

                # 发布TTS请求（封死后门：强制所有声音走统一队列）
                try:
                    # 队列项目包含文本和情感信息
                    tts_item = {"text": text, "emotion": "neutral"}
                    self._tts_queue.put(tts_item, timeout=2.0)
                    print(f"[Discovery] TTS请求已入队: '{text[:30]}...'")
                except queue.Full:
                    print(f"[WARN] [Discovery] TTS队列已满，丢弃发现回复: '{text[:20]}...'")
                except Exception as e:
                    print(f"[ERROR] [Discovery] TTS入队失败: {e}")

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
                    # 清空草稿纸（V1→V3 已废弃）
                    # MemoryCore.clear_file("surfing_memories.md", backup=False)
                    return

                print(f"[SurfingReview] 千问回复: {qwen_response[:100]}...")

                # 检查是否返回"无"
                if qwen_response.strip() == "无":
                    print("[SurfingReview] 千问表示没有想记住的内容")
                else:
                    # 写入长期记忆
                    # [V1→V3] 已废弃：长期记忆写入已由日记系统接管
                    # MemoryCore.append_to_file("memories.md", "\n\n" + qwen_response.strip())
                    print("[SurfingReview] 已写入长期记忆")

                # 无论结果如何，清空草稿纸（V1→V3 已废弃）
                # MemoryCore.clear_file("surfing_memories.md", backup=False)
                print("[SurfingReview] 冲浪草稿纸已清空")

            except Exception as e:
                print(f"[SurfingReview] 冲浪回顾异常: {e}")
                # 异常时也尝试清空草稿纸（V1→V3 已废弃）
                # try:
                #     MemoryCore.clear_file("surfing_memories.md", backup=False)
                # except:
                #     pass

        print("[EventHandlers] 冲浪回顾事件处理器已注册")

    # ----------------------------------------
    # WebSocket文本发送方法
    # ----------------------------------------
    def _send_text_to_frontend(self, text: str, text_type: str = "chunk"):
        """
        发送文本消息到前端（用于打字机效果）

        Args:
            text: 要发送的文本
            text_type: 文本类型 - "thinking"（思考提示）或 "chunk"（回复片段）
        """
        try:
            # 局部导入，避免循环导入
            from api.netwebsocket.ws_server import ws_instance

            if not ws_instance:
                return

            # 构建消息数据
            data = {
                "type": "TEXT_" + text_type.upper(),
                "text": text,
                "timestamp": time.time()
            }

            # 尝试通过send_queue发送（非阻塞）
            if hasattr(ws_instance, 'send_queue'):
                ws_instance.send_queue.put(data)
                if text_type == "thinking":
                    print(f"[WS] 思考提示已排队: '{text[:30]}...'")
                else:
                    print(f"[WS] 文本片段已排队: '{text[:30]}...'")
            else:
                print(f"[WARN] ws_instance没有send_queue属性")

        except ImportError:
            print(f"[WARN] WebSocket模块导入失败，前端打字机效果不可用")
        except Exception as e:
            print(f"[ERROR] 发送文本到前端失败: {e}")

    # ----------------------------------------
    # TTS 后台消费线程
    # ----------------------------------------
    def _tts_worker_loop(self):
        """
        后台线程：从队列取句子，同步调用 TTS，确保一句播完才播下一句。
        """
        while True:
            item = self._tts_queue.get()

            # 收到退出哨兵，结束线程
            if item is None:
                self._tts_queue.task_done()
                break

            # 解析队列项目：可能是字典（包含text和emotion）或字符串（兼容旧格式）
            if isinstance(item, dict):
                text = item.get("text", "")
                emotion = item.get("emotion", self._current_emotion)
            else:
                # 旧格式：纯字符串
                text = item
                emotion = self._current_emotion

            if not text.strip():
                self._tts_queue.task_done()
                continue

            try:
                # 【关键】直接调用语音模块，绕过事件总线，确保同步执行
                # 先清除完成事件状态
                self.voice._tts_done_event.clear()

                # 发布 TTS 请求事件（全系统唯一允许的地方）
                event_bus.publish(
                    EventType.TTS_REQUESTED,
                    source="_tts_worker_loop",
                    text=text,
                    emotion=emotion,
                    timestamp=time.time()
                )

                # 【核心】阻塞等待 TTS 合成完毕（最多等 60 秒）
                if not self.voice._tts_done_event.wait(timeout=60):
                    print(f"[ERROR] [TTS_Queue] 句子合成超时(60s): '{text[:30]}...' (情感: {emotion})")
                else:
                    print(f"[OK] [TTS_Queue] 句子合成完成: '{text[:30]}...' (情感: {emotion})")

            except Exception as e:
                print(f"[ERROR] [TTS_Queue] 合成出错: {e}")
            finally:
                self._tts_queue.task_done()

    # ----------------------------------------
    # 流式处理逻辑（只入队，不等待）
    # ----------------------------------------
    def _process_stream_chunk(self, chunk_data: dict, full_text_received: str, text: str):
        """
        处理流式chunk：文字推前端，句子入队列

        Args:
            chunk_data: 流式chunk数据
            full_text_received: 累积的完整文本引用
            text: 用户输入文本
        Returns:
            tuple: (是否结束, 累积文本)
        """
        chunk_type = chunk_data.get("type")

        if chunk_type == "thinking":
            thinking_text = chunk_data.get("text", "")
            print(f"[Stream] [思考提示] {thinking_text}")
            # 发送思考提示到前端
            self._send_text_to_frontend(thinking_text, "thinking")

        elif chunk_type == "tool":
            # 【TTS 掩护——工具调用缓冲】
            # 在发起工具调用之前，先推一句缓冲语到 TTS 队列
            buffer = self._get_buffer_sentence()
            # 使用现有的 TTS 队列方法推送缓冲语
            # 如果暂时找不到 TTS 推送方法，先打印日志占位：
            print(f"[TTS掩护] 推送缓冲语：{buffer}")
            # 工具调用结果将在后续处理
            tool_name = chunk_data.get("tool", "")
            tool_params = chunk_data.get("params", {})
            print(f"[Tool] 工具调用: {tool_name}, 参数: {tool_params}")

        elif chunk_type == "chunk":
            chunk_text = chunk_data.get("text", "")
            # 1. 立刻推给前端（不阻塞）
            print(chunk_text, end="", flush=True)  # 控制台实时打印
            self._send_text_to_frontend(chunk_text, "chunk")

            # 2. 积累完整文本用于记忆写入
            full_text_received += chunk_text

            # 3. 过滤掉换行符，绝对不让它进入 TTS 缓冲区
            chunk_text = chunk_text.replace("\n", "").replace("\r", "")

            # 4. 攒入TTS缓冲区
            if not hasattr(self, '_tts_buffer'):
                self._tts_buffer = ""
            self._tts_buffer += chunk_text

            # 5. 只有遇到句号、问号、感叹号才断句入队（只切走标点及前面的内容）
            first_end_pos = -1
            for punc in ["。", "！", "？"]:
                pos = self._tts_buffer.find(punc)
                if pos != -1:
                    if first_end_pos == -1 or pos < first_end_pos:
                        first_end_pos = pos

            if first_end_pos != -1:
                # 找到第一个标点，切走标点及之前的文本，标点后的文本留在缓冲区
                sentence = self._tts_buffer[:first_end_pos + 1]
                self._tts_buffer = self._tts_buffer[first_end_pos + 1:]
                # 把句子扔进队列，如果队列满了会自动阻塞一会儿（保护机制）
                try:
                    # 队列项目包含文本和情感信息
                    tts_item = {"text": sentence, "emotion": self._current_emotion}
                    self._tts_queue.put(tts_item, timeout=2.0)
                    # 延迟诊断：第一句入队时间戳
                    queue_time = time.time() * 1000  # 毫秒
                    print(f"[延迟诊断] 第一句句子已入队时间戳: {queue_time:.2f} ms (文本: '{sentence[:30]}...')")
                    print(f"[Queue] [TTS] 句子已入队: '{sentence[:30]}...' (情感: {self._current_emotion})")
                except queue.Full:
                    print(f"[WARN] [TTS_Queue] 队列已满，丢弃句子: '{sentence[:20]}...'")

        elif chunk_type == "done":
            # 获取最终情感和动作
            final_emotion = chunk_data.get("emotion", "neutral")
            final_action = chunk_data.get("action", "")

            # 流式结束，把尾巴也扔进队列（使用最终情感）
            if hasattr(self, '_tts_buffer') and self._tts_buffer.strip():
                tail_text = self._tts_buffer
                self._tts_buffer = ""
                try:
                    # 队列项目包含文本和情感信息
                    tts_item = {"text": tail_text, "emotion": final_emotion}
                    self._tts_queue.put(tts_item, timeout=2.0)
                    # 延迟诊断：尾巴句子入队时间戳
                    tail_queue_time = time.time() * 1000  # 毫秒
                    print(f"[延迟诊断] 尾巴句子已入队时间戳: {tail_queue_time:.2f} ms (文本: '{tail_text[:30]}...')")
                    print(f"[Queue] [TTS] 尾巴句子已入队: '{tail_text[:30]}...' (情感: {final_emotion})")
                except queue.Full:
                    print(f"[WARN] [TTS_Queue] 队列已满，丢弃尾巴句子: {tail_text[:20]}...")

            # 更新当前情感（用于后续TTS合成）
            self._current_emotion = final_emotion

            # 获取最终情感和动作
            final_emotion = chunk_data.get("emotion", "neutral")
            final_action = chunk_data.get("action", "")
            # 更新当前情感（用于后续TTS合成）
            self._current_emotion = final_emotion

            # 驱动Live2D表情
            if self.live2d:
                self.live2d.set_emotion_mode(final_emotion)

            # 打印动作
            if final_action:
                print(f"[Action] [动作] {final_action}")

            # 发布思考完成事件
            event_bus.publish(
                EventType.THINKING_COMPLETED,
                source="YumeDriver.handle_user_input",
                text=text,
                reply_count=1,
                timestamp=time.time()
            )
            return True, full_text_received  # 结束流式循环

        return False, full_text_received  # 继续流式循环

    # ----------------------------------------
    # 自驱动引擎回调
    # ----------------------------------------
    def _on_spontaneous_speech(self, text: str, context: Dict[str, Any]):
        """
        自驱动引擎的回调函数：将主动发言送入TTS队列

        Args:
            text: 发言文本
            context: 发言上下文（包含情感、优先级等）
        """

        if not text.strip():
            return

        emotion = context.get("emotion", "neutral")
        priority = context.get("priority", 1)
        trigger_reason = context.get("trigger_reason", "")

        print(f"[SpontaneousEngine] 主动发言: '{text}'")
        print(f"  情感: {emotion}, 优先级: {priority}, 触发原因: {trigger_reason}")

        # 更新当前情感
        self._current_emotion = emotion

        # 驱动Live2D表情
        if self.live2d:
            self.live2d.set_emotion_mode(emotion)

        # 将发言送入TTS队列
        tts_item = {"text": text, "emotion": emotion}
        try:
            self._tts_queue.put(tts_item, timeout=2.0)
            print(f"[Queue] [TTS] 主动发言已入队: '{text[:30]}...' (情感: {emotion})")

            # 通知引擎AI已发言
            if self.spontaneous_engine:
                self.spontaneous_engine.on_ai_spoke(text)

        except queue.Full:
            print(f"[WARN] [TTS_Queue] 队列已满，丢弃主动发言: '{text[:20]}...'")
        except Exception as e:
            print(f"[ERROR] 主动发言入队失败: {e}")

    # ----------------------------------------
    # 系统关闭清理
    # ----------------------------------------
    def shutdown(self):
        """关闭 TTS 后台线程和自驱动引擎"""
        # 停止自驱动引擎
        if hasattr(self, 'spontaneous_engine') and self.spontaneous_engine:
            try:
                self.spontaneous_engine.stop()
                print("[SpontaneousEngine] 自驱动引擎已停止")
            except Exception as e:
                print(f"[SpontaneousEngine] 停止失败: {e}")

        print("[Agent Driver] 正在关闭 TTS 后台线程...")
        # 发送退出哨兵
        self._tts_queue.put(None)
        # 等待线程结束
        self._tts_worker_thread.join(timeout=2)
        if self._tts_worker_thread.is_alive():
            print("[WARN] TTS 后台线程未能正常结束")
        else:
            print("[OK] TTS 后台线程已关闭")

    # ----------------------------------------
    # TTS 缓冲掩护语池
    # ----------------------------------------
    def _get_buffer_sentence(self) -> str:
        import random
        return random.choice(self._BUFFER_SENTENCES)




