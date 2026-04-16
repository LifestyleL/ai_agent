#!/usr/bin/env python3
"""
Step 2 阻断验证测试
验证参数标准化和范围限制机制是否生效
"""

import sys
import os
import time

# 添加 my_agent 目录到路径，以便导入模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'my-react-app', 'my_agent'))

from live2d.animator import Live2DAnimator
from live2d.live2d_manager import Live2DManager
from live2d.live2d_constants import Live2DConstants


def test_animator_clamp_extreme_values():
    """测试 animator 对极端值的范围限制"""
    print("=== 测试 1: animator 对极端值的范围限制 ===")

    animator = Live2DAnimator()

    # 1. 设置极端值的目标参数
    animator.set_head(x=999, y=-999, z=500)        # 头部角度 ±30 范围外
    animator.set_body(x=999, y=-999, z=500)        # 身体角度 ±10 范围外
    animator.set_mouth(-50)                        # 嘴巴开合 0~1 范围外
    animator.set_hair(999)                         # 头发飘动 -3~3 范围外
    animator.set_eyes(left=999, right=-999)        # 眼睛开合 -1~1 范围外
    animator.set_arms(arm_a=999, arm_b=-999)       # 手臂显示 0~1 范围外

    # 2. 计算参数
    t = time.time()
    params = animator.compute_params(t)

    # 3. 验证范围限制
    errors = []

    # 头部角度应在 ±30 内
    if not (-30 <= params.get("ParamAngleX", 0) <= 30):
        errors.append(f"ParamAngleX 超出范围: {params.get('ParamAngleX')}")
    if not (-30 <= params.get("ParamAngleY", 0) <= 30):
        errors.append(f"ParamAngleY 超出范围: {params.get('ParamAngleY')}")
    if not (-30 <= params.get("ParamAngleZ", 0) <= 30):
        errors.append(f"ParamAngleZ 超出范围: {params.get('ParamAngleZ')}")

    # 身体角度应在 ±10 内
    if not (-10 <= params.get("ParamBodyAngleX", 0) <= 10):
        errors.append(f"ParamBodyAngleX 超出范围: {params.get('ParamBodyAngleX')}")
    if not (-10 <= params.get("ParamBodyAngleY", 0) <= 10):
        errors.append(f"ParamBodyAngleY 超出范围: {params.get('ParamBodyAngleY')}")
    if not (-10 <= params.get("ParamBodyAngleZ", 0) <= 10):
        errors.append(f"ParamBodyAngleZ 超出范围: {params.get('ParamBodyAngleZ')}")

    # 嘴巴开合应在 0~1 内
    if not (0 <= params.get("ParamMouthOpenY", 0) <= 1):
        errors.append(f"ParamMouthOpenY 超出范围: {params.get('ParamMouthOpenY')}")

    # 头发飘动应在 -3~3 内
    if not (-3 <= params.get("ParamHairAhoge", 0) <= 3):
        errors.append(f"ParamHairAhoge 超出范围: {params.get('ParamHairAhoge')}")

    # 眼睛开合应在 -1~1 内（set_eyes 已限制，但验证出口）
    eye_left = params.get("ParamEyeLOpen", 0)
    eye_right = params.get("ParamEyeROpen", 0)
    if not (-1 <= eye_left <= 1):
        errors.append(f"ParamEyeLOpen 超出范围: {eye_left}")
    if not (-1 <= eye_right <= 1):
        errors.append(f"ParamEyeROpen 超出范围: {eye_right}")

    # 手臂显示应在 0~1 内
    arm_params = ["ParamArmLA", "ParamArmLB", "ParamArmRA", "ParamArmRB"]
    for arm_param in arm_params:
        value = params.get(arm_param, 0)
        if not (0 <= value <= 1):
            errors.append(f"{arm_param} 超出范围: {value}")

    if errors:
        print("[FAIL] 测试失败:")
        for error in errors:
            print(f"  - {error}")
        print(f"  实际参数: {params}")
        return False
    else:
        print("[PASS] animator 范围限制测试通过")
        print(f"  参数全部在合法范围内: {list(params.keys())}")
        return True


def test_live2d_manager_param_normalization():
    """测试 live2d_manager 的参数名标准化和范围限制"""
    print("\n=== 测试 2: live2d_manager 参数名标准化和范围限制 ===")

    # 创建 Live2DManager 实例（单例模式，但测试中可以创建新的）
    manager = Live2DManager()

    # 重置控制，确保初始状态
    manager.reset_control()

    test_cases = [
        {
            "name": "标准参数名 + 极端值",
            "input": {
                "ParamAngleX": 999,          # 应被限制到 30
                "ParamMouthOpenY": -50,      # 应被限制到 0
                "ParamBodyAngleY": -999,     # 应被限制到 -10
                "ParamArmLA": 999,           # 应被限制到 1
            },
            "expected_keys": ["ParamAngleX", "ParamMouthOpenY", "ParamBodyAngleY", "ParamArmLA"]
        },
        {
            "name": "旧参数名 + 极端值",
            "input": {
                "headX": 999,                # 应被标准化为 ParamAngleX 并限制到 30
                "mouth": -50,                # 应被标准化为 ParamMouthOpenY 并限制到 0
                "bodyY": -999,               # 应被标准化为 ParamBodyAngleY 并限制到 -10
                "PartArmA": 999,             # 应被标准化为 ParamArmLA 并限制到 1
            },
            "expected_keys": ["ParamAngleX", "ParamMouthOpenY", "ParamBodyAngleY", "ParamArmLA"]
        },
        {
            "name": "混合参数名 + 正常值",
            "input": {
                "ParamAngleX": 15,           # 正常值，应保持不变
                "headY": -10,                # 旧参数名，应标准化
                "ParamEyeLOpen": 0.7,        # 标准参数名
                "eyeRight": 0.8,             # 旧参数名
            },
            "expected_keys": ["ParamAngleX", "ParamAngleY", "ParamEyeLOpen", "ParamEyeROpen"]
        }
    ]

    all_passed = True

    for i, test_case in enumerate(test_cases):
        print(f"\n子测试 {i+1}: {test_case['name']}")
        print(f"  输入参数: {test_case['input']}")

        # 调用 send_custom_params
        manager.send_custom_params(test_case['input'])

        # 获取 animator 的当前参数状态（通过计算一帧）
        t = time.time()
        animator_params = manager.animator.compute_params(t)

        # 验证参数名标准化
        missing_keys = []
        for expected_key in test_case['expected_keys']:
            if expected_key not in animator_params:
                missing_keys.append(expected_key)

        if missing_keys:
            print(f"  [FAIL] 参数名标准化失败: 缺少预期键 {missing_keys}")
            print(f"    实际参数键: {list(animator_params.keys())}")
            all_passed = False
            continue

        # 验证范围限制（针对本次测试的输入）
        errors = []

        # 检查每个输入参数是否被正确限制
        for input_key, input_value in test_case['input'].items():
            # 标准化参数名
            if input_key in Live2DConstants.OLD_PARAM_MAPPING:
                std_key = Live2DConstants.OLD_PARAM_MAPPING[input_key]
            else:
                std_key = input_key

            if std_key in animator_params:
                actual_value = animator_params[std_key]
                expected_range = Live2DConstants.PARAM_RANGES.get(std_key)

                if expected_range:
                    min_val, max_val = expected_range
                    if not (min_val <= actual_value <= max_val):
                        errors.append(f"{std_key}: 值 {actual_value} 超出范围 [{min_val}, {max_val}]")
                # 没有定义范围的不检查
            elif std_key in Live2DConstants.PARAM_RANGES:
                # 标准参数名应该在结果中
                errors.append(f"{std_key}: 未在输出参数中找到")

        if errors:
            print(f"  [FAIL] 范围限制验证失败:")
            for error in errors:
                print(f"    - {error}")
            all_passed = False
        else:
            print(f"  [PASS] 参数名标准化和范围限制通过")
            # 打印标准化后的参数值
            relevant_params = {k: animator_params[k] for k in test_case['expected_keys'] if k in animator_params}
            print(f"    标准化后参数: {relevant_params}")

    # 重置控制，避免影响后续测试
    manager.reset_control()

    return all_passed


def test_live2d_constants_clamp():
    """测试 Live2DConstants.clamp_params 函数"""
    print("\n=== 测试 3: Live2DConstants.clamp_params 函数 ===")

    test_params = {
        "ParamAngleX": 999,          # 应被限制到 30
        "ParamAngleY": -999,         # 应被限制到 -30
        "ParamMouthOpenY": -50,      # 应被限制到 0
        "ParamMouthOpenY": 50,       # 应被限制到 1（注意：键重复，后面的会覆盖）
        "ParamBodyAngleX": 999,      # 应被限制到 10
        "ParamArmLA": 999,           # 应被限制到 1
        "ParamHairAhoge": 999,       # 应被限制到 3
        "unknown_param": 999,        # 未知参数，应原样保留
    }

    clamped = Live2DConstants.clamp_params(test_params)

    errors = []

    # 检查标准参数的范围
    if not clamped.get("ParamAngleX", 0) == 30:
        errors.append(f"ParamAngleX: {clamped.get('ParamAngleX')} != 30")
    if not clamped.get("ParamAngleY", 0) == -30:
        errors.append(f"ParamAngleY: {clamped.get('ParamAngleY')} != -30")
    if not clamped.get("ParamMouthOpenY", 0) == 1:  # 被第二个值覆盖
        errors.append(f"ParamMouthOpenY: {clamped.get('ParamMouthOpenY')} != 1")
    if not clamped.get("ParamBodyAngleX", 0) == 10:
        errors.append(f"ParamBodyAngleX: {clamped.get('ParamBodyAngleX')} != 10")
    if not clamped.get("ParamArmLA", 0) == 1:
        errors.append(f"ParamArmLA: {clamped.get('ParamArmLA')} != 1")
    if not clamped.get("ParamHairAhoge", 0) == 3:
        errors.append(f"ParamHairAhoge: {clamped.get('ParamHairAhoge')} != 3")

    # 检查未知参数是否保留
    if not clamped.get("unknown_param", 0) == 999:
        errors.append(f"unknown_param: {clamped.get('unknown_param')} != 999")

    if errors:
        print(f"[FAIL] clamp_params 测试失败:")
        for error in errors:
            print(f"  - {error}")
        print(f"  实际结果: {clamped}")
        return False
    else:
        print("[PASS] Live2DConstants.clamp_params 测试通过")
        print(f"  输入: {test_params}")
        print(f"  输出: {clamped}")
        return True


def main():
    """运行所有测试"""
    print("=" * 70)
    print("Step 2 阻断验证测试")
    print("验证参数标准化和范围限制机制是否生效")
    print("=" * 70)

    results = []

    # 运行测试
    results.append(("animator 范围限制", test_animator_clamp_extreme_values()))
    results.append(("live2d_manager 参数标准化", test_live2d_manager_param_normalization()))
    results.append(("Live2DConstants.clamp_params", test_live2d_constants_clamp()))

    # 汇总结果
    print("\n" + "=" * 70)
    print("测试结果汇总:")
    print("=" * 70)

    all_passed = True
    for test_name, passed in results:
        status = "[PASS] 通过" if passed else "[FAIL] 失败"
        print(f"{test_name}: {status}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 70)
    if all_passed:
        print("[PASS] 所有测试通过！Step 2 验证完成，可以开始 Step 3。")
        return 0
    else:
        print("[FAIL] 测试失败！请修复问题后再继续 Step 3。")
        return 1


if __name__ == "__main__":
    sys.exit(main())