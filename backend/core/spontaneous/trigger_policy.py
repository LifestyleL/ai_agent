"""
触发策略 V5.0：情绪驱动的多层触发系统
- 替代旧版单一沉默阈值 + 随机概率，改用 4 层窗口评估
- 4 层触发：对话延续 → 情绪冲动 → 目标驱动 → 冷场填补
- 情绪状态调制所有层的概率和内容风格
"""

import time
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import config


class TriggerPolicy:
    """V5.0 情绪感知的多层主动发言触发策略"""

    def __init__(self, emotion_engine=None):
        self.last_user_activity = time.time()
        self.last_spoke_time = 0
        self.conversation_lull_start = None
        self.trigger_history: list = []
        self._emotion_engine = emotion_engine  # EmotionEngine 引用

        # 从配置读取各层窗口
        self.window_continuation = getattr(config, 'SPONTANEOUS_WINDOW_CONTINUATION', (8, 30))
        self.window_emotional = getattr(config, 'SPONTANEOUS_WINDOW_EMOTIONAL', (30, 120))
        self.window_goal = getattr(config, 'SPONTANEOUS_WINDOW_GOAL', (60, 900))
        self.window_silence = getattr(config, 'SPONTANEOUS_MIN_SILENCE', 300)

    # ─── 公共 API ───

    def update_user_activity(self):
        self.last_user_activity = time.time()
        self.conversation_lull_start = None

    def update_spoke(self):
        self.last_spoke_time = time.time()

    def _calculate_silence_duration(self) -> float:
        return time.time() - max(self.last_user_activity, self.last_spoke_time)

    # ─── 情绪读取 ───

    def _get_emotion(self) -> Tuple[int, float]:
        """返回 (type, strength)，无引擎时默认 neutral/0"""
        if self._emotion_engine:
            return self._emotion_engine.get_emotion()
        return 0, 0.0

    # ─── 核心评估 ───

    def evaluate(self, context: Dict[str, Any],
                 has_goal: bool = False,
                 short_term_count: int = 0) -> Dict[str, Any]:
        """
        多层评估是否触发主动发言。
        context 包含 context_reader 的输出（topic / time 等）。
        """
        silence = self._calculate_silence_duration()
        emotion_type, emotion_strength = self._get_emotion()
        now = datetime.now()
        hour = now.hour

        # ── 深夜抑制 ──
        night_start = getattr(config, 'SPONTANEOUS_NIGHT_START', 2)
        night_end = getattr(config, 'SPONTANEOUS_NIGHT_END', 5)
        is_night = night_start <= hour < night_end

        result = {
            "should_trigger": False,
            "silence_duration": silence,
            "trigger_reason": "",
            "priority": 0,
            "trigger_layer": "",
            "details": {
                "emotion_type": emotion_type,
                "emotion_strength": emotion_strength,
                "silence": silence,
                "hour": hour,
                "is_night": is_night,
            }
        }

        # ── 深夜一律不触发 ──
        if is_night:
            return result

        # ── 按层级评估（从高优先级到低） ──

        # Layer 1: 对话延续（8-30s）
        if self._evaluate_layer_continuation(silence, emotion_type, emotion_strength, short_term_count):
            result["should_trigger"] = True
            result["trigger_layer"] = "continuation"
            result["trigger_reason"] = "对话自然延续"
            result["priority"] = 5

        # Layer 2: 情绪冲动（30-120s）—— 情绪越强越容易触发
        elif self._evaluate_layer_emotional(silence, emotion_type, emotion_strength):
            result["should_trigger"] = True
            result["trigger_layer"] = "emotional"
            labels = {0: "平静", 1: "开心想说话", 2: "有点担心", 3: "烦躁想吐槽"}
            result["trigger_reason"] = f"情绪驱动: {labels.get(emotion_type, 'unknown')}"
            result["priority"] = 4

        # Layer 3: 目标驱动（60-300s）
        elif has_goal and self._evaluate_layer_goal(silence, emotion_strength):
            result["should_trigger"] = True
            result["trigger_layer"] = "goal_driven"
            result["trigger_reason"] = "想聊聊之前的话题"
            result["priority"] = 3

        # Layer 4: 冷场填补（300s+）
        elif silence >= self.window_silence and self._cold_silence_probability(silence, emotion_type):
            result["should_trigger"] = True
            result["trigger_layer"] = "cold_silence"
            result["trigger_reason"] = f"沉默{silence:.0f}秒，打破冷场"
            result["priority"] = 2

        if result["should_trigger"]:
            # 深夜不触发已在上面处理，这里无需重复
            self._record(result)
            print(f"[TriggerPolicy V5.0] 评估通过: {result['trigger_reason']} "
                  f"(层: {result['trigger_layer']}, 优先级: {result['priority']}, "
                  f"情绪: {emotion_type}/{emotion_strength:.1f})")

        return result

    # ─── 各层评估逻辑 ───

    def _evaluate_layer_continuation(self, silence: float, etype: int, estrength: float,
                                     short_term_count: int) -> bool:
        """Layer 1: 对话延续 —— 有对话内容且在时间窗口内"""
        low, high = self.window_continuation
        if silence < low or silence > high:
            return False
        # 确定性：必须有至少 3 轮对话内容才考虑延续
        return short_term_count >= 3

    def _evaluate_layer_emotional(self, silence: float, etype: int, estrength: float) -> bool:
        """Layer 2: 情绪冲动 —— 情绪显著波动且非平静"""
        low, high = self.window_emotional
        if silence < low or silence > high:
            return False
        # 确定性：情绪强度 ≥ 5 才可能触发（有明显情绪）
        if estrength < 5.0:
            return False
        # 平静情绪不触发（没话想说）
        if etype == 0:
            return False
        return True

    def _evaluate_layer_goal(self, silence: float, estrength: float) -> bool:
        """Layer 3: 目标驱动 —— 有 goal 且在时间窗口内"""
        low, high = self.window_goal
        if silence < low or silence > high:
            return False
        # 确定性：有 goal 就触发（has_goal 已在 evaluate 层判断）
        return True

    def _cold_silence_probability(self, silence: float, etype: int) -> bool:
        """Layer 4: 冷场填补 —— 沉默超过窗口阈值"""
        return silence >= self.window_silence

    # ─── 记录 ───

    def _record(self, result: Dict[str, Any]):
        self.trigger_history.append({
            "timestamp": time.time(),
            **{k: v for k, v in result.items() if k != "details"},
            **result["details"],
        })
        if len(self.trigger_history) > 50:
            self.trigger_history.pop(0)
