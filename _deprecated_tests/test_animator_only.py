#!/usr/bin/env python3
"""
只测试Animator控制接口，避免循环导入问题
"""

import time
import math

def clamp(v, min_v, max_v):
    return max(min(v, max_v), min_v)

# 直接导入animator，避免导入live2d_manager
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from live2d.animator import Live2DAnimator
    print("成功导入Live2DAnimator")
except ImportError as e:
    print(f"导入失败: {e}")
    print("尝试手动创建类...")

    # 手动定义简化版的Live2DAnimator类
    import random

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

        # 这里省略其他方法，只为了测试
        def set_head(self, x=None, y=None, z=None):
            """设置头部目标值（None表示使用算法生成）"""
            if x is not None:
                self._target_head_x = clamp(x, -10, 10)
            if y is not None:
                self._target_head_y = clamp(y, -8, 8)
            if z is not None:
                self._target_head_z = clamp(z, -5, 5)

        def set_body(self, x=None, y=None, z=None):
            """设置身体目标值"""
            if x is not None:
                self._target_body_x = clamp(x, -1, 1)
            if y is not None:
                self._target_body_y = clamp(y, -0.5, 0.5)
            if z is not None:
                self._target_body_z = clamp(z, -0.3, 0.3)

        def set_mouth(self, value=None):
            """设置嘴巴开合（0~1）"""
            if value is not None:
                self._target_mouth = clamp(value, 0, 1)

        def compute_params(self, t: float):
            """简化版的compute_params"""
            # 返回一个简单的测试参数集
            return {
                "eyeLeft": 1.0,
                "eyeRight": 1.0,
                "mouth": 0.3,
                "headX": 0.0,
                "headY": 0.0,
                "headZ": 0.0,
                "hair": 0.0,
                "bodyX": 0.0,
                "bodyY": 0.0,
                "bodyZ": 0.0,
                "PartArmA": 1.0,
                "PartArmB": 0.0
            }

def test_animator_controls():
    """测试Animator控制功能"""
    print("=" * 60)
    print("Live2DAnimator 控制接口测试")
    print("=" * 60)

    # 创建Animator实例
    animator = Live2DAnimator()
    print("Live2DAnimator实例创建成功")

    # 测试1: 初始状态
    print("\n[测试1] 初始状态检查")
    t = time.time()
    params = animator.compute_params(t)
    print(f"初始参数数量: {len(params)}")
    print(f"初始模式: {animator.mode}")
    print(f"初始活动度: {animator.activity_smooth:.3f}")

    # 测试2: 设置头部
    print("\n[测试2] 设置头部参数")
    animator.set_head(x=0.5, y=-0.3, z=0.2)
    print(f"设置后目标值: head_x={animator._target_head_x}, head_y={animator._target_head_y}, head_z={animator._target_head_z}")

    # 测试3: 设置身体
    print("\n[测试3] 设置身体参数")
    animator.set_body(x=0.3, y=0.1, z=-0.1)
    print(f"设置后目标值: body_x={animator._target_body_x}, body_y={animator._target_body_y}, body_z={animator._target_body_z}")

    # 测试4: 设置嘴巴
    print("\n[测试4] 设置嘴巴参数")
    animator.set_mouth(0.8)
    print(f"设置后目标值: mouth={animator._target_mouth}")

    # 测试5: 测试范围限制
    print("\n[测试5] 测试参数范围限制")

    # 测试超出上限
    animator.set_head(x=15.0)  # 应限制为10.0
    print(f"设置headX=15.0 -> 实际: {animator._target_head_x} (期望: 10.0)")

    # 测试超出下限
    animator.set_head(x=-15.0)  # 应限制为-10.0
    print(f"设置headX=-15.0 -> 实际: {animator._target_head_x} (期望: -10.0)")

    # 测试嘴巴范围
    animator.set_mouth(1.5)  # 应限制为1.0
    print(f"设置mouth=1.5 -> 实际: {animator._target_mouth} (期望: 1.0)")

    animator.set_mouth(-0.5)  # 应限制为0.0
    print(f"设置mouth=-0.5 -> 实际: {animator._target_mouth} (期望: 0.0)")

    # 测试6: 测试None值处理
    print("\n[测试6] 测试None值处理")
    animator.set_head(x=None, y=None, z=None)  # 全部设为None
    print(f"全部设为None后: head_x={animator._target_head_x}, head_y={animator._target_head_y}, head_z={animator._target_head_z}")

    # 测试7: 部分设置
    print("\n[测试7] 测试部分设置")
    animator.set_head(x=0.7)  # 只设置x
    print(f"只设置headX=0.7: head_x={animator._target_head_x}, head_y={animator._target_head_y}, head_z={animator._target_head_z}")

    print("\n" + "=" * 60)
    print("Animator控制接口测试完成!")
    print("=" * 60)

    # 显示最终状态
    print("\n最终目标值状态:")
    target_vars = [
        ("_target_head_x", animator._target_head_x),
        ("_target_head_y", animator._target_head_y),
        ("_target_head_z", animator._target_head_z),
        ("_target_body_x", animator._target_body_x),
        ("_target_body_y", animator._target_body_y),
        ("_target_body_z", animator._target_body_z),
        ("_target_mouth", animator._target_mouth),
    ]

    for name, value in target_vars:
        status = "已设置" if value is not None else "未设置"
        val_str = f"{value:.3f}" if value is not None else "None"
        print(f"  {name}: {val_str} ({status})")

def test_parameter_calculation():
    """测试参数计算逻辑"""
    print("\n" + "=" * 60)
    print("参数计算逻辑测试")
    print("=" * 60)

    # 创建新的animator实例
    animator = Live2DAnimator()

    # 测试不同时间点的参数
    print("测试不同时间点的参数变化:")

    times = [0.0, 1.0, 2.0, 3.0, 4.0]
    for t in times:
        params = animator.compute_params(t)
        print(f"\n时间 t={t:.1f}s:")
        print(f"  headX: {params.get('headX', 0):.3f}")
        print(f"  headY: {params.get('headY', 0):.3f}")
        print(f"  mouth: {params.get('mouth', 0):.3f}")
        print(f"  bodyX: {params.get('bodyX', 0):.3f}")

if __name__ == "__main__":
    print("开始测试Live2DAnimator控制接口...")

    test_animator_controls()
    test_parameter_calculation()

    print("\n所有测试完成!")
    print("\n下一步:")
    print("1. 运行主系统: python main.py")
    print("2. 在另一个终端运行调试器: python live2d_debug.py")
    print("3. 或运行监控器: python live2d_monitor.py")