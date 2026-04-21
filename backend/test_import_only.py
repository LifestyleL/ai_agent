#!/usr/bin/env python3
"""
最小导入测试
"""
import sys
import os

# 模仿 main.py 的路径设置
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

print(f"当前目录: {current_dir}")
print(f"父目录: {parent_dir}")
print(f"sys.path: {sys.path[:3]}")

try:
    # 测试关键导入
    from core.state_machine.actions import create_think_action
    print('PASS: create_think_action 导入成功')

    from core.state_machine.actions import create_real_think_action, create_real_do_tool_action
    print('PASS: 真实 Action 函数导入成功')

    from backend.plugins.registry import get_global_registry
    print('PASS: registry 导入成功')

    from config import WS_PORT, QWEN_API_KEY, DEEPSEEK_API_KEY
    print(f'PASS: 配置导入成功, WS_PORT={WS_PORT}')

    print('=' * 60)
    print('[OK] Phase 2.3-B 所有导入测试通过')
    print('=' * 60)

except Exception as e:
    print(f'FAIL: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)