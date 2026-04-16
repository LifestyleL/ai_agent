import math
from .live2d_constants import Live2DConstants

def clamp(v, min_v, max_v):
    return max(min(v, max_v), min_v)

class CleanFaceDriver:
    """极简驱动：只负责把 0~1 的坐标，翻译成 -30~30 的 Live2D角度"""
    
    def __init__(self):
        # 放大系数（如果觉得转头太小，就调大这三个数）
        self.head_x_scale = 60.0  
        self.head_y_scale = 50.0
        self.head_z_scale = 40.0
        
        self.body_x_scale = 20.0
        self.body_y_scale = 15.0

    def compute(self, raw_face_x, raw_face_y, raw_face_z, mouth_open, eye_open):
        """
        输入：摄像头原始数据 (假设 x,y 在 0~1 之间，0.5为中心)
        输出：直接返回符合 Live2D 命名规范的字典
        """
        # 1. 计算偏移量 (减去中心点 0.5)
        offset_x = raw_face_x - 0.5
        offset_y = raw_face_y - 0.5
        
        # 2. 乘以系数，得到目标角度
        target_angle_x = offset_x * self.head_x_scale
        target_angle_y = offset_y * self.head_y_scale
        target_angle_z = raw_face_z * self.head_z_scale
        
        # 3. 身体联动（通常身体动作是头部的 1/3 到 1/2）
        target_body_x = offset_x * self.body_x_scale
        target_body_y = offset_y * self.body_y_scale

        # 4. 🌟 核心铁律：直接使用 Live2D 的原生参数名作为键名！
        params = {
            "ParamAngleX": clamp(target_angle_x, -30, 30),
            "ParamAngleY": clamp(target_angle_y, -30, 30),
            "ParamAngleZ": clamp(target_angle_z, -30, 30),

            "ParamBodyAngleX": clamp(target_body_x, -10, 10),
            "ParamBodyAngleY": clamp(target_body_y, -10, 10),
            "ParamBodyAngleZ": 0,

            "ParamMouthOpenY": clamp(mouth_open, 0, 1),
            "ParamEyeLOpen": clamp(eye_open, 0, 1),
            "ParamEyeROpen": clamp(eye_open, 0, 1),

            # 手臂参数（标准化）
            "ParamArmLA": 1,
            "ParamArmLB": 1,
            "ParamArmRA": 1,
            "ParamArmRB": 1
        }

        # 应用标准范围限制
        params = Live2DConstants.clamp_params(params)

        return params
