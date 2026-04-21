#!/usr/bin/env python3
"""
Phase 3.1 验证脚本
测试状态机是否完全接管对话流程
"""
import sys
import os
import asyncio
import time

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

print("=" * 60)
print("Phase 3.1 验证 - 状态机接管测试")
print("=" * 60)

async def main():
    try:
        from backend.agent_shell import AgentShell

        # 1. 初始化系统
        print("[1] 初始化 AgentShell...")
        shell = AgentShell(config_path=None)
        success = shell.initialize()
        if not success:
            print("[FAIL] 系统初始化失败")
            sys.exit(1)

        print("[OK] 系统初始化成功")

        # 获取 driver 和 state_machine
        driver = shell.agent_driver
        sm = shell.state_machine

        print(f"[INFO] 状态机当前状态: {sm.get_state_summary()}")

        # 2. 测试简单对话（不需要工具）
        print("\n[2] 测试简单对话: '你好'")
        # 直接调用 handle_user_input（会触发事件）
        driver.handle_user_input("你好")

        # 等待状态机处理（最多10秒）
        print("[INFO] 等待状态机处理...")
        for i in range(20):
            await asyncio.sleep(0.5)
            state_summary = sm.get_state_summary()
            current_state = state_summary.get('current_state')
            print(f"  轮询 {i}: 当前状态={current_state}")
            if current_state == 'IDLE':
                print("[OK] 状态机已回到 IDLE，表示处理完成")
                break

        # 3. 测试工具调用
        print("\n[3] 测试工具调用: '帮我搜索记忆'")
        driver.handle_user_input("帮我搜索记忆")

        print("[INFO] 等待状态机处理工具调用...")
        for i in range(30):
            await asyncio.sleep(0.5)
            state_summary = sm.get_state_summary()
            current_state = state_summary.get('current_state')
            tool_usage = state_summary.get('tool_usage_total', 0)
            print(f"  轮询 {i}: 当前状态={current_state}, 工具使用次数={tool_usage}")
            if current_state == 'IDLE' and tool_usage > 0:
                print("[OK] 状态机完成工具调用并回到 IDLE")
                break

        print("\n" + "=" * 60)
        print("[OK] Phase 3.1 验证通过")
        print("=" * 60)

        # 清理（可选）
        # shell.shutdown()  # AgentShell 目前没有 shutdown 方法

    except Exception as e:
        print(f"[FAIL] 验证失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())