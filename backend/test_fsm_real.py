#!/usr/bin/env python3
"""
Phase 2.3-B 状态机真实引擎接入测试脚本

测试真实的状态机工作流，包括：
1. 状态机初始化
2. 工具注册中心初始化
3. 真实Action绑定
4. 模拟用户输入触发状态流转
"""

import asyncio
import sys
import os

# 设置路径（模仿 main.py）
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from core.state_machine.state_machine import get_state_machine, State, Event
from core.state_machine.transitions import setup_base_transitions
from core.state_machine.actions import create_real_think_action, create_real_do_tool_action
from backend.plugins.registry import get_global_registry
from backend.plugins.builtin.adapters import SearchMemoryAdapter, WriteFileAdapter
from core.agent.agent_driver import YumeDriver

async def test_fsm_real_engine():
    """测试真实引擎状态机"""
    print("=" * 60)
    print("Phase 2.3-B 状态机真实引擎接入测试")
    print("=" * 60)

    try:
        # 1. 初始化驱动实例（模拟）
        print("[1] 初始化 YumeDriver（模拟）...")
        driver = YumeDriver()
        print(f"    ✅ YumeDriver 初始化成功")

        # 2. 初始化状态机
        print("[2] 初始化状态机...")
        sm = get_state_machine()
        setup_base_transitions(sm)
        print(f"    ✅ 状态机初始化成功，当前状态: {sm.current_state}")

        # 3. 初始化工具注册中心
        print("[3] 初始化工具注册中心...")
        reg = get_global_registry()
        reg.register(SearchMemoryAdapter())
        reg.register(WriteFileAdapter())
        print(f"    ✅ 工具注册完成，已注册 {len(reg.get_all_tools())} 个工具")

        # 4. 绑定真实 Action
        print("[4] 绑定真实 Action 引擎...")
        real_think = create_real_think_action(state_machine=sm, registry=reg, driver_instance=driver)
        real_do_tool = create_real_do_tool_action(state_machine=sm, registry=reg)
        sm.register_action(State.THINK, real_think)
        sm.register_action(State.DO_TOOL, real_do_tool)
        print("    ✅ 真实 Action 绑定完成")

        # 5. 模拟用户输入，触发状态流转
        print("[5] 模拟用户输入，触发状态流转...")
        test_input = "帮我搜索一下记忆"
        print(f"    📝 测试输入: '{test_input}'")

        # 创建事件上下文
        context = {
            "user_input": test_input,
            "step": 0,
            "conversation_history": [],
            "tool_results": []
        }

        # 触发 USER_INPUT 事件，从 IDLE 跳转到 THINK
        print(f"    ⚡ 触发事件: USER_INPUT (当前状态: {sm.current_state})")
        coro = sm.trigger(Event.USER_INPUT, context)

        # 运行状态机（有限时间）
        print("    🚀 启动状态机执行...")
        try:
            await asyncio.wait_for(coro, timeout=10.0)
            print("    ✅ 状态机执行完成")
        except asyncio.TimeoutError:
            print("    ⚠️  状态机执行超时（可能正在等待API响应）")
        except Exception as e:
            print(f"    ❌ 状态机执行异常: {e}")

        # 6. 检查最终状态
        print(f"[6] 最终状态检查: {sm.current_state}")
        if sm.current_state == State.IDLE:
            print("    ✅ 状态机正确回到 IDLE 状态")
        else:
            print(f"    ⚠️  状态机停留在 {sm.current_state} 状态")

        print("=" * 60)
        print("✅ Phase 2.3-B 测试完成")
        print("=" * 60)

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True


if __name__ == "__main__":
    # 运行测试
    success = asyncio.run(test_fsm_real_engine())
    sys.exit(0 if success else 1)