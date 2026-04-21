#!/usr/bin/env python3
"""
初始化测试 - 只测试初始化，不启动服务
"""
import sys
import os

# 设置路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

print("=" * 60)
print("初始化测试")
print("=" * 60)

try:
    # 导入必要的模块
    from backend.agent_shell import AgentShell

    # 创建AgentShell实例
    print("[1] 创建 AgentShell 实例...")
    shell = AgentShell(config_path=None)

    # 初始化子系统
    print("[2] 初始化子系统...")
    success = shell.initialize()

    if success:
        print("[OK] 子系统初始化成功")

        # 获取状态
        status = shell.get_status()
        print(f"状态: running={status['running']}")
        print(f"状态机: {status['state_machine']}")

        # 测试Skill（异步）
        import asyncio
        print("[3] 测试Skill执行...")

        async def test_skill():
            await shell._test_skill_execution()

        asyncio.run(test_skill())

        print("=" * 60)
        print("[OK] 初始化测试通过")
        print("=" * 60)
    else:
        print("[FAIL] 子系统初始化失败")
        sys.exit(1)

except Exception as e:
    print(f"[FAIL] 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)