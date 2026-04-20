"""
Live2D 标准参数常量定义
遵循架构方案 4.3 节规范：前后端统一使用相同的参数名称
"""

from typing import Dict, Tuple, Any

class Live2DConstants:
    """Live2D 标准参数常量类"""

    # ==================== 标准参数名 ====================

    # 头部角度参数
    PARAM_ANGLE_X = "ParamAngleX"
    PARAM_ANGLE_Y = "ParamAngleY"
    PARAM_ANGLE_Z = "ParamAngleZ"

    # 身体角度参数
    PARAM_BODY_ANGLE_X = "ParamBodyAngleX"
    PARAM_BODY_ANGLE_Y = "ParamBodyAngleY"
    PARAM_BODY_ANGLE_Z = "ParamBodyAngleZ"

    # 面部表情参数
    PARAM_MOUTH_OPEN_Y = "ParamMouthOpenY"
    PARAM_EYE_L_OPEN = "ParamEyeLOpen"
    PARAM_EYE_R_OPEN = "ParamEyeROpen"
    PARAM_HAIR_AHOGE = "ParamHairAhoge"

    # 手臂显示参数（标准化命名，废除 PartArmA/B）
    PARAM_ARM_LA = "ParamArmLA"  # 左臂A
    PARAM_ARM_RA = "ParamArmRA"  # 右臂A
    PARAM_ARM_LB = "ParamArmLB"  # 左臂B
    PARAM_ARM_RB = "ParamArmRB"  # 右臂B

    # ==================== 参数取值范围 ====================

    # 角度范围（单位：度）
    HEAD_ANGLE_RANGE = (-30.0, 30.0)      # 头部角度 ±30°
    BODY_ANGLE_RANGE = (-10.0, 10.0)      # 身体角度 ±10°

    # 开合范围（0~1）
    MOUTH_OPEN_RANGE = (0.0, 1.0)         # 嘴巴开合 0=闭嘴, 1=最大
    EYE_OPEN_RANGE = (0.0, 1.0)           # 眼睛开合 0=闭眼, 1=睁眼
    ARM_VISIBILITY_RANGE = (0.0, 1.0)     # 手臂显示 0=隐藏, 1=显示

    # 特殊范围
    HAIR_AHOGE_RANGE = (-3.0, 3.0)        # 头发飘动范围

    # ==================== 参数到范围的映射 ====================

    # 每个标准参数的取值范围
    PARAM_RANGES: Dict[str, Tuple[float, float]] = {
        # 头部角度
        PARAM_ANGLE_X: HEAD_ANGLE_RANGE,
        PARAM_ANGLE_Y: HEAD_ANGLE_RANGE,
        PARAM_ANGLE_Z: HEAD_ANGLE_RANGE,

        # 身体角度
        PARAM_BODY_ANGLE_X: BODY_ANGLE_RANGE,
        PARAM_BODY_ANGLE_Y: BODY_ANGLE_RANGE,
        PARAM_BODY_ANGLE_Z: BODY_ANGLE_RANGE,

        # 面部表情
        PARAM_MOUTH_OPEN_Y: MOUTH_OPEN_RANGE,
        PARAM_EYE_L_OPEN: EYE_OPEN_RANGE,
        PARAM_EYE_R_OPEN: EYE_OPEN_RANGE,
        PARAM_HAIR_AHOGE: HAIR_AHOGE_RANGE,

        # 手臂显示
        PARAM_ARM_LA: ARM_VISIBILITY_RANGE,
        PARAM_ARM_RA: ARM_VISIBILITY_RANGE,
        PARAM_ARM_LB: ARM_VISIBILITY_RANGE,
        PARAM_ARM_RB: ARM_VISIBILITY_RANGE,
    }

    # ==================== 工具方法 ====================

    @staticmethod
    def clamp_param(param_name: str, value: float) -> float:
        """根据参数名限制值在合法范围内"""
        if param_name not in Live2DConstants.PARAM_RANGES:
            return value  # 未知参数，不限制

        min_val, max_val = Live2DConstants.PARAM_RANGES[param_name]
        return max(min_val, min(value, max_val))

    @staticmethod
    def clamp_params(params_dict: Dict[str, float]) -> Dict[str, float]:
        """批量限制参数值在合法范围内"""
        result = {}
        for param_name, value in params_dict.items():
            if param_name in Live2DConstants.PARAM_RANGES:
                result[param_name] = Live2DConstants.clamp_param(param_name, value)
            else:
                result[param_name] = value  # 未知参数，原样保留
        return result

    @staticmethod
    def is_standard_param(param_name: str) -> bool:
        """检查参数名是否为标准参数"""
        return param_name in Live2DConstants.PARAM_RANGES

    @staticmethod
    def get_all_standard_params() -> list:
        """获取所有标准参数名列表"""
        return list(Live2DConstants.PARAM_RANGES.keys())

    # ==================== 旧参数名兼容映射 ====================
    # 注：仅用于临时兼容，新代码应直接使用标准参数名

    OLD_PARAM_MAPPING = {
        # 头部参数别名
        "headX": PARAM_ANGLE_X,
        "headY": PARAM_ANGLE_Y,
        "headZ": PARAM_ANGLE_Z,

        # 身体参数别名
        "bodyX": PARAM_BODY_ANGLE_X,
        "bodyY": PARAM_BODY_ANGLE_Y,
        "bodyZ": PARAM_BODY_ANGLE_Z,

        # 面部表情别名
        "mouth": PARAM_MOUTH_OPEN_Y,
        "eyeLeft": PARAM_EYE_L_OPEN,
        "eyeRight": PARAM_EYE_R_OPEN,
        "hair": PARAM_HAIR_AHOGE,

        # 手臂别名（废弃）
        "PartArmA": PARAM_ARM_LA,  # 映射到左臂A
        "PartArmB": PARAM_ARM_RA,  # 映射到右臂A
        "arm_a": PARAM_ARM_LA,
        "arm_b": PARAM_ARM_RA,
    }

    @staticmethod
    def normalize_params(params_dict: Dict[str, Any]) -> Dict[str, float]:
        """
        将包含旧参数名的字典转换为标准参数名字典
        并确保所有值在合法范围内
        """
        normalized = {}

        for key, value in params_dict.items():
            # 转换参数名
            if key in Live2DConstants.OLD_PARAM_MAPPING:
                std_key = Live2DConstants.OLD_PARAM_MAPPING[key]
            else:
                std_key = key

            # 确保值为浮点数
            try:
                float_value = float(value)
            except (ValueError, TypeError):
                continue  # 忽略无法转换的值

            normalized[std_key] = float_value

        # 应用范围限制
        return Live2DConstants.clamp_params(normalized)