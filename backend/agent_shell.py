#!/usr/bin/env python3
"""
AI Agent 主入口状态机外壳

集成状态机、插件管理器、记忆系统，提供统一的启动、运行、关闭接口。
"""

import asyncio
import signal
import sys
import time
from typing import Optional

from core.state_machine.state_machine import get_state_machine, State, Event
from core.state_machine.transitions import setup_base_transitions
from core.state_machine.actions import create_real_think_action, create_real_do_tool_action
from core.plugin_base import get_plugin_manager
from core.memory.memory_core import MemoryCore
from core.agent.agent_driver import YumeDriver
from backend.plugins.registry import get_global_registry
from backend.plugins.builtin.adapters import SearchMemoryAdapter, WriteFileAdapter
from backend.plugins.builtin.skills.memory_summary_skill import MemorySummarySkill


class AgentShell:
    """Agent外壳：集成所有子系统"""

    def __init__(self, config_path: Optional[str] = None):
        """
        初始化Agent外壳

        Args:
            config_path: 配置文件路径（可选）
        """
        print("=" * 60)
        print("AI Agent 状态机外壳启动")
        print("=" * 60)

        # 加载配置（如果提供了配置文件）
        self.config_path = config_path
        self.config = self._load_config()

        # 初始化核心组件
        self.state_machine = get_state_machine()
        self.plugin_manager = get_plugin_manager()
        self.memory_core = MemoryCore()
        self.agent_driver: Optional[YumeDriver] = None

        # 运行标志
        self.is_running = False

        # 注册信号处理
        self._setup_signal_handlers()

    def _load_config(self) -> dict:
        """加载配置"""
        # 这里可以扩展为从文件加载配置
        # 目前使用默认配置
        import config
        return {
            "app": {"debug": config.DEBUG},
            "websocket": {"port": config.WS_PORT},
            "memory": {
                "short_term_max_tokens": config.SHORT_TERM_MAX_TOKENS,
                "short_term_history_tokens": config.SHORT_TERM_HISTORY_TOKENS,
            },
            "agent": {
                "idle_timeout": config.AGENT_IDLE_TIMEOUT,
                "max_steps": config.MAX_STEPS,
            },
            "live2d": {"enabled": config.LIVE2D_ENABLED},
        }

    def _setup_signal_handlers(self):
        """设置信号处理"""
        signal.signal(signal.SIGINT, self._handle_shutdown_signal)
        signal.signal(signal.SIGTERM, self._handle_shutdown_signal)

    def _handle_shutdown_signal(self, signum, frame):
        """处理关闭信号"""
        print(f"\n收到关闭信号 {signum}，正在优雅关闭...")
        self.stop()

    def initialize(self) -> bool:
        """初始化所有子系统"""
        print("\n[初始化] 启动子系统初始化...")

        # 1. 初始化插件管理器
        print("[初始化] 1. 初始化插件管理器...")
        plugin_config = self.config.get("plugins", {})
        if not self.plugin_manager.initialize_all(plugin_config):
            print("[WARN] 插件管理器初始化有警告，但继续启动...")

        # 2. 初始化记忆系统（已通过MemoryCore构造函数初始化）
        print("[初始化] 2. 记忆系统就绪")

        # 3. 初始化状态机
        print("[初始化] 3. 状态机就绪")

        # 4. 初始化Agent驱动
        print("[初始化] 4. 初始化Agent驱动...")
        try:
            self.agent_driver = YumeDriver()
            print("[初始化] Agent驱动初始化成功")

            # 5. 配置状态机转移规则和Action（微观骨架模式）
            print("[初始化] 5. 配置状态机转移规则和Action（微观骨架模式）...")
            sm = self.state_machine
            # 设置基础转移规则
            setup_base_transitions(sm)

            # 5.1 工具系统插件化注册（提前，供微观 Action 使用）
            print("[初始化] 5.1 工具系统插件化注册...")
            reg = get_global_registry()
            reg.register(SearchMemoryAdapter())
            reg.register(WriteFileAdapter())
            # 将注册中心实例挂载到 driver 上（备用，暂不强制 driver 使用）
            self.agent_driver.tool_registry = reg
            print(f"[初始化] 工具注册完成，已注册 {len(reg.get_all_tools())} 个工具")

            # 5.2 绑定真实 Action 引擎
            print("[初始化] 5.2 绑定真实 Action 引擎...")
            # 暂时注释掉旧的宏观绑定
            # think_action = create_think_action(driver_instance=self.agent_driver, state_machine=sm)
            # sm.register_action(State.THINK, think_action)
            # 绑定真实引擎
            real_think = create_real_think_action(state_machine=sm, registry=reg, driver_instance=self.agent_driver)
            real_do_tool = create_real_do_tool_action(state_machine=sm, registry=reg)
            sm.register_action(State.THINK, real_think)
            sm.register_action(State.DO_TOOL, real_do_tool)
            print("[初始化] 真实 Action 绑定完成")

            # 将状态机挂载到driver实例，便于其他模块访问
            self.agent_driver.state_machine = sm

            print("[初始化] 状态机配置完成")
        except Exception as e:
            print(f"[ERROR] Agent驱动初始化失败: {e}")
            return False

        print("[初始化] 所有子系统初始化完成")
        return True

    async def _test_skill_execution(self):
        """启动时模拟执行一次 Skill，验证工具编排链路"""
        print("[Test] 开始模拟执行 MemorySummarySkill...")

        # 1. 从注册中心拿出刚才注册的两个适配器实例
        reg = get_global_registry()
        search_adapter = reg.get_tool("search_memory")
        write_adapter = reg.get_tool("write_file")

        if not search_adapter or not write_adapter:
            print("[Test] 缺少工具适配器，跳过 Skill 测试")
            return

        # 2. 实例化 Skill 并注入依赖
        skill = MemorySummarySkill(tools=[search_adapter, write_adapter])

        # 3. 模拟执行
        result = await skill.run(context={
            "query": "测试查询",
            "archive_path": "agent_memory/test_skill_output.txt"
        })

        print(f"[Test] Skill 模拟执行结果: {result}")

    def start(self) -> bool:
        """启动Agent"""
        if self.agent_driver is None:
            print("[ERROR] Agent驱动未初始化，请先调用 initialize()")
            return False

        print("\n[启动] 启动Agent...")
        try:
            self.agent_driver.start()
            self.is_running = True
            print("[启动] Agent已启动，等待用户输入...")

            # 在后台线程中执行 Skill 测试（不阻塞主流程）
            def run_skill_test():
                try:
                    # 创建新的事件循环用于测试
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(self._test_skill_execution())
                    loop.close()
                except Exception as e:
                    print(f"[Test] Skill 测试执行出错: {e}")

            import threading
            test_thread = threading.Thread(target=run_skill_test, daemon=True)
            test_thread.start()
            print("[Test] 已启动后台线程执行 Skill 连通性测试")

            return True
        except Exception as e:
            print(f"[ERROR] 启动Agent失败: {e}")
            return False

    def stop(self) -> None:
        """停止Agent"""
        if not self.is_running:
            return

        print("\n[关闭] 正在停止Agent...")
        self.is_running = False

        # 1. 停止Agent驱动
        if self.agent_driver:
            try:
                self.agent_driver.shutdown()
                print("[关闭] Agent驱动已停止")
            except Exception as e:
                print(f"[WARN] 停止Agent驱动时出错: {e}")

        # 2. 关闭插件管理器
        try:
            self.plugin_manager.shutdown_all()
            print("[关闭] 插件管理器已关闭")
        except Exception as e:
            print(f"[WARN] 关闭插件管理器时出错: {e}")

        # 3. 保存状态（可选）
        print("[关闭] Agent已完全停止")

    def run(self) -> None:
        """运行Agent（阻塞直到停止）"""
        if not self.initialize():
            print("[ERROR] 初始化失败，无法启动")
            return

        if not self.start():
            print("[ERROR] 启动失败")
            return

        print("\n" + "=" * 60)
        print("AI Agent 运行中...")
        print("按 Ctrl+C 停止")
        print("=" * 60)

        # 主循环（简单等待）
        try:
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n收到键盘中断")
        finally:
            self.stop()

    def get_status(self) -> dict:
        """获取系统状态"""
        return {
            "running": self.is_running,
            "state_machine": self.state_machine.get_state_summary(),
            "plugins": self.plugin_manager.get_all_status(),
            "memory": {
                "short_term_count": len(self.memory_core.get_short_term_memory()),
                "emotion": self.memory_core.get_current_emotion(),
            },
        }


def main():
    """主函数"""
    # 解析命令行参数（简单示例）
    config_path = None
    if len(sys.argv) > 1:
        config_path = sys.argv[1]

    # 创建并运行Agent外壳
    shell = AgentShell(config_path)
    shell.run()

    print("\n" + "=" * 60)
    print("AI Agent 已退出")
    print("=" * 60)


if __name__ == "__main__":
    main()