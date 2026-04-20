#!/usr/bin/env python3
"""
测试自驱动引擎初始化
"""
import sys
import os
import time

# 模拟 main.py 的路径设置
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

print("="*50)
print("测试自驱动引擎初始化")
print("="*50)

try:
    from backend.core.agent.agent_driver import YumeDriver
    print("[OK] 导入 YumeDriver 成功")

    driver = YumeDriver()
    print("[OK] YumeDriver 实例化成功")

    # 检查自驱动引擎
    if hasattr(driver, 'spontaneous_engine') and driver.spontaneous_engine:
        print("[OK] 自驱动引擎初始化成功")
        print(f"    引擎状态: is_running={driver.spontaneous_engine.is_running}")
    else:
        print("[WARN] 自驱动引擎初始化失败或未启用")

    # 启动 driver（包括自驱动引擎）
    driver.start()
    print("[OK] Driver 启动成功")

    # 等待几秒，观察日志
    print("等待 3 秒观察日志...")
    time.sleep(3)

    # 关闭
    driver.shutdown()
    print("[OK] Driver 关闭成功")

except Exception as e:
    print(f"[ERROR] 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("="*50)
print("测试完成")
print("="*50)