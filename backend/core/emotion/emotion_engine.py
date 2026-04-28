"""
极简情绪缓动引擎
维护情绪类型 (0-3) 和强度 (0-10)，实现平滑过渡和自然衰减
参数从 config 全局配置读取
"""
import config


class EmotionEngine:
    def __init__(self, initial_type: int = None, initial_strength: float = None):
        if initial_type is None:
            initial_type = 0
        if initial_strength is None:
            initial_strength = 0.0
        self.type = max(0, min(3, initial_type))
        self.strength = max(0.0, min(10.0, initial_strength))
        # 从配置读取算法参数
        self.smoothing = config.EMOTION_SMOOTHING_FACTOR
        self.decay = config.EMOTION_DECAY_FACTOR
        self.switch_threshold = config.EMOTION_SWITCH_THRESHOLD

    def update_emotion(self, new_type: int, new_strength: float) -> None:
        """更新情绪状态，应用平滑、阈值切换和自然衰减"""
        # 1. 强度平滑
        self.strength = self.smoothing * self.strength + (1 - self.smoothing) * new_strength

        # 2. 类型切换阈值
        if abs(new_type - self.type) >= self.switch_threshold:
            self.type = new_type

        # 3. 自然衰减
        self.strength *= self.decay

        # 确保数值在有效范围内
        self.strength = max(0.0, min(10.0, self.strength))
        self.type = max(0, min(3, self.type))

    def get_emotion(self) -> tuple[int, float]:
        """
        获取当前情绪状态
        :return: (情绪类型, 情绪强度)
        """
        return self.type, round(self.strength, 2)

    def get_emotion_dict(self) -> dict:
        """
        获取当前情绪状态的字典表示
        :return: {"type": int, "strength": float}
        """
        return {"type": self.type, "strength": round(self.strength, 2)}

    def infer_from_text(self, text: str) -> tuple[int, float]:
        """
        从用户文本推断情绪类型和强度（纯关键词规则，0延迟）
        返回 (type, strength) 供 update_emotion() 使用
        """
        type_scores = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0}

        # 开心/兴奋 (type=1)
        happy_words = ["哈哈", "嘿嘿", "开心", "高兴", "太好了", "nice", "棒", "喜欢",
                       "不错", "好耶", "耶", "233", "笑死", "好玩", "有趣", "快乐"]
        for w in happy_words:
            if w in text:
                type_scores[1] += 2.0

        # 难过/低落 (type=2)
        sad_words = ["难过", "伤心", "哭", "难受", "郁闷", "烦", "累死了", "好累",
                     "不开心", "低落", "失恋", "分手", "失败", "唉", "压力"]
        for w in sad_words:
            if w in text:
                type_scores[2] += 2.0

        # 生气/烦躁 (type=3)
        angry_words = ["气死", "愤怒", "生气", "恶心", "无语", "讨厌", "烦死了",
                       "滚", "操", "tm", "tmd", "傻逼", "sb", "垃圾"]
        for w in angry_words:
            if w in text:
                type_scores[3] += 2.5

        # 找最高分
        best_type = max(type_scores, key=type_scores.get)
        best_score = type_scores[best_type]

        if best_score == 0:
            return 0, 0.0  # 无情绪信号，保持中性

        # 强度 = 1 + 分数/4 (范围 1-5)
        strength = min(5.0, 1.0 + best_score / 2.0)
        return best_type, strength

    @staticmethod
    def type_to_label(etype: int) -> str:
        """情绪类型 → TTS 标签"""
        mapping = {0: "neutral", 1: "happy", 2: "sad", 3: "angry"}
        return mapping.get(etype, "neutral")

    def drift(self) -> None:
        """基线回归：每次调用温和地向 neutral(type=0, strength=0.5) 靠近一步"""
        # 类型回归（每步概率推进）
        if self.type > 0 and self.strength < 3.0:
            # 低强度时加速类型回归
            self.type = max(0, self.type - 1) if self.strength < 1.5 else self.type
        # 强度回归：向基线 0.5 靠近
        if self.strength > 0.5:
            self.strength -= 0.05  # 每步减 0.05，30步（~30分钟）回到基线
        elif self.strength < 0.5:
            self.strength = min(0.5, self.strength + 0.05)
        self.strength = max(0.0, min(10.0, self.strength))

    def reset(self, new_type: int = 0, new_strength: float = 0.0) -> None:
        """重置情绪状态"""
        self.type = max(0, min(3, new_type))
        self.strength = max(0.0, min(10.0, new_strength))