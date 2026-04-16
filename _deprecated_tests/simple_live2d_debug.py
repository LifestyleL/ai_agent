#!/usr/bin/env python3
"""
简化版Live2D调试器
避免循环导入问题，直接测试Animator
"""

import time
import threading
import json
from datetime import datetime

# 直接导入animator，避免导入live2d_manager
try:
    from live2d.animator import Live2DAnimator
    print("[OK] 成功导入Live2DAnimator")
except ImportError as e:
    print(f"[ERROR] 导入失败: {e}")
    exit(1)

class SimpleLive2DDebugger:
    def __init__(self):
        # 创建Animator实例
        self.animator = Live2DAnimator()

        # 监控状态
        self.is_running = True
        self.last_params = {}
        self.param_history = []
        self.max_history = 100

        # 启动监控线程
        self._start_monitor_thread()

        print("=" * 60)
        print("简化版Live2D调试器 v1.0")
        print("=" * 60)
        print("注意: 此版本仅测试Animator，不包含WebSocket功能")
        print("输入 'help' 查看可用命令")
        print("=" * 60)

    def _start_monitor_thread(self):
        """启动参数监控线程"""
        def monitor_loop():
            while self.is_running:
                try:
                    t = time.time()
                    params = self.animator.compute_params(t)

                    # 记录历史
                    history_entry = {
                        "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                        "params": params.copy()
                    }
                    self.param_history.append(history_entry)

                    if len(self.param_history) > self.max_history:
                        self.param_history.pop(0)

                    self.last_params = params

                    time.sleep(0.1)  # 10Hz更新
                except Exception as e:
                    print(f"[监控错误] {e}")
                    time.sleep(1)

        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()

    def print_current_params(self):
        """打印当前参数"""
        if not self.last_params:
            print("等待数据...")
            return

        print("\n" + "=" * 60)
        print("当前Live2DAnimator参数:")
        print("=" * 60)

        params = self.last_params
        print(f"模式: {self.animator.mode}")
        print(f"活动度: {self.animator.activity_smooth:.3f}")

        print("\n关键参数:")
        print(f"  [eye] eyeLeft:  {params.get('eyeLeft', 0):.3f}")
        print(f"  [eye] eyeRight: {params.get('eyeRight', 0):.3f}")
        print(f"  [mouth] mouth:  {params.get('mouth', 0):.3f}")
        print(f"  [head] headX:   {params.get('headX', 0):.3f}")
        print(f"  [head] headY:   {params.get('headY', 0):.3f}")
        print(f"  [body] bodyX:   {params.get('bodyX', 0):.3f}")
        print(f"  [hair] hair:    {params.get('hair', 0):.3f}")
        print("=" * 60)

    def print_target_values(self):
        """打印目标值状态"""
        print("\n目标值状态 (None表示使用算法):")
        print("-" * 40)

        targets = [
            ("head_x", self.animator._target_head_x),
            ("head_y", self.animator._target_head_y),
            ("head_z", self.animator._target_head_z),
            ("body_x", self.animator._target_body_x),
            ("body_y", self.animator._target_body_y),
            ("body_z", self.animator._target_body_z),
            ("mouth", self.animator._target_mouth),
            ("hair", self.animator._target_hair),
            ("eye_left", self.animator._target_eye_left),
            ("eye_right", self.animator._target_eye_right),
            ("arm_a", self.animator._target_arm_a),
            ("arm_b", self.animator._target_arm_b),
            ("activity", self.animator._target_activity),
        ]

        for name, value in targets:
            status = "算法生成" if value is None else f"外部控制: {value:.3f}"
            print(f"  {name:12} {status}")

    def set_parameter(self, param_name, value_str):
        """设置参数"""
        try:
            value = float(value_str)

            if param_name == "headX":
                self.animator.set_head(x=value)
                print(f"设置 headX = {value}")
            elif param_name == "headY":
                self.animator.set_head(y=value)
                print(f"设置 headY = {value}")
            elif param_name == "headZ":
                self.animator.set_head(z=value)
                print(f"设置 headZ = {value}")
            elif param_name == "bodyX":
                self.animator.set_body(x=value)
                print(f"设置 bodyX = {value}")
            elif param_name == "bodyY":
                self.animator.set_body(y=value)
                print(f"设置 bodyY = {value}")
            elif param_name == "bodyZ":
                self.animator.set_body(z=value)
                print(f"设置 bodyZ = {value}")
            elif param_name == "mouth":
                self.animator.set_mouth(value)
                print(f"设置 mouth = {value}")
            elif param_name == "hair":
                self.animator.set_hair(value)
                print(f"设置 hair = {value}")
            elif param_name == "mode":
                if value_str in ["idle", "thinking"]:
                    self.animator.mode = value_str
                    print(f"设置模式 = {value_str}")
                else:
                    print("模式必须是 'idle' 或 'thinking'")
            elif param_name == "activity":
                self.animator.set_activity(value)
                print(f"设置活动度 = {value}")
            else:
                print(f"未知参数: {param_name}")
                return False

            return True

        except ValueError:
            print(f"无效的数值: {value_str}")
            return False
        except Exception as e:
            print(f"设置失败: {e}")
            return False

    def test_animation(self, name):
        """测试动画"""
        print(f"\n测试动画: {name}")

        if name == "nod":
            # 点头
            for i in range(3):
                self.animator.set_head(y=-3)
                time.sleep(0.3)
                self.animator.set_head(y=3)
                time.sleep(0.3)
            self.animator.reset_control()

        elif name == "shake":
            # 摇头
            for i in range(3):
                self.animator.set_head(x=5)
                time.sleep(0.3)
                self.animator.set_head(x=-5)
                time.sleep(0.3)
            self.animator.reset_control()

        elif name == "speak":
            # 说话
            for i in range(5):
                self.animator.set_mouth(0.8)
                time.sleep(0.1)
                self.animator.set_mouth(0.2)
                time.sleep(0.1)
            self.animator.reset_control()

        elif name == "reset":
            self.animator.reset_control()
            print("已重置所有控制")

        else:
            print(f"未知动画: {name}")
            return False

        print(f"动画 {name} 完成")
        return True

    def print_help(self):
        """显示帮助"""
        print("\n" + "=" * 60)
        print("可用命令")
        print("=" * 60)
        print("status      - 显示当前参数")
        print("targets     - 显示目标值状态")
        print("set <p> <v> - 设置参数 (如: set headX 0.5)")
        print("test <name> - 测试动画 (nod/shake/speak/reset)")
        print("mode <m>    - 设置模式 (idle/thinking)")
        print("activity <v>- 设置活动度 (0~1)")
        print("reset       - 重置控制")
        print("help        - 显示此帮助")
        print("exit        - 退出")
        print("=" * 60)
        print("可用参数: headX, headY, headZ, bodyX, bodyY, bodyZ")
        print("          mouth, hair, mode, activity")
        print("=" * 60)

    def run(self):
        """运行调试器"""
        while self.is_running:
            try:
                cmd = input("\ndebug> ").strip()
                if not cmd:
                    continue

                parts = cmd.lower().split()
                command = parts[0]
                args = parts[1:]

                if command == "exit" or command == "quit":
                    print("退出调试器...")
                    self.is_running = False
                    break

                elif command == "help":
                    self.print_help()

                elif command == "status":
                    self.print_current_params()

                elif command == "targets":
                    self.print_target_values()

                elif command == "reset":
                    self.animator.reset_control()
                    print("已重置所有控制")

                elif command == "set" and len(args) >= 2:
                    param_name = args[0]
                    value = args[1]
                    self.set_parameter(param_name, value)

                elif command == "test" and args:
                    self.test_animation(args[0])

                elif command == "mode" and args:
                    self.set_parameter("mode", args[0])

                elif command == "activity" and args:
                    self.set_parameter("activity", args[0])

                else:
                    print(f"未知命令: {command}")
                    print("输入 'help' 查看帮助")

            except KeyboardInterrupt:
                print("\n退出调试器...")
                self.is_running = False
                break
            except Exception as e:
                print(f"错误: {e}")

def main():
    """主函数"""
    print("简化版Live2D调试器")
    print("此工具仅测试Animator，用于验证控制接口")
    print("对于完整系统测试，请运行主系统后使用其他工具")
    print("=" * 60)

    try:
        debugger = SimpleLive2DDebugger()
        debugger.run()
    except KeyboardInterrupt:
        print("\n调试器已退出")
    except Exception as e:
        print(f"启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()