"""
自驱动引擎主模块：协调各组件，实现用户沉默时的主动发言
"""

import asyncio
import time
import threading
import json
from typing import Optional, Dict, Any, Callable, List
from datetime import datetime
from pathlib import Path

from .context_reader import ContextReader
from .trigger_policy import TriggerPolicy
from .content_generator import ContentGenerator
from .freq_limiter import FreqLimiter
from .response_tracker import ResponseTracker, ResponseType
from .interrupt_handler import InterruptHandler, InterruptType
from .engagement_profile import EngagementProfile, EngagementParameters, load_profiles_dict, PRESET_PROFILES_PATH
from .engagement_analyzer import UserEngagementAnalyzer
from .silence_gate import SilenceGate, InternalEvent, Decision, detect_short_reply

from ..memory.memory_facade import MemoryFacade as MemoryCore
from ..event.event_bus import event_bus, EventType, Event, event_handler
import config


def _longest_common_substring(a: str, b: str) -> str:
    """两个字符串的最长公共子串（纯函数）"""
    if not a or not b:
        return ""
    m, n = len(a), len(b)
    max_len, end_pos = 0, 0
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
                if curr[j] > max_len:
                    max_len = curr[j]
                    end_pos = i
            else:
                curr[j] = 0
        prev = curr
    return a[end_pos - max_len:end_pos]


class SpontaneousEngine:
    """自驱动引擎主类"""

    def __init__(self, memory_core: MemoryCore, llm=None, goal_tracker=None, visual_observer=None):
        self.memory_core = memory_core
        self.llm = llm
        self.goal_tracker = goal_tracker  # GoalTracker 实例（可选）
        self._visual_observer = visual_observer  # VisualObserver 实例（可选）

        # 初始化组件（注入情绪引擎引用）
        emotion_engine = memory_core._emotion_engine if hasattr(memory_core, '_emotion_engine') else None
        self.context_reader = ContextReader(memory_core)
        self.trigger_policy = TriggerPolicy(emotion_engine=emotion_engine)
        self.content_generator = ContentGenerator(llm)
        self.freq_limiter = FreqLimiter()
        self.response_tracker = ResponseTracker()
        self.interrupt_handler = InterruptHandler()

        # 状态（从全局配置读取）
        self.is_running = False
        self.check_interval = config.SPONTANEOUS_CHECK_INTERVAL
        self.last_check_time = 0
        self.loop_task: Optional[asyncio.Task] = None

        # SilenceGate 语境门控
        self._silence_gate = None  # 在 __init__ 末尾初始化

        # 内部事件队列
        self._internal_events: list = []

        # ── 用户画像 ──
        self._load_user_profile()
        if self.user_profile.mode == "auto":
            self.engagement_analyzer = UserEngagementAnalyzer(
                window_days=7, max_rounds=50
            )
        else:
            self.engagement_analyzer = None
        self._inference_history: list = []

        # ── 会话状态 ──
        self._last_daily_greet_date: Optional[str] = None

        # 回调函数
        self.speech_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None

        # 心跳日志计数器
        self._loop_ticks = 0

        # 最近自发发言记录，用于硬去重
        self._recently_spoken: list = []  # 最多保留 10 条

        # 注册事件处理器
        self._setup_event_handlers()

        # 初始化 SilenceGate
        self._silence_gate = SilenceGate(
            llm=self.llm,
            short_term_provider=lambda: self.memory_core.short_term_history[-12:] if self.memory_core.short_term_history else []
        )

        print(f"[SpontaneousEngine] 引擎初始化完成，检查间隔: {self.check_interval}秒, "
              f"用户类型: {self.user_profile.profile_type}")

    def _setup_event_handlers(self):
        """设置事件处理器"""
        # 用户活动事件（来自ASR或文本输入）
        @event_handler(EventType.USER_INPUT_RECEIVED)
        def on_user_message(event: Event):
            self.on_user_activity(event.data.get("text", ""))

        # 本能触发事件（可选的触发源）
        @event_handler(EventType.INSTINCT_TRIGGERED)
        def on_instinct(event: Event):
            self.on_instinct_triggered(event.data)

        print("[SpontaneousEngine] 事件处理器已注册")

    def set_speech_callback(self, callback: Callable[[str, Dict[str, Any]], None]):
        """设置发言回调函数（用于实际输出发言）"""
        self.speech_callback = callback
        print("[SpontaneousEngine] 发言回调已设置")

    def on_user_activity(self, user_input: str = ""):
        """用户活动回调（ASR或文本输入）"""
        self.trigger_policy.update_user_activity()
        self.freq_limiter.reset_reject_multiplier()

        # SilenceGate 检测关键词 + 更新状态
        if self._silence_gate:
            self._silence_gate.on_user_activity(user_input)

        # 检测话题枯竭信号
        if user_input and detect_short_reply(user_input):
            self._push_internal_event("topic_exhausted", 0.3, "用户连续短回复，话题可能枯竭")

        # 如果有待追踪的主动发言，记录用户响应
        if user_input and self.response_tracker.last_spontaneous_time > 0:
            time_to_respond = time.time() - self.response_tracker.last_spontaneous_time
            response_type = self.response_tracker.record_response(user_input, time_to_respond)
            self._adjust_based_on_response(response_type)

        print(f"[SpontaneousEngine] 用户活动: '{user_input[:30]}...'")

    def on_instinct_triggered(self, instinct_data: Dict[str, Any]):
        """本能触发回调（可选）"""
        # 本能触发可以作为主动发言的补充触发源
        urge_type = instinct_data.get("urge_type", "")
        comfort_level = instinct_data.get("comfort_level", 0)

        if urge_type == "initiative" and comfort_level > 0.7:
            # 舒适度高且有主动欲望，可以增加触发概率
            print(f"[SpontaneousEngine] 本能触发: {urge_type}, 舒适度: {comfort_level}")
            # 这里可以调整触发策略，例如临时提高触发概率

    def on_ai_spoke(self, text: str):
        """AI发言回调（用于记录发言时间，不记录频率限制）"""
        self.trigger_policy.update_spoke()

        # 如果是主动发言，记录下来
        if hasattr(self, '_last_was_spontaneous') and self._last_was_spontaneous:
            context = self._last_spontaneous_context or {}
            self.response_tracker.record_spontaneous(text, context)
            self._last_was_spontaneous = False
            self._last_spontaneous_context = None

        print(f"[SpontaneousEngine] AI发言记录: '{text[:30]}...'")

    def _adjust_based_on_response(self, response_type: ResponseType):
        """基于用户响应调整策略"""
        if response_type == ResponseType.POSITIVE:
            # 正面响应，保持或略微增加频率
            print("[SpontaneousEngine] 正面响应，策略保持")
        elif response_type == ResponseType.NEGATIVE:
            # 负面响应，减少频率
            print("[SpontaneousEngine] 负面响应，减少主动频率")
            self.freq_limiter.record_reject("负面响应")
        elif response_type == ResponseType.IGNORE:
            # 无视，适当减少频率
            print("[SpontaneousEngine] 用户无视，适当减少频率")
            self.freq_limiter.record_reject("用户无视")
        # 中性响应不需要特殊调整

    # ─── 用户画像 ───

    def _load_user_profile(self):
        """加载用户画像配置"""
        base_dir = Path(__file__).parent.parent.parent
        default_spon = {
            "check_interval": config.SPONTANEOUS_CHECK_INTERVAL,
            "max_per_hour": config.SPONTANEOUS_MAX_PER_HOUR,
            "max_per_day": config.SPONTANEOUS_MAX_PER_DAY,
            "min_interval": config.SPONTANEOUS_MIN_INTERVAL,
            "night_start": config.SPONTANEOUS_NIGHT_START,
            "night_end": config.SPONTANEOUS_NIGHT_END,
        }
        profiles = load_profiles_dict(PRESET_PROFILES_PATH)
        user_config = self._read_user_engagement_config()
        self.user_profile = EngagementProfile.create_from_config(user_config, default_spon, profiles)
        self._apply_profile_to_components()

    def _read_user_engagement_config(self) -> dict:
        config_path = Path(__file__).parent.parent.parent / "agent_memory" / "spontaneous" / "engagement.json"
        try:
            if config_path.exists():
                return json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {"mode": "auto", "profile_type": "normal"}

    def _apply_profile_to_components(self):
        p = self.user_profile.parameters
        self.check_interval = p.check_interval
        self.freq_limiter.apply_parameters(p)

    # ─── 追问与冷场恢复 ───

    async def _try_daily_greeting(self):
        today = time.strftime("%Y-%m-%d")
        if self._last_daily_greet_date == today:
            return
        hour = time.localtime().tm_hour
        if hour in (8, 20):
            greeting = "早安～" if hour == 8 else "晚安，早点休息～"
            try:
                ctx = {"source": "daily_greeting", "priority": 1, "emotion": "neutral",
                       "action": "", "time": datetime.now().strftime("%H:%M:%S")}
                if self.speech_callback:
                    self.speech_callback(greeting, ctx)
                    self._last_daily_greet_date = today
            except Exception:
                pass

    # ─── 自动推断 ───

    async def _auto_update_profile(self):
        if self.user_profile.mode != "auto" or not self.engagement_analyzer:
            return
        now = time.time()
        if now - self.engagement_analyzer.last_inference_time < 21600:
            return
        inferred = self.engagement_analyzer.infer_type()
        self._inference_history.append(inferred)
        if len(self._inference_history) > 3:
            self._inference_history.pop(0)
        if len(set(self._inference_history)) == 1 and len(self._inference_history) >= 3:
            if inferred != self.user_profile.profile_type:
                base_dir = Path(__file__).parent.parent.parent
                default_spon = {
                    "check_interval": config.SPONTANEOUS_CHECK_INTERVAL,
                    "max_per_hour": config.SPONTANEOUS_MAX_PER_HOUR,
                    "max_per_day": config.SPONTANEOUS_MAX_PER_DAY,
                    "min_interval": config.SPONTANEOUS_MIN_INTERVAL,
                    "night_start": config.SPONTANEOUS_NIGHT_START,
                    "night_end": config.SPONTANEOUS_NIGHT_END,
                }
                profiles = load_profiles_dict(PRESET_PROFILES_PATH)
                self.user_profile.apply_preset(inferred, default_spon, profiles)
                self._apply_profile_to_components()
                print(f"[SpontaneousEngine] 自动切换用户类型: → {inferred}")
        self.engagement_analyzer.last_inference_time = now

    # ─── 主循环 ───

    async def _main_loop(self):
        """主循环：事件驱动 + 语境门控"""
        print(f"[SpontaneousEngine] 主循环启动，间隔: {self.check_interval}秒")

        while self.is_running:
            try:
                # 视觉观察 tick（独立于触发逻辑，混合节奏）
                if self._visual_observer:
                    silence = time.time() - max(
                        self.trigger_policy.last_user_activity,
                        self.trigger_policy.last_spoke_time
                    )
                    await self._visual_observer.tick(silence)

                if self.user_profile.parameters.allow_spontaneous:
                    await self._check_and_trigger()

                # 每日问候（独立于触发逻辑）
                await self._try_daily_greeting()

                # 情绪基线回归
                if self.trigger_policy._emotion_engine:
                    self.trigger_policy._emotion_engine.drift()

                # 自动推断更新
                await self._auto_update_profile()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[SpontaneousEngine] 主循环错误: {e}")
                await asyncio.sleep(5)

        print("[SpontaneousEngine] 主循环结束")

    async def _check_and_trigger(self):
        """事件驱动触发检测：内部事件 → 触发信号 → 语境门控 → 频率限制 → 内容生成"""
        now = time.time()

        # 控制检查频率
        if now - self.last_check_time < self.check_interval:
            return

        self.last_check_time = now
        self._loop_ticks += 1

        # 心跳日志
        if self._loop_ticks % 10 == 0:
            silence = time.time() - max(
                self.trigger_policy.last_user_activity,
                self.trigger_policy.last_spoke_time
            )
            print(f"[SpontaneousEngine] 心跳 #{self._loop_ticks}: 沉默 {silence:.0f}s")

        # 1. 收集内部事件
        events = self._collect_internal_events()

        # 2. 触发策略：汇总信号（确定性，不掷骰子）
        context = self.context_reader.build_context_summary()
        has_goal = bool(self.goal_tracker and self.goal_tracker.get_best_goal())
        short_term_count = context.get("short_term_count", 0)
        trigger_result = self.trigger_policy.evaluate(
            context,
            has_goal=has_goal,
            short_term_count=short_term_count,
        )

        # 3. 语境门控：即使有触发信号，也需要语境允许
        if self._silence_gate:
            silence_duration = trigger_result.get("silence_duration", 0)
            emotion_type = trigger_result.get("details", {}).get("emotion_type", 0)
            hour = time.localtime().tm_hour

            gate_result = self._silence_gate.check(
                events=events,
                silence_duration=silence_duration,
                short_term_count=short_term_count,
                emotion_type=emotion_type,
                hour=hour,
            )

            if gate_result.decision != Decision.SPEAK:
                if gate_result.decision == Decision.WAIT and gate_result.wait_seconds > 0:
                    # 延长检查间隔
                    self.last_check_time = now + gate_result.wait_seconds - self.check_interval
                elif gate_result.decision in (Decision.SILENCE, Decision.SILENCE_LONG):
                    # 静默时退避：避免无意义的短间隔重检
                    backoff = 120 if gate_result.decision == Decision.SILENCE else 300
                    self.last_check_time = now + backoff - self.check_interval
                print(f"[SpontaneousEngine] 语境门控阻止: {gate_result.decision.value} - {gate_result.reason}")
                return

        # 5. 主动搜索记忆，给内容生成提供真实话题材料
        memory_cards = []
        if self.context_reader:
            try:
                topics = context.get("recent_topics", [])
                keywords = [t[:15] for t in topics[:3]] if topics else []
                memory_cards = self.context_reader.search_relevant_memories(keywords, limit=5)
                if memory_cards:
                    print(f"[SpontaneousEngine] 记忆检索到 {len(memory_cards)} 张相关卡片")
            except Exception as e:
                print(f"[SpontaneousEngine] 记忆检索异常: {e}")
        context["memory_cards"] = memory_cards

        # 视觉观察上下文注入
        if self._visual_observer and self._visual_observer.last_description:
            context["visual_observation"] = self._visual_observer.last_description

        # 6. 生成内容：优先目标驱动（有目标时不必等高层触发）
        content_result = None

        if self.goal_tracker:
            best_goal = self.goal_tracker.get_best_goal()
            if best_goal:
                print(f"[SpontaneousEngine] 尝试目标驱动发言: {best_goal[:60]}...")
                goal_text = await self.content_generator.generate_from_goal(best_goal, context)
                if goal_text:
                    content_result = {
                        "text": goal_text,
                        "source": "goal_driven",
                        "emotion": "neutral",
                        "action": "",
                        "priority": trigger_result["priority"]
                    }

        if content_result is None:
            use_llm = trigger_result["priority"] >= 4
            content_result = await self.content_generator.generate(
                {**context, "trigger_info": trigger_result},
                use_llm=use_llm
            )

        if not content_result["text"]:
            print("[SpontaneousEngine] 内容生成失败")
            return

        # 7. 去重：与最近发言的公共子串 >= 一半 → 丢弃
        text = content_result["text"]
        for prev in self._recently_spoken[-5:]:
            common = _longest_common_substring(text, prev)
            if len(common) >= min(len(text), len(prev)) * 0.5:
                print(f"[SpontaneousEngine] 丢弃重复发言: '{text}' (与 '{prev}' 公共子串 '{common}')")
                return

        # 记录
        self._recently_spoken.append(text)
        if len(self._recently_spoken) > 10:
            self._recently_spoken.pop(0)

        # 8. 发言
        speech_context = {
            "source": content_result["source"],
            "priority": trigger_result["priority"],
            "trigger_reason": trigger_result.get("trigger_reason", ""),
            "silence_duration": trigger_result.get("silence_duration", 0),
            "emotion": content_result.get("emotion", "neutral"),
            "action": content_result.get("action", ""),
            "time": datetime.now().strftime("%H:%M:%S")
        }

        self._last_was_spontaneous = True
        self._last_spontaneous_context = {
            **trigger_result,
            **content_result,
            "time_context": context.get("time_context", {})
        }

        print(f"[SpontaneousEngine] 触发主动发言:")
        print(f"  内容: '{content_result['text']}'")
        print(f"  来源: {content_result['source']}, 优先级: {trigger_result['priority']}")
        print(f"  触发原因: {trigger_result.get('trigger_reason', 'N/A')}")
        print(f"  沉默时长: {trigger_result.get('silence_duration', 0):.1f}秒")

        if self.speech_callback:
            self.speech_callback(content_result["text"], speech_context)
            self.freq_limiter.record_spoke()
        else:
            print("[SpontaneousEngine] 警告: 未设置发言回调")

    # ─── 内部事件收集 ───

    def _push_internal_event(self, event_type: str, strength: float, summary: str = "", data: dict = None):
        """添加内部事件到队列"""
        event = InternalEvent(type=event_type, strength=strength, summary=summary, data=data or {})
        self._internal_events.append(event)

    def _collect_internal_events(self) -> List[InternalEvent]:
        """收集并清空内部事件队列"""
        events = self._internal_events[:]
        self._internal_events.clear()

        # 沉默本身就是一个事件：沉默越久，强度越高
        silence = time.time() - max(
            self.trigger_policy.last_user_activity,
            self.trigger_policy.last_spoke_time
        )
        if silence >= 300:  # 5 分钟以上沉默产生事件
            silence_strength = min(silence / 3600, 1.0)  # 1 小时封顶
            events.append(InternalEvent(
                type="prolonged_silence",
                strength=silence_strength,
                summary=f"用户已沉默 {silence/60:.0f} 分钟"
            ))

        # 检查 GoalTracker 是否有活跃目标
        if self.goal_tracker:
            best_goal = self.goal_tracker.get_best_goal()
            if best_goal:
                events.append(InternalEvent(
                    type="goal_updated",
                    strength=0.5,
                    summary=best_goal[:60]
                ))

        # 检查是否刚创建了重要卡片（从 response_tracker 推断）
        if self.response_tracker.last_spontaneous_time > 0:
            recent_stats = self.response_tracker.get_recent_stats(1)
            if recent_stats.get("positive_ratio", 0) > 0.5:
                events.append(InternalEvent(
                    type="positive_interaction",
                    strength=0.4,
                    summary="刚才的互动看起来不错"
                ))

        return events

    def start(self):
        """启动引擎"""
        if self.is_running:
            print("[SpontaneousEngine] 引擎已在运行中")
            return

        self.is_running = True

        # 创建异步任务
        loop = asyncio.get_event_loop()
        self.loop_task = loop.create_task(self._main_loop())

        print("[SpontaneousEngine] 引擎已启动")

    def stop(self):
        """停止引擎"""
        if not self.is_running:
            print("[SpontaneousEngine] 引擎未在运行")
            return

        self.is_running = False

        if self.loop_task and not self.loop_task.done():
            self.loop_task.cancel()

        print("[SpontaneousEngine] 引擎已停止")

    def get_status(self) -> Dict[str, Any]:
        """获取引擎状态"""
        now = time.time()
        silence_duration = now - max(
            self.trigger_policy.last_user_activity,
            self.trigger_policy.last_spoke_time
        )

        freq_status = self.freq_limiter.get_status()
        recent_stats = self.response_tracker.get_recent_stats(6)
        insights = self.response_tracker.get_insights()

        return {
            "is_running": self.is_running,
            "silence_duration": silence_duration,
            "check_interval": self.check_interval,
            "last_check_ago": now - self.last_check_time if self.last_check_time > 0 else None,
            "has_speech_callback": self.speech_callback is not None,
            "frequency_status": freq_status,
            "recent_stats": recent_stats,
            "insights": insights,
            "components": {
                "context_reader": "active",
                "trigger_policy": "active",
                "content_generator": "active",
                "freq_limiter": "active",
                "response_tracker": "active",
                "interrupt_handler": "active" if self.interrupt_handler else "inactive"
            }
        }

    async def manual_trigger_async(self) -> bool:
        """
        手动触发主动发言（异步版，在已有事件循环中调用）

        Returns:
            bool: 是否成功触发
        """
        print("[SpontaneousEngine] 手动触发主动发言 (async)")

        context = self.context_reader.build_context_summary()
        trigger_result = {
            "should_trigger": True,
            "silence_duration": self.trigger_policy._calculate_silence_duration(),
            "trigger_reason": "manual_trigger",
            "priority": 5,
            "details": {"manual": True}
        }

        content_result = await self.content_generator.generate(
            {**context, "trigger_info": trigger_result},
            use_llm=True
        )

        if not content_result["text"]:
            print("[SpontaneousEngine] 手动触发内容生成失败")
            return False

        speech_context = {
            "source": "manual",
            "priority": 5,
            "trigger_reason": "manual_trigger",
            "silence_duration": trigger_result["silence_duration"],
            "emotion": content_result.get("emotion", "neutral"),
            "action": content_result.get("action", ""),
            "time": datetime.now().strftime("%H:%M:%S")
        }

        if self.speech_callback:
            self.speech_callback(content_result["text"], speech_context)
            # 不记录 freq_limiter，避免测试用的 /trigger 消耗频率配额
            return True
        else:
            print("[SpontaneousEngine] 手动触发失败: 未设置发言回调")
            return False

    def manual_trigger(self) -> bool:
        """
        手动触发主动发言（同步版，用于测试或特殊场景）
        在线程中运行，创建新事件循环执行异步逻辑。
        """
        print("[SpontaneousEngine] 手动触发主动发言")

        def _run():
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(self.manual_trigger_async())
            finally:
                loop.close()

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run)
            try:
                return future.result(timeout=30)
            except concurrent.futures.TimeoutError:
                print("[SpontaneousEngine] 手动触发超时")
                return False