"""
极简情绪缓动引擎
维护情绪类型 (0-3) 和强度 (0-10)，实现平滑过渡和自然衰减
"""

class EmotionEngine:
    def __init__(self, initial_type: int = 0, initial_strength: float = 0.0):
        """
        初始化情绪引擎
        :param initial_type: 初始情绪类型 (0-3)，默认为0（中性）
        :param initial_strength: 初始情绪强度 (0-10)，默认为0
        """
        self.type = max(0, min(3, initial_type))
        self.strength = max(0.0, min(10.0, initial_strength))

    def update_emotion(self, new_type: int, new_strength: float) -> None:
        """
        更新情绪状态，应用平滑、阈值切换和自然衰减
        严格按照三行核心算法：
        1. 强度平滑：0.7旧强度 + 0.3新强度
        2. 类型切换：当新旧类型差值≥2时切换
        3. 自然衰减：强度乘以0.9
        """
        # 1. 强度平滑
        self.strength = 0.7 * self.strength + 0.3 * new_strength

        # 2. 类型切换阈值（差值≥2时切换）
        if abs(new_type - self.type) >= 2:
            self.type = new_type

        # 3. 自然衰减
        self.strength *= 0.9

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

    def reset(self, new_type: int = 0, new_strength: float = 0.0) -> None:
        """
        重置情绪状态
        """
        self.type = max(0, min(3, new_type))
        self.strength = max(0.0, min(10.0, new_strength))