#!/usr/bin/env python3
"""
去动画化重构测试
验证 animator.py 和 live2d_manager.py 的修改是否正确
"""

import sys
import os

# 添加 my_agent 目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'my-react-app', 'my_agent'))

from live2d.animator import Live2DAnimator
from live2d.live2d_manager import Live2DManager


def test_animator_basic():
    """测试 animator 基础功能"""
    print("=== 测试 1: animator 基础功能 ===")

    animator = Live2DAnimator()

    # 1. 测试默认值
    params = animator.get_current_target_params()
    print(f"默认参数: {params}")

    # 检查默认值
    assert params["ParamAngleX"] == 0.0, f"ParamAngleX 默认值错误: {params['ParamAngleX']}"
    assert params["ParamAngleY"] == 0.0, f"ParamAngleY 默认值错误: {params['ParamAngleY']}"
    assert params["ParamAngleZ"] == 0.0, f"ParamAngleZ 默认值错误: {params['ParamAngleZ']}"
    assert params["ParamBodyAngleX"] == 0.0, f"ParamBodyAngleX 默认值错误: {params['ParamBodyAngleX']}"
    assert params["ParamBodyAngleY"] == 0.0, f"ParamBodyAngleY 默认值错误: {params['ParamBodyAngleY']}"
    assert params["ParamBodyAngleZ"] == 0.0, f"ParamBodyAngleZ 默认值错误: {params['ParamBodyAngleZ']}"
    assert params["ParamMouthOpenY"] == 0.0, f"ParamMouthOpenY 默认值错误: {params['ParamMouthOpenY']}"
    assert params["ParamHairAhoge"] == 0.0, f"ParamHairAhoge 默认值错误: {params['ParamHairAhoge']}"
    assert params["ParamEyeLOpen"] == 1.0, f"ParamEyeLOpen 默认值错误: {params['ParamEyeLOpen']}"
    assert params["ParamEyeROpen"] == 1.0, f"ParamEyeROpen 默认值错误: {params['ParamEyeROpen']}"
    assert params["ParamArmLA"] == 1.0, f"ParamArmLA 默认值错误: {params['ParamArmLA']}"
    assert params["ParamArmLB"] == 1.0, f"ParamArmLB 默认值错误: {params['ParamArmLB']}"
    assert params["ParamArmRA"] == 1.0, f"ParamArmRA 默认值错误: {params['ParamArmRA']}"
    assert params["ParamArmRB"] == 1.0, f"ParamArmRB 默认值错误: {params['ParamArmRB']}"

    print("[PASS] 默认值测试通过")

    # 2. 测试设置值
    animator.set_head(x=15, y=-10, z=5)
    animator.set_body(x=5, y=-3, z=2)
    animator.set_mouth(0.8)
    animator.set_hair(1.5)
    animator.set_eyes(left=0.7, right=0.9)
    animator.set_arms(arm_a=0.5, arm_b=0.6)

    params = animator.get_current_target_params()

    # 检查设置的值
    assert abs(params["ParamAngleX"] - 15) < 0.001, f"ParamAngleX 设置值错误: {params['ParamAngleX']}"
    assert abs(params["ParamAngleY"] - (-10)) < 0.001, f"ParamAngleY 设置值错误: {params['ParamAngleY']}"
    assert abs(params["ParamAngleZ"] - 5) < 0.001, f"ParamAngleZ 设置值错误: {params['ParamAngleZ']}"
    assert abs(params["ParamBodyAngleX"] - 5) < 0.001, f"ParamBodyAngleX 设置值错误: {params['ParamBodyAngleX']}"
    assert abs(params["ParamBodyAngleY"] - (-3)) < 0.001, f"ParamBodyAngleY 设置值错误: {params['ParamBodyAngleY']}"
    assert abs(params["ParamBodyAngleZ"] - 2) < 0.001, f"ParamBodyAngleZ 设置值错误: {params['ParamBodyAngleZ']}"
    assert abs(params["ParamMouthOpenY"] - 0.8) < 0.001, f"ParamMouthOpenY 设置值错误: {params['ParamMouthOpenY']}"
    assert abs(params["ParamHairAhoge"] - 1.5) < 0.001, f"ParamHairAhoge 设置值错误: {params['ParamHairAhoge']}"
    assert abs(params["ParamEyeLOpen"] - 0.7) < 0.001, f"ParamEyeLOpen 设置值错误: {params['ParamEyeLOpen']}"
    assert abs(params["ParamEyeROpen"] - 0.9) < 0.001, f"ParamEyeROpen 设置值错误: {params['ParamEyeROpen']}"
    assert abs(params["ParamArmLA"] - 0.5) < 0.001, f"ParamArmLA 设置值错误: {params['ParamArmLA']}"
    assert abs(params["ParamArmLB"] - 0.5) < 0.001, f"ParamArmLB 设置值错误: {params['ParamArmLB']}"
    assert abs(params["ParamArmRA"] - 0.6) < 0.001, f"ParamArmRA 设置值错误: {params['ParamArmRA']}"
    assert abs(params["ParamArmRB"] - 0.6) < 0.001, f"ParamArmRB 设置值错误: {params['ParamArmRB']}"

    print("[PASS] 设置值测试通过")

    # 3. 测试范围限制
    animator.set_head(x=999, y=-999, z=999)  # 应被限制到 ±30
    animator.set_body(x=999, y=-999, z=999)  # 应被限制到 ±10
    animator.set_mouth(999)  # 应被限制到 1.0
    animator.set_hair(999)   # 应被限制到 3.0
    animator.set_eyes(left=999, right=-999)  # 应被限制到 1.0 和 -1.0
    animator.set_arms(arm_a=999, arm_b=-999)  # 应被限制到 1.0 和 0.0

    params = animator.get_current_target_params()

    # 检查范围限制
    assert -30 <= params["ParamAngleX"] <= 30, f"ParamAngleX 范围限制失败: {params['ParamAngleX']}"
    assert -30 <= params["ParamAngleY"] <= 30, f"ParamAngleY 范围限制失败: {params['ParamAngleY']}"
    assert -30 <= params["ParamAngleZ"] <= 30, f"ParamAngleZ 范围限制失败: {params['ParamAngleZ']}"
    assert -10 <= params["ParamBodyAngleX"] <= 10, f"ParamBodyAngleX 范围限制失败: {params['ParamBodyAngleX']}"
    assert -10 <= params["ParamBodyAngleY"] <= 10, f"ParamBodyAngleY 范围限制失败: {params['ParamBodyAngleY']}"
    assert -10 <= params["ParamBodyAngleZ"] <= 10, f"ParamBodyAngleZ 范围限制失败: {params['ParamBodyAngleZ']}"
    assert 0 <= params["ParamMouthOpenY"] <= 1, f"ParamMouthOpenY 范围限制失败: {params['ParamMouthOpenY']}"
    assert -3 <= params["ParamHairAhoge"] <= 3, f"ParamHairAhoge 范围限制失败: {params['ParamHairAhoge']}"
    assert -1 <= params["ParamEyeLOpen"] <= 1, f"ParamEyeLOpen 范围限制失败: {params['ParamEyeLOpen']}"
    assert -1 <= params["ParamEyeROpen"] <= 1, f"ParamEyeROpen 范围限制失败: {params['ParamEyeROpen']}"
    assert 0 <= params["ParamArmLA"] <= 1, f"ParamArmLA 范围限制失败: {params['ParamArmLA']}"
    assert 0 <= params["ParamArmLB"] <= 1, f"ParamArmLB 范围限制失败: {params['ParamArmLB']}"
    assert 0 <= params["ParamArmRA"] <= 1, f"ParamArmRA 范围限制失败: {params['ParamArmRA']}"
    assert 0 <= params["ParamArmRB"] <= 1, f"ParamArmRB 范围限制失败: {params['ParamArmRB']}"

    print("[PASS] 范围限制测试通过")

    # 4. 测试 reset_control
    animator.reset_control()
    params = animator.get_current_target_params()

    # 检查是否恢复默认值
    assert params["ParamAngleX"] == 0.0, f"reset_control 后 ParamAngleX 错误: {params['ParamAngleX']}"
    assert params["ParamAngleY"] == 0.0, f"reset_control 后 ParamAngleY 错误: {params['ParamAngleY']}"
    assert params["ParamAngleZ"] == 0.0, f"reset_control 后 ParamAngleZ 错误: {params['ParamAngleZ']}"
    assert params["ParamMouthOpenY"] == 0.0, f"reset_control 后 ParamMouthOpenY 错误: {params['ParamMouthOpenY']}"

    print("[PASS] reset_control 测试通过")

    return True


def test_animator_no_sin():
    """测试 animator 中没有 sin 计算"""
    print("\n=== 测试 2: animator 中没有 sin 计算 ===")

    # 读取 animator.py 文件内容
    animator_path = os.path.join(os.path.dirname(__file__), '..', 'my-react-app', 'my_agent', 'live2d', 'animator.py')
    with open(animator_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查是否包含 sin 计算
    forbidden_patterns = [
        "math.sin",
        "math.cos",
        "math.tan",
        "update_mode",
        "get_activity_target",
        "activity_smooth",
        "blink_timer",
        "last_switch",
    ]

    violations = []
    for pattern in forbidden_patterns:
        if pattern in content:
            violations.append(pattern)

    if violations:
        print(f"[FAIL] 发现禁止的模式: {violations}")
        return False

    # 检查是否包含时间参数
    if "compute_params(self, t: float)" in content and "t" in content:
        # 允许 compute_params 方法存在（向后兼容），但检查是否使用了 t 参数
        lines = content.split('\n')
        in_compute = False
        uses_t = False
        for line in lines:
            if "def compute_params" in line:
                in_compute = True
            elif "def " in line and "def compute_params" not in line and in_compute:
                in_compute = False

            if in_compute and "t" in line and not line.strip().startswith('#'):
                # 检查是否是方法签名或注释
                if "def compute_params" not in line and not "向后兼容" in line:
                    uses_t = True

        if uses_t:
            print("[FAIL] compute_params 方法中使用了时间参数 t")
            return False

    print("[PASS] 没有发现 sin 计算和时间依赖")
    return True


def test_live2d_manager_basic():
    """测试 live2d_manager 基础功能"""
    print("\n=== 测试 3: live2d_manager 基础功能 ===")

    # 创建管理器实例
    manager = Live2DManager()

    # 模拟 WebSocket 队列
    class MockQueue:
        def __init__(self):
            self.items = []
        def put(self, item):
            self.items.append(item)

    # 替换 send_queue
    from unittest.mock import patch
    import netwebsocket.ws_server

    mock_queue = MockQueue()

    with patch('live2d.live2d_manager._get_ws_instance') as mock_get_ws:
        mock_ws = type('MockWS', (), {'send_queue': mock_queue})()
        mock_get_ws.return_value = mock_ws

        # 1. 测试坐标映射
        manager.set_head(x=0.75, y=0.25, z=0.5)  # x: (0.75-0.5)*60=15, y: (0.25-0.5)*60=-15, z: 0.5*30=15

        # 检查队列中是否有数据
        if len(mock_queue.items) > 0:
            last_item = mock_queue.items[-1]
            print(f"set_head 后发送的参数: {last_item}")
            # 检查参数值
            assert abs(last_item.get("ParamAngleX", 0) - 15) < 0.1, f"坐标映射错误: {last_item.get('ParamAngleX')}"
            assert abs(last_item.get("ParamAngleY", 0) - (-15)) < 0.1, f"坐标映射错误: {last_item.get('ParamAngleY')}"
            assert abs(last_item.get("ParamAngleZ", 0) - 15) < 0.1, f"坐标映射错误: {last_item.get('ParamAngleZ')}"
        else:
            print("[FAIL] set_head 后没有发送参数")
            return False

        # 2. 测试 send_custom_params
        mock_queue.items.clear()  # 清空队列

        manager.send_custom_params({
            "ParamAngleX": 20,
            "ParamMouthOpenY": 0.5,
            "ParamEyeLOpen": 0.8
        })

        if len(mock_queue.items) > 0:
            last_item = mock_queue.items[-1]
            print(f"send_custom_params 后发送的参数: {last_item}")
            assert abs(last_item.get("ParamAngleX", 0) - 20) < 0.1, f"send_custom_params 错误: {last_item.get('ParamAngleX')}"
            assert abs(last_item.get("ParamMouthOpenY", 0) - 0.5) < 0.1, f"send_custom_params 错误: {last_item.get('ParamMouthOpenY')}"
            assert abs(last_item.get("ParamEyeLOpen", 0) - 0.8) < 0.1, f"send_custom_params 错误: {last_item.get('ParamEyeLOpen')}"
        else:
            print("[FAIL] send_custom_params 后没有发送参数")
            return False

        # 3. 测试 reset_control
        mock_queue.items.clear()

        manager.reset_control()

        if len(mock_queue.items) > 0:
            last_item = mock_queue.items[-1]
            print(f"reset_control 后发送的参数: {last_item}")
            # 重置后应该恢复默认值
            assert abs(last_item.get("ParamAngleX", 999) - 0) < 0.1, f"reset_control 错误: {last_item.get('ParamAngleX')}"
        else:
            print("[FAIL] reset_control 后没有发送参数")
            return False

    print("[PASS] live2d_manager 基础功能测试通过")
    return True


def test_live2d_manager_no_30fps():
    """测试 live2d_manager 没有 30fps 轮询"""
    print("\n=== 测试 4: live2d_manager 没有 30fps 轮询 ===")

    # 读取 live2d_manager.py 文件内容
    manager_path = os.path.join(os.path.dirname(__file__), '..', 'my-react-app', 'my_agent', 'live2d', 'live2d_manager.py')
    with open(manager_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 检查是否包含 30fps 轮询模式
    forbidden_patterns = [
        "time.sleep(0.033)",  # 30fps
        "time.sleep(0.016)",  # 60fps
        "time.sleep(0.01)",   # 100fps
        "while.*sleep.*0.0",  # 高频轮询
    ]

    violations = []
    for pattern in forbidden_patterns:
        if pattern in content:
            violations.append(pattern)

    # 允许 time.sleep(0.1) 用于低频心跳
    if "time.sleep(0.1)" in content:
        print("[PASS] 使用 0.1 秒低频心跳（允许）")

    if violations:
        print(f"[FAIL] 发现高频轮询模式: {violations}")
        return False

    # 检查 _sync_loop 是否包含事件驱动逻辑
    if "_send_current_params" not in content:
        print("[FAIL] 缺少 _send_current_params 方法")
        return False

    # 检查 set 方法是否调用 _send_current_params
    set_methods = ["set_head", "set_body", "set_mouth", "set_hair", "set_eyes", "set_arms"]
    missing_calls = []

    for method in set_methods:
        # 查找方法定义
        method_pattern = f"def {method}("
        if method_pattern in content:
            # 检查方法体中是否有 _send_current_params()
            lines = content.split('\n')
            in_method = False
            has_call = False

            for line in lines:
                if method_pattern in line:
                    in_method = True
                elif in_method and line.strip().startswith("def "):
                    break

                if in_method and "_send_current_params()" in line:
                    has_call = True

            if not has_call:
                missing_calls.append(method)

    if missing_calls:
        print(f"[FAIL] 以下方法没有调用 _send_current_params: {missing_calls}")
        return False

    print("[PASS] 没有 30fps 轮询，采用事件驱动")
    return True


def main():
    """运行所有测试"""
    print("=" * 70)
    print("去动画化重构测试")
    print("验证后端已移除所有动画计算，改为事件驱动")
    print("=" * 70)

    results = []

    # 运行测试
    results.append(("animator 基础功能", test_animator_basic()))
    results.append(("animator 没有 sin 计算", test_animator_no_sin()))
    results.append(("live2d_manager 基础功能", test_live2d_manager_basic()))
    results.append(("live2d_manager 没有 30fps 轮询", test_live2d_manager_no_30fps()))

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
        print("[PASS] 所有测试通过！去动画化重构成功完成。")
        print("\n重构总结:")
        print("1. animator.py: 移除所有 sin 计算、时间依赖、活动度概念")
        print("2. live2d_manager.py: 移除 30fps 轮询，改为事件驱动")
        print("3. 后端现在只发送'干巴巴的目标值'，所有平滑动画由前端处理")
        return 0
    else:
        print("[FAIL] 测试失败！请修复问题。")
        return 1


if __name__ == "__main__":
    sys.exit(main())