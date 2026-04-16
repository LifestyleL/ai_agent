#!/usr/bin/env python3
"""
Live2D 参数调试器
用于实时监控和调整Live2D动画参数
运行: python live2d_debug.py
"""

import time
import threading
import json
import asyncio
from queue import Queue, Empty
from datetime import datetime
from live2d.live2d_manager import Live2DManager

# 尝试导入websockets库
try:
    import websockets
    WEBSOCKET_AVAILABLE = True
except ImportError:
    print("[警告] websockets库未安装，直接WebSocket功能不可用")
    print("安装: pip install websockets")
    WEBSOCKET_AVAILABLE = False

class Live2DWebSocketClient:
    """简单的WebSocket客户端，直接发送参数到前端"""
    def __init__(self, host="localhost", port=8765):
        self.host = host
        self.port = port
        self.websocket = None
        self.connected = False

    async def connect(self):
        """连接到WebSocket服务器"""
        if not WEBSOCKET_AVAILABLE:
            print("[错误] websockets库未安装，无法连接")
            return False

        try:
            print(f"正在连接到 ws://{self.host}:{self.port} ...")
            self.websocket = await websockets.connect(f"ws://{self.host}:{self.port}")
            self.connected = True
            print("[OK] WebSocket连接成功!")
            return True
        except Exception as e:
            print(f"[ERROR] WebSocket连接失败: {e}")
            print("请确保主系统已运行: python main.py")
            return False

    async def send_params(self, params_dict):
        """发送参数到前端"""
        if not self.connected or not self.websocket:
            print("未连接到WebSocket服务器")
            return False

        try:
            # 添加时间戳
            data = {
                "type": "PARAMS",
                "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "data": params_dict
            }
            await self.websocket.send(json.dumps(data))
            print(f"[send] 直接发送参数: {json.dumps(params_dict, indent=2)}")
            return True
        except Exception as e:
            print(f"[ERROR] 发送失败: {e}")
            return False

    async def close(self):
        """关闭连接"""
        if self.websocket:
            await self.websocket.close()
            self.connected = False
            print("WebSocket连接已关闭")


class Live2DDebugger:
    def __init__(self):
        # 获取Live2D管理器实例
        self.live2d = Live2DManager()
        self.live2d.start()

        # WebSocket客户端
        self.ws_client = Live2DWebSocketClient() if WEBSOCKET_AVAILABLE else None
        self.ws_connected = False

        # 参数历史记录
        self.param_history = []
        self.max_history = 200  # 最多记录200个数据点

        # 调试状态
        self.is_running = True
        self.last_params = {}

        # 消息队列
        self.message_queue = Queue()

        # 启动参数监控线程
        self._start_monitor_thread()

        # 尝试连接WebSocket
        if self.ws_client:
            self._connect_websocket()

        print("=" * 60)
        print("Live2D 参数调试器 v1.0")
        print("=" * 60)
        print(f"Live2D管理器已启动: {self.live2d}")
        if self.ws_client and self.ws_connected:
            print("[OK] WebSocket已连接，可直接控制前端Live2D")
        else:
            print("[警告]  WebSocket未连接，仅测试Animator逻辑")
        print("输入 'help' 查看可用命令")
        print("=" * 60)

    def _connect_websocket(self):
        """在后台线程中连接WebSocket"""
        def connect_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                success = loop.run_until_complete(self.ws_client.connect())
                if success:
                    self.ws_connected = True
            except Exception as e:
                print(f"WebSocket连接线程错误: {e}")
            finally:
                loop.close()

        thread = threading.Thread(target=connect_in_thread, daemon=True)
        thread.start()
        thread.join(timeout=2.0)  # 等待最多2秒连接

    def _direct_send_params(self, params_dict):
        """通过WebSocket直接发送参数到前端"""
        if not self.ws_client or not self.ws_connected:
            print("WebSocket未连接，无法直接发送")
            return False

        def send_in_thread():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                success = loop.run_until_complete(self.ws_client.send_params(params_dict))
                return success
            except Exception as e:
                print(f"直接发送参数错误: {e}")
                return False
            finally:
                loop.close()

        # 在新线程中发送
        thread = threading.Thread(target=send_in_thread, daemon=True)
        thread.start()
        thread.join(timeout=1.0)  # 等待最多1秒
        return True

    def _start_monitor_thread(self):
        """启动参数监控线程"""
        def monitor_loop():
            while self.is_running:
                try:
                    # 模拟计算参数（实际应该从animator获取）
                    t = time.time()
                    params = self.live2d.animator.compute_params(t)

                    # 记录参数历史
                    history_entry = {
                        "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                        "params": params.copy()
                    }
                    self.param_history.append(history_entry)

                    # 保持历史记录长度
                    if len(self.param_history) > self.max_history:
                        self.param_history.pop(0)

                    self.last_params = params

                    time.sleep(0.033)  # 约30fps
                except Exception as e:
                    print(f"[监控线程错误] {e}")
                    time.sleep(1)

        thread = threading.Thread(target=monitor_loop, daemon=True)
        thread.start()

    def print_current_params(self):
        """打印当前参数值"""
        if not self.last_params:
            print("尚无参数数据，请稍候...")
            return

        print("\n" + "=" * 60)
        print("当前Live2D参数值:")
        print("=" * 60)

        # 分组显示参数
        print("[eye]  眼部:")
        print(f"  eyeLeft:    {self.last_params.get('eyeLeft', 0):.3f}")
        print(f"  eyeRight:   {self.last_params.get('eyeRight', 0):.3f}")

        print("\n[mouth] 嘴巴:")
        print(f"  mouth:      {self.last_params.get('mouth', 0):.3f}")

        print("\n[head] 头部:")
        print(f"  headX:      {self.last_params.get('headX', 0):.3f}")
        print(f"  headY:      {self.last_params.get('headY', 0):.3f}")
        print(f"  headZ:      {self.last_params.get('headZ', 0):.3f}")

        print("\n[body] 身体:")
        print(f"  bodyX:      {self.last_params.get('bodyX', 0):.3f}")
        print(f"  bodyY:      {self.last_params.get('bodyY', 0):.3f}")
        print(f"  bodyZ:      {self.last_params.get('bodyZ', 0):.3f}")

        print("\n[hair] 头发:")
        print(f"  hair:       {self.last_params.get('hair', 0):.3f}")

        print("\n[arm] 手臂:")
        print(f"  PartArmA:   {self.last_params.get('PartArmA', 0):.3f}")
        print(f"  PartArmB:   {self.last_params.get('PartArmB', 0):.3f}")

        print("=" * 60)

    def print_param_ranges(self):
        """显示参数范围"""
        print("\n" + "=" * 60)
        print("Live2D参数范围限制:")
        print("=" * 60)
        print("参数        | 范围       | 描述")
        print("-" * 60)
        print("eyeLeft     | -1.0 ~ 1.0 | -1=前端眨眼, 0=闭眼, 1=睁眼")
        print("eyeRight    | -1.0 ~ 1.0 | -1=前端眨眼, 0=闭眼, 1=睁眼")
        print("mouth       |  0.0 ~ 1.0 | 0=闭嘴, 1=最大张嘴")
        print("headX       | -10.0 ~ 10.0 | 头部左右转动")
        print("headY       | -8.0 ~ 8.0   | 头部上下转动")
        print("headZ       | -5.0 ~ 5.0   | 头部倾斜")
        print("bodyX       | -1.0 ~ 1.0   | 身体左右摇摆")
        print("bodyY       | -0.5 ~ 0.5   | 身体上下俯仰")
        print("bodyZ       | -0.3 ~ 0.3   | 身体倾斜")
        print("hair        | -1.0 ~ 1.0   | 头发飘动")
        print("PartArmA    |  0.0 ~ 1.0   | 左手显示度")
        print("PartArmB    |  0.0 ~ 1.0   | 右手显示度")
        print("=" * 60)

    def set_parameter(self, param_name, value):
        """设置单个参数"""
        try:
            value = float(value)

            # 根据参数名调用相应的控制方法
            if param_name == "eyeLeft" or param_name == "eyeRight":
                # 眼睛需要特殊处理
                left = value if param_name == "eyeLeft" else None
                right = value if param_name == "eyeRight" else None
                self.live2d.set_eyes(left=left, right=right)
                print(f"设置 {param_name} = {value}")

            elif param_name == "mouth":
                self.live2d.set_mouth(value)
                print(f"设置 mouth = {value}")

            elif param_name == "headX":
                self.live2d.set_head(x=value)
                print(f"设置 headX = {value}")
            elif param_name == "headY":
                self.live2d.set_head(y=value)
                print(f"设置 headY = {value}")
            elif param_name == "headZ":
                self.live2d.set_head(z=value)
                print(f"设置 headZ = {value}")

            elif param_name == "bodyX":
                self.live2d.set_body(x=value)
                print(f"设置 bodyX = {value}")
            elif param_name == "bodyY":
                self.live2d.set_body(y=value)
                print(f"设置 bodyY = {value}")
            elif param_name == "bodyZ":
                self.live2d.set_body(z=value)
                print(f"设置 bodyZ = {value}")

            elif param_name == "hair":
                self.live2d.set_hair(value)
                print(f"设置 hair = {value}")

            elif param_name == "PartArmA":
                self.live2d.set_arms(arm_a=value)
                print(f"设置 PartArmA = {value}")
            elif param_name == "PartArmB":
                self.live2d.set_arms(arm_b=value)
                print(f"设置 PartArmB = {value}")

            else:
                print(f"未知参数: {param_name}")
                return False

            return True

        except ValueError:
            print(f"无效的数值: {value}")
            return False
        except Exception as e:
            print(f"设置参数失败: {e}")
            return False

    def test_animation(self, animation_name):
        """测试预设动画"""
        print(f"\n测试动画: {animation_name}")

        if animation_name == "nod":
            # 点头
            for i in range(3):
                self.live2d.set_head(y=-3)
                time.sleep(0.3)
                self.live2d.set_head(y=3)
                time.sleep(0.3)
            self.live2d.reset_control()

        elif animation_name == "shake":
            # 摇头
            for i in range(3):
                self.live2d.set_head(x=5)
                time.sleep(0.3)
                self.live2d.set_head(x=-5)
                time.sleep(0.3)
            self.live2d.reset_control()

        elif animation_name == "blink":
            # 眨眼测试
            self.live2d.set_eyes(left=0.2, right=0.2)
            time.sleep(0.2)
            self.live2d.set_eyes(left=-1, right=-1)  # 恢复前端眨眼

        elif animation_name == "speak":
            # 说话口型测试
            for i in range(5):
                self.live2d.set_mouth(0.8)
                time.sleep(0.1)
                self.live2d.set_mouth(0.3)
                time.sleep(0.1)
            self.live2d.reset_control()

        elif animation_name == "idle":
            # 空闲模式
            self.live2d.set_emotion_mode("idle")
            print("设置为 idle 模式")

        elif animation_name == "thinking":
            # 思考模式
            self.live2d.set_emotion_mode("thinking")
            print("设置为 thinking 模式")

        else:
            print(f"未知动画: {animation_name}")
            return False

        print(f"动画 {animation_name} 测试完成")
        return True

    def print_help(self):
        """显示帮助信息"""
        print("\n" + "=" * 60)
        print("Live2D 调试器命令")
        print("=" * 60)
        print("status     - 显示当前参数值")
        print("ranges     - 显示参数范围")
        print("history    - 显示参数历史")
        print("reset      - 重置所有控制（恢复算法生成）")
        print("auto       - 切换到自动模式（算法生成）")
        print("manual     - 切换到手动模式（外部控制）")
        print("mode <m>   - 设置模式 (idle/thinking)")
        print("activity <v> - 设置活动度 (0~1)")
        print("set <p> <v> - 设置参数值 (如: set headX 0.5)")
        print("test <a>   - 测试预设动画 (nod/shake/blink/speak/idle/thinking)")
        print("batch      - 批量设置参数")
        print("direct <p> <v> - 直接发送参数到前端 (如: direct headX 0.5)")
        print("save       - 保存当前配置")
        print("load       - 加载配置")
        print("help       - 显示此帮助")
        print("exit       - 退出调试器")
        print("=" * 60)

    def run_batch_setting(self):
        """批量设置参数"""
        print("\n批量设置参数 (输入 'done' 完成)")
        print("格式: <参数名> <值>")
        print("示例: headX 0.5")

        while True:
            try:
                cmd = input("batch> ").strip()
                if not cmd:
                    continue

                if cmd.lower() == "done":
                    break

                parts = cmd.split()
                if len(parts) != 2:
                    print("格式错误，应为: <参数名> <值>")
                    continue

                param_name, value_str = parts
                self.set_parameter(param_name, value_str)

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"错误: {e}")

    def run(self):
        """运行调试器主循环"""
        while self.is_running:
            try:
                cmd = input("\ndebug> ").strip().lower()
                if not cmd:
                    continue

                parts = cmd.split()
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

                elif command == "ranges":
                    self.print_param_ranges()

                elif command == "reset":
                    self.live2d.reset_control()
                    print("已重置所有控制，恢复算法生成")

                elif command == "auto":
                    self.live2d.reset_control()
                    print("切换到自动模式（算法生成）")

                elif command == "manual":
                    print("已切换到手动模式（外部控制）")
                    print("使用 'set' 命令调整参数")

                elif command == "mode" and args:
                    mode = args[0]
                    if mode in ["idle", "thinking"]:
                        self.live2d.set_emotion_mode(mode)
                        print(f"设置为 {mode} 模式")
                    else:
                        print("模式必须是 'idle' 或 'thinking'")

                elif command == "activity" and args:
                    try:
                        activity = float(args[0])
                        if 0 <= activity <= 1:
                            self.live2d.set_activity(activity)
                            print(f"设置活动度: {activity}")
                        else:
                            print("活动度必须在 0~1 之间")
                    except ValueError:
                        print("无效的活动度值")

                elif command == "set" and len(args) >= 2:
                    param_name = args[0]
                    value = args[1]
                    self.set_parameter(param_name, value)

                elif command == "direct" and len(args) >= 2:
                    param_name = args[0]
                    value_str = args[1]
                    try:
                        value = float(value_str)
                        params_dict = {param_name: value}
                        self._direct_send_params(params_dict)
                    except ValueError:
                        print(f"无效的数值: {value_str}")

                elif command == "test" and args:
                    animation_name = args[0]
                    self.test_animation(animation_name)

                elif command == "batch":
                    self.run_batch_setting()

                elif command == "save":
                    self.save_config()

                elif command == "load":
                    self.load_config()

                else:
                    print(f"未知命令: {command}")
                    print("输入 'help' 查看可用命令")

            except KeyboardInterrupt:
                print("\n检测到Ctrl+C，退出调试器...")
                self.is_running = False
                break
            except Exception as e:
                print(f"命令执行错误: {e}")

    def close(self):
        """关闭调试器资源"""
        self.is_running = False
        if self.ws_client and self.ws_connected:
            def close_in_thread():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self.ws_client.close())
                except Exception as e:
                    print(f"关闭WebSocket连接错误: {e}")
                finally:
                    loop.close()
            thread = threading.Thread(target=close_in_thread, daemon=True)
            thread.start()
            thread.join(timeout=1.0)
        print("调试器资源已关闭")

    def save_config(self):
        """保存当前配置到文件"""
        try:
            config = {
                "mode": self.live2d.animator.mode,
                "activity": self.live2d.animator.activity_smooth,
                "targets": {
                    "head_x": self.live2d.animator._target_head_x,
                    "head_y": self.live2d.animator._target_head_y,
                    "head_z": self.live2d.animator._target_head_z,
                    "body_x": self.live2d.animator._target_body_x,
                    "body_y": self.live2d.animator._target_body_y,
                    "body_z": self.live2d.animator._target_body_z,
                    "mouth": self.live2d.animator._target_mouth,
                    "hair": self.live2d.animator._target_hair,
                    "eye_left": self.live2d.animator._target_eye_left,
                    "eye_right": self.live2d.animator._target_eye_right,
                    "arm_a": self.live2d.animator._target_arm_a,
                    "arm_b": self.live2d.animator._target_arm_b,
                    "activity": self.live2d.animator._target_activity,
                }
            }

            filename = f"live2d_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, "w") as f:
                json.dump(config, f, indent=2)

            print(f"配置已保存到: {filename}")

        except Exception as e:
            print(f"保存配置失败: {e}")

    def load_config(self):
        """从文件加载配置"""
        try:
            import os
            files = [f for f in os.listdir(".") if f.startswith("live2d_config_") and f.endswith(".json")]

            if not files:
                print("未找到配置文件")
                return

            print("\n可用配置文件:")
            for i, f in enumerate(sorted(files, reverse=True)[:10]):  # 显示最近10个
                print(f"  [{i}] {f}")

            choice = input("选择文件编号 (或输入文件名): ").strip()

            if choice.isdigit():
                idx = int(choice)
                if 0 <= idx < len(files):
                    filename = sorted(files, reverse=True)[idx]
                else:
                    print("无效的编号")
                    return
            else:
                filename = choice

            with open(filename, "r") as f:
                config = json.load(f)

            # 应用配置
            if "mode" in config:
                self.live2d.set_emotion_mode(config["mode"])

            if "activity" in config:
                self.live2d.set_activity(config["activity"])

            if "targets" in config:
                targets = config["targets"]
                # 这里可以逐个应用目标值，但需要更复杂的逻辑
                print("配置文件已加载，部分配置可能需要手动应用")

            print(f"配置已从 {filename} 加载")

        except Exception as e:
            print(f"加载配置失败: {e}")

def main():
    """主函数"""
    debugger = None
    try:
        debugger = Live2DDebugger()
        debugger.run()
    except KeyboardInterrupt:
        print("\n调试器已退出")
    except Exception as e:
        print(f"调试器启动失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if debugger:
            debugger.close()

if __name__ == "__main__":
    main()