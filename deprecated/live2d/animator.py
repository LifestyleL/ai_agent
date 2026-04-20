# animator.py
import math
from .live2d_constants import Live2DConstants

def clamp(v, min_v, max_v):
    return max(min(v, max_v), min_v)

class Live2DAnimator:
    def __init__(self):
        # 目标值寄存器（None表示使用默认值）
        self._target_head_x = None
        self._target_head_y = None
        self._target_head_z = None

        self._target_body_x = None
        self._target_body_y = None
        self._target_body_z = None

        self._target_mouth = None
        self._target_hair = None
        self._target_eye_left = None
        self._target_eye_right = None
        self._target_arm_a = None
        self._target_arm_b = None

    # ---------------------------
    # 控制接口
    # ---------------------------
    def set_head(self, x=None, y=None, z=None):
        """设置头部目标值（None表示使用默认值）"""
        if x is not None:
            self._target_head_x = clamp(x, -30, 30)  # 🔥 改成 ±30
        if y is not None:
            self._target_head_y = clamp(y, -30, 30)  # 🔥 改成 ±30
        if z is not None:
            self._target_head_z = clamp(z, -30, 30)  # 🔥 改成 ±30

    def set_body(self, x=None, y=None, z=None):
        """设置身体目标值"""
        if x is not None:
            self._target_body_x = clamp(x, -10, 10)  # 🔥 改成 ±10
        if y is not None:
            self._target_body_y = clamp(y, -10, 10)  # 🔥 改成 ±10
        if z is not None:
            self._target_body_z = clamp(z, -10, 10)  # 🔥 改成 ±10

    def set_mouth(self, value=None):
        """设置嘴巴开合（0~1）"""
        if value is not None:
            self._target_mouth = clamp(value, 0, 1)

    def set_hair(self, value=None):
        """设置头发飘动（-3~3）"""
        if value is not None:
            self._target_hair = clamp(value, -3, 3)

    def set_eyes(self, left=None, right=None):
        """
        设置眼睛开合（0~1）
        -1表示使用前端眨眼（默认），0~1为具体开合值
        """
        if left is not None:
            self._target_eye_left = clamp(left, -1, 1)
        if right is not None:
            self._target_eye_right = clamp(right, -1, 1)

    def set_arms(self, arm_a=None, arm_b=None):
        """
        设置手臂状态（0~1）
        arm_a: 左臂显示度 (同时控制 ParamArmLA 和 ParamArmLB)
        arm_b: 右臂显示度 (同时控制 ParamArmRA 和 ParamArmRB)
        """
        if arm_a is not None:
            self._target_arm_a = clamp(arm_a, 0, 1)
        if arm_b is not None:
            self._target_arm_b = clamp(arm_b, 0, 1)

    def set_mode(self, mode):
        """设置模式（idle/thinking）- 已弃用，保留接口兼容性"""
        pass  # 模式概念已移除

    def reset_control(self):
        """重置所有控制，恢复完全默认值"""
        self._target_head_x = None
        self._target_head_y = None
        self._target_head_z = None
        self._target_body_x = None
        self._target_body_y = None
        self._target_body_z = None
        self._target_mouth = None
        self._target_hair = None
        self._target_eye_left = None
        self._target_eye_right = None
        self._target_arm_a = None
        self._target_arm_b = None

    # ---------------------------
    # 获取当前目标参数
    # ---------------------------
    def get_current_target_params(self):
        """
        获取当前目标参数值（去动画化版本）
        只返回目标寄存器中的值，如果没有设置则返回默认值
        所有平滑、呼吸动画由前端处理
        """
        # -------- 应用目标值（如果存在）或使用默认值 --------
        # 头部（默认：0度）
        target_head_x = self._target_head_x if self._target_head_x is not None else 0.0
        target_head_y = self._target_head_y if self._target_head_y is not None else 0.0
        target_head_z = self._target_head_z if self._target_head_z is not None else 0.0

        # 身体（默认：0度）
        target_body_x = self._target_body_x if self._target_body_x is not None else 0.0
        target_body_y = self._target_body_y if self._target_body_y is not None else 0.0
        target_body_z = self._target_body_z if self._target_body_z is not None else 0.0

        # 嘴巴（默认：0.0 闭嘴）
        mouth = self._target_mouth if self._target_mouth is not None else 0.0

        # 头发（默认：0.0 不飘动）
        hair = self._target_hair if self._target_hair is not None else 0.0

        # 眼睛（默认：1.0 睁眼）
        eye_left = self._target_eye_left if self._target_eye_left is not None else 1.0
        eye_right = self._target_eye_right if self._target_eye_right is not None else 1.0

        # 手臂（默认：1.0 显示）
        arm_a = self._target_arm_a if self._target_arm_a is not None else 1.0
        arm_b = self._target_arm_b if self._target_arm_b is not None else 1.0

        # -------- 应用范围限制（匹配前端） --------
        target_head_x = clamp(target_head_x, -30, 30)  # 🔥 改成 ±30
        target_head_y = clamp(target_head_y, -30, 30)  # 🔥 改成 ±30
        target_head_z = clamp(target_head_z, -30, 30)  # 🔥 改成 ±30

        target_body_x = clamp(target_body_x, -10, 10)  # 🔥 改成 ±10
        target_body_y = clamp(target_body_y, -10, 10)  # 🔥 改成 ±10
        target_body_z = clamp(target_body_z, -10, 10)  # 🔥 改成 ±10

        mouth = clamp(mouth, 0, 1)
        hair = clamp(hair, -3, 3)

        # 眼睛值已在set_eyes中限制（-1~1），这里不再限制以保持-1值
        # 手臂值已在set_arms中限制（0~1）

        # 构建参数字典
        params = {
            "ParamEyeLOpen": eye_left,
            "ParamEyeROpen": eye_right,
            "ParamMouthOpenY": mouth,
            "ParamAngleX": target_head_x,
            "ParamAngleY": target_head_y,
            "ParamAngleZ": target_head_z,
            "ParamHairAhoge": hair,
            "ParamBodyAngleX": target_body_x,
            "ParamBodyAngleY": target_body_y,
            "ParamBodyAngleZ": target_body_z,
            "ParamArmLA": arm_a,
            "ParamArmLB": arm_a,
            "ParamArmRA": arm_b,
            "ParamArmRB": arm_b,
        }

        # 应用标准范围限制
        params = Live2DConstants.clamp_params(params)

        return params

    # 向后兼容：保留 compute_params 方法，但调用新的方法
    def compute_params(self, t: float = 0.0):
        """
        向后兼容方法
        已弃用：不再需要时间参数，所有平滑动画由前端处理
        """
        return self.get_current_target_params()