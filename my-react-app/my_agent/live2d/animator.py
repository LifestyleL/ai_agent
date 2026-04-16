# animator.py
import math
import random
import time
from .live2d_constants import Live2DConstants

def clamp(v, min_v, max_v):
    return max(min(v, max_v), min_v)

class Live2DAnimator:
    def __init__(self):
        # 头部
        self.head_x = self.head_y = self.head_z = 0
        # 身体
        self.body_x = self.body_y = self.body_z = 0
        # 活动度平滑
        self.activity_smooth = 0.3
        # 模式切换
        self.mode = "idle"
        self.last_switch = time.time()
        # 眨眼
        self.blink_timer = 0
        self.blink_duration = 0.25

        # 目标值变量（None表示使用算法生成）
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
        self._target_activity = None

    # ---------------------------
    # 模式 & 活动度
    # ---------------------------
    def update_mode(self):
        now = time.time()
        if now - self.last_switch > random.uniform(4, 9):
            self.mode = random.choice(["idle", "thinking"])
            self.last_switch = now

    def get_activity_target(self):
        return 0.3 if self.mode == "idle" else 0.75

    # ---------------------------
    # 控制接口
    # ---------------------------
    def set_head(self, x=None, y=None, z=None):
        """设置头部目标值（None表示使用算法生成）"""
        if x is not None:
            self._target_head_x = clamp(x, -30, 30) # 🔥 改成 ±30
        if y is not None:
            self._target_head_y = clamp(y, -30, 30) # 🔥 改成 ±30
        if z is not None:
            self._target_head_z = clamp(z, -30, 30) # 🔥 改成 ±30


    def set_body(self, x=None, y=None, z=None):
        """设置身体目标值"""
        if x is not None:
            self._target_body_x = clamp(x, -10, 10) # 🔥 改成 ±10
        if y is not None:
            self._target_body_y = clamp(y, -10, 10) # 🔥 改成 ±10
        if z is not None:
            self._target_body_z = clamp(z, -10, 10) # 🔥 改成 ±10


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

    def set_activity(self, value=None):
        """设置活动度（0~1）"""
        if value is not None:
            self._target_activity = clamp(value, 0, 1)

    def set_mode(self, mode):
        """设置模式（idle/thinking）"""
        if mode in ["idle", "thinking"]:
            self.mode = mode

    def reset_control(self):
        """重置所有控制，恢复完全算法生成"""
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
        self._target_activity = None

    # ---------------------------
    # 生成参数
    # ---------------------------
    def compute_params(self, t: float):
        self.update_mode()

        # -------- 活动度 --------
        if self._target_activity is not None:
            # 使用外部设置的活动度
            activity = self._target_activity
            self.activity_smooth = activity  # 同步平滑值
        else:
            # 原有活动度算法
            activity_target = self.get_activity_target()
            self.activity_smooth += (activity_target - self.activity_smooth) * 0.02
            activity = self.activity_smooth

        # -------- 计算算法基础值 --------
        # 头部基础值
        main = math.sin(t * 0.6)
        noise_x = math.sin(t * 0.25 + 10) * 0.4
        noise_y = math.sin(t * 0.20 + 20) * 0.3

        algo_head_x = (main * 7 + noise_x) * activity
        algo_head_y = (math.sin(t * 0.6 + 0.5) * 5 + noise_y) * activity
        algo_head_z = math.sin(t * 0.2) * 2 * activity

        # 身体基础值
        algo_body_x = -algo_head_x * 0.2 + math.sin(t * 0.4 + 30) * activity
        algo_body_y = math.sin(t * 0.3 + 40) * 1.5 * activity
        algo_body_z = -algo_head_z * 0.15

        # 嘴巴基础值
        algo_mouth = (math.sin(t * 3) + 1) / 2 * 0.3  # 0~0.3 轻微张嘴

        # 头发基础值
        algo_hair = algo_head_x * 0.3 + math.sin(t * 2) * 0.5

        # 眼睛基础值（默认睁眼）
        algo_eye_left = 1.0
        algo_eye_right = 1.0

        # 手臂基础值
        algo_arm_a = 1.0
        algo_arm_b = 0.0

        # -------- 应用目标值（如果存在） --------
        # 头部
        target_head_x = self._target_head_x if self._target_head_x is not None else algo_head_x
        target_head_y = self._target_head_y if self._target_head_y is not None else algo_head_y
        target_head_z = self._target_head_z if self._target_head_z is not None else algo_head_z

        # 身体
        target_body_x = self._target_body_x if self._target_body_x is not None else algo_body_x
        target_body_y = self._target_body_y if self._target_body_y is not None else algo_body_y
        target_body_z = self._target_body_z if self._target_body_z is not None else algo_body_z

        # 嘴巴
        mouth = self._target_mouth if self._target_mouth is not None else algo_mouth

        # 头发
        hair = self._target_hair if self._target_hair is not None else algo_hair

        # 眼睛
        eye_left = self._target_eye_left if self._target_eye_left is not None else algo_eye_left
        eye_right = self._target_eye_right if self._target_eye_right is not None else algo_eye_right

        # 手臂
        arm_a = self._target_arm_a if self._target_arm_a is not None else algo_arm_a
        arm_b = self._target_arm_b if self._target_arm_b is not None else algo_arm_b

        # -------- 应用范围限制（匹配前端） --------
        target_head_x = clamp(target_head_x, -30, 30) # 🔥 改成 ±30
        target_head_y = clamp(target_head_y, -30, 30) # 🔥 改成 ±30
        target_head_z = clamp(target_head_z, -30, 30) # 🔥 改成 ±30

        target_body_x = clamp(target_body_x, -10, 10) # 🔥 改成 ±10
        target_body_y = clamp(target_body_y, -10, 10) # 🔥 改成 ±10
        target_body_z = clamp(target_body_z, -10, 10) # 🔥 改成 ±10

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