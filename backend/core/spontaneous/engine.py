"""
自驱动引擎主模块：协调各组件，实现用户沉默时的主动发言
"""

import asyncio
import time
import random
import threading
from typing import Optional, Dict, Any, Callable
from datetime import datetime

from .context_reader import ContextReader
from .trigger_policy import TriggerPolicy
from .content_generator import ContentGenerator
from .freq_limiter import FreqLimiter
from .response_tracker import ResponseTracker, ResponseType
from .interrupt_handler import InterruptHandler, InterruptType

from ..memory.memory_core import MemoryCore
from ..event.event_bus import event_bus, EventType, Event, event_handler
import config

class SpontaneousEngine:
    """自驱动引擎主类"""

    def __init__(self, memory_core: MemoryCore, llm=None, goal_tracker=None):
        self.memory_core = memory_core
        self.llm = llm
        self.goal_tracker = goal_tracker  # GoalTracker 实例（可选）

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

        # 连续发言状态
        self._consecutive_count = 0
        self._consecutive_active = False
        self._consecutive_max = config.SPONTANEOUS_CONSECUTIVE_MAX
        self._consecutive_stop_prob = config.SPONTANEOUS_CONSECUTIVE_STOP_PROB

        # 回调函数
        self.speech_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None

        # 心跳日志计数器
        self._loop_ticks = 0

        # 注册事件处理器
        self._setup_event_handlers()

        print(f"[SpontaneousEngine] 引擎初始化完成，检查间隔: {self.check_interval}秒")

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

    def _calc_backoff_delay(self) -> float:
        """
        指数回退延迟：连续发言时，每次延迟指数增长+随机抖动

        第0次: random(0, 1)
        第1次: random(1, 10)
        第2次: random(10, 60)
        第3次: random(60, 180)
        第4次+: random(60, 180)  # 封顶
        """
        tiers = [
            (0, 1),     # 第0次：试探性，很快
            (1, 10),    # 第1次：稍微等一下
            (10, 60),   # 第2次：想想再说
            (60, 180),  # 第3次+：封顶
        ]
        idx = min(self._consecutive_count, len(tiers) - 1)
        low, high = tiers[idx]
        return random.uniform(low, high)

    def _should_continue(self) -> bool:
        """
        判断是否继续连续发言，概率递减
        第0次后: 100% 继续（刚触发，至少说一句）
        第1次后: 70% 继续
        第2次后: 49% 继续
        第3次后: 34% 继续
        或者达到最大次数 → 停止
        """
        if self._consecutive_count >= self._consecutive_max:
            return False
        if self._consecutive_count == 0:
            return True  # 触发后至少说一句

        stop_prob = self._consecutive_stop_prob * self._consecutive_count
        return random.random() > stop_prob

    def _end_consecutive(self):
        """结束连续发言，重置状态"""
        self._consecutive_active = False
        self._consecutive_count = 0
        self.trigger_policy.update_user_activity()  # 重置沉默计时（模拟用户活动）
        print("[SpontaneousEngine] [连续发言] 状态重置")

    def on_user_activity(self, user_input: str = ""):
        """用户活动回调（ASR或文本输入）"""
        # 如果处于连续发言模式，立即打断
        if self._consecutive_active:
            print("[SpontaneousEngine] [连续发言] 用户打断，立即停止")
            self._end_consecutive()

        self.trigger_policy.update_user_activity()

        # 如果有待追踪的主动发言，记录用户响应
        if user_input and self.response_tracker.last_spontaneous_time > 0:
            time_to_respond = time.time() - self.response_tracker.last_spontaneous_time
            response_type = self.response_tracker.record_response(user_input, time_to_respond)

            # 基于响应类型调整策略
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

    async def _main_loop(self):
        """主循环"""
        print(f"[SpontaneousEngine] 主循环启动，间隔: {self.check_interval}秒")

        while self.is_running:
            try:
                # === 情况A：连续发言模式 ===
                if self._consecutive_active:
                    delay = self._calc_backoff_delay()
                    print(f"[SpontaneousEngine] [连续发言] 第{self._consecutive_count}次，等待 {delay:.1f}s 后决定是否继续")
                    await asyncio.sleep(delay)

                    if self._should_continue():
                        # 生成下一句
                        success = await self._generate_and_speak_consecutive()
                        if success:
                            self._consecutive_count += 1
                        else:
                            self._end_consecutive()
                    else:
                        print(f"[SpontaneousEngine] [连续发言] 自然结束，共发言 {self._consecutive_count} 次")
                        self._end_consecutive()
                    continue

                # === 情况B：正常沉默检测 ===
                await self._check_and_trigger()
                # 情绪基线回归：每次循环温和地向 neutral 靠近
                if self.trigger_policy._emotion_engine:
                    self.trigger_policy._emotion_engine.drift()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[SpontaneousEngine] 主循环错误: {e}")
                await asyncio.sleep(5)  # 错误后等待5秒

        print("[SpontaneousEngine] 主循环结束")

    async def _check_and_trigger(self):
        """检查并触发主动发言"""
        # 如果处于连续发言模式，跳过正常检测
        if self._consecutive_active:
            return

        now = time.time()

        # 控制检查频率
        if now - self.last_check_time < self.check_interval:
            return

        self.last_check_time = now
        self._loop_ticks += 1

        # 每10次检查打印心跳
        if self._loop_ticks % 10 == 0:
            silence = time.time() - max(
                self.trigger_policy.last_user_activity,
                self.trigger_policy.last_spoke_time
            )
            print(f"[SpontaneousEngine] 心跳 #{self._loop_ticks}: 沉默 {silence:.0f}s, "
                  f"触发阈值 {self.trigger_policy.window_silence}s")

        # 1. 读取上下文
        context = self.context_reader.build_context_summary()

        # 2. 检查触发策略（V5.0 情绪感知多层触发）
        has_goal = bool(self.goal_tracker and self.goal_tracker.get_best_goal())
        short_term_count = context.get("short_term_count", 0)
        trigger_result = self.trigger_policy.evaluate(
            context,
            has_goal=has_goal,
            short_term_count=short_term_count,
        )

        if not trigger_result["should_trigger"]:
            return

        # 3. 检查频率限制
        freq_check = self.freq_limiter.check(trigger_result["priority"])

        if not freq_check["allowed"]:
            print(f"[SpontaneousEngine] 频率限制阻止发言: {', '.join(freq_check['reasons'])}")
            return

        # 4. 生成内容（优先使用 GoalTracker 目标驱动）
        content_result = None

        if self.goal_tracker and trigger_result["priority"] >= 3:
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
            use_llm = trigger_result["priority"] >= 4  # 高优先级使用LLM
            content_result = await self.content_generator.generate(
                {**context, "trigger_info": trigger_result},
                use_llm=use_llm
            )

        if not content_result["text"]:
            print("[SpontaneousEngine] 内容生成失败")
            return

        # 5. 准备发言上下文
        speech_context = {
            "source": content_result["source"],
            "priority": trigger_result["priority"],
            "trigger_reason": trigger_result.get("trigger_reason", ""),
            "silence_duration": trigger_result.get("silence_duration", 0),
            "emotion": content_result.get("emotion", "neutral"),
            "action": content_result.get("action", ""),
            "time": datetime.now().strftime("%H:%M:%S")
        }

        # 6. 标记为主动发言并调用回调
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
            # 记录自驱动发言频率
            self.freq_limiter.record_spoke()
            # 触发连续发言模式
            self._consecutive_active = True
            self._consecutive_count = 1
            print(f"[SpontaneousEngine] 进入连续发言模式，当前计数: {self._consecutive_count}")
        else:
            print("[SpontaneousEngine] 警告: 未设置发言回调")

    async def _generate_and_speak_consecutive(self) -> bool:
        """
        连续发言模式下生成并说出一句话
        Returns: 是否成功发言
        """
        # 1. 读取上下文
        context = self.context_reader.build_context_summary()

        # 2. 检查频率限制（使用中等优先级3）
        freq_check = self.freq_limiter.check(priority=3)
        if not freq_check["allowed"]:
            print(f"[SpontaneousEngine] [连续发言] 频率限制阻止发言: {', '.join(freq_check['reasons'])}")
            return False

        # 3. 生成内容（根据连续次数调整）
        use_llm = False  # 连续发言不使用LLM，保持轻量
        # 构建触发信息模拟
        trigger_result = {
            "should_trigger": True,
            "silence_duration": self.trigger_policy._calculate_silence_duration(),
            "trigger_reason": f"consecutive_{self._consecutive_count}",
            "priority": 3,
            "details": {"consecutive": True}
        }

        content_result = await self.content_generator.generate(
            {**context, "trigger_info": trigger_result},
            use_llm=use_llm
        )

        if not content_result["text"]:
            print("[SpontaneousEngine] [连续发言] 内容生成失败")
            return False

        # 4. 准备发言上下文
        speech_context = {
            "source": content_result["source"] + "_consecutive",
            "priority": 3,
            "trigger_reason": f"连续发言第{self._consecutive_count}次",
            "silence_duration": trigger_result["silence_duration"],
            "emotion": content_result.get("emotion", "neutral"),
            "action": content_result.get("action", ""),
            "time": datetime.now().strftime("%H:%M:%S")
        }

        # 6. 标记为主动发言并调用回调
        self._last_was_spontaneous = True
        self._last_spontaneous_context = {
            **trigger_result,
            **content_result,
            "time_context": context.get("time_context", {})
        }

        print(f"[SpontaneousEngine] [连续发言] 第{self._consecutive_count}次发言:")
        print(f"  内容: '{content_result['text']}'")
        print(f"  来源: {content_result['source']}")

        if self.speech_callback:
            self.speech_callback(content_result["text"], speech_context)
            # 记录自驱动发言频率
            self.freq_limiter.record_spoke()
            return True
        else:
            print("[SpontaneousEngine] [连续发言] 警告: 未设置发言回调")
            return False

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