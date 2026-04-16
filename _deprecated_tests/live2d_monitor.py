#!/usr/bin/env python3
"""
Live2D 参数实时监控器
实时显示Live2D参数变化，观察系统行为
运行: python live2d_monitor.py
"""

import time
import threading
import sys
from datetime import datetime
from live2d.live2d_manager import Live2DManager

class Live2DMonitor:
    def __init__(self, update_interval=0.1, history_size=50):
        """
        初始化监控器

        Args:
            update_interval: 更新间隔（秒）
            history_size: 历史记录大小
        """
        # 获取Live2D管理器实例
        self.live2d = Live2DManager()
        self.live2d.start()

        # 监控设置
        self.update_interval = update_interval
        self.history_size = history_size

        # 数据存储
        self.param_history = []
        self.is_running = False

        # 统计数据
        self.start_time = None
        self.update_count = 0

        # 显示配置
        self.display_config = {
            "show_all": False,           # 显示所有参数
            "show_changes": True,        # 显示变化值
            "show_stats": True,          # 显示统计信息
            "show_trend": True,          # 显示趋势
            "refresh_rate": 10,          # 刷新率（次/秒）
        }

        print("=" * 80)
        print("Live2D 参数实时监控器 v1.0")
        print("=" * 80)
        print(f"监控间隔: {update_interval:.3f}s")
        print(f"历史记录: {history_size} 个点")
        print("按 Ctrl+C 停止监控")
        print("=" * 80)

    def start_monitoring(self):
        """开始监控"""
        self.start_time = time.time()
        self.is_running = True

        # 启动监控线程
        monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        monitor_thread.start()

        # 启动显示线程
        display_thread = threading.Thread(target=self._display_loop, daemon=True)
        display_thread.start()

        try:
            # 主线程等待结束
            while self.is_running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop_monitoring()

    def _monitor_loop(self):
        """监控循环 - 收集数据"""
        last_params = {}

        while self.is_running:
            try:
                # 获取当前参数
                t = time.time()
                current_params = self.live2d.animator.compute_params(t)

                # 计算变化值
                changes = {}
                if last_params:
                    for key in current_params:
                        if key in last_params:
                            changes[key] = current_params[key] - last_params[key]

                # 创建记录
                record = {
                    "timestamp": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "time": t,
                    "params": current_params.copy(),
                    "changes": changes.copy(),
                }

                # 添加到历史
                self.param_history.append(record)
                if len(self.param_history) > self.history_size:
                    self.param_history.pop(0)

                # 更新最后参数
                last_params = current_params.copy()

                self.update_count += 1

            except Exception as e:
                print(f"[监控错误] {e}")

            time.sleep(self.update_interval)

    def _display_loop(self):
        """显示循环 - 输出数据"""
        last_display_time = 0
        refresh_interval = 1.0 / self.display_config["refresh_rate"]

        while self.is_running:
            try:
                current_time = time.time()
                if current_time - last_display_time >= refresh_interval:
                    self._clear_screen()
                    self._display_header()
                    self._display_current_params()

                    if self.display_config["show_stats"]:
                        self._display_statistics()

                    if self.display_config["show_trend"] and len(self.param_history) > 1:
                        self._display_trends()

                    last_display_time = current_time

                time.sleep(0.01)  # 避免过度占用CPU

            except Exception as e:
                print(f"[显示错误] {e}")
                time.sleep(1)

    def _clear_screen(self):
        """清屏"""
        print("\033[2J\033[H", end="")

    def _display_header(self):
        """显示头部信息"""
        elapsed = time.time() - self.start_time if self.start_time else 0
        print("=" * 80)
        print(f"Live2D 参数监控 | 运行时间: {elapsed:.1f}s | 更新次数: {self.update_count}")
        print("=" * 80)

    def _display_current_params(self):
        """显示当前参数"""
        if not self.param_history:
            print("等待数据...")
            return

        latest = self.param_history[-1]

        print("\n📊 当前参数值:")
        print("-" * 80)

        # 分组显示
        groups = [
            ("👁️  眼部", ["eyeLeft", "eyeRight"]),
            ("👄 嘴巴", ["mouth"]),
            ("🧠 头部", ["headX", "headY", "headZ"]),
            ("💃 身体", ["bodyX", "bodyY", "bodyZ"]),
            ("💇 头发", ["hair"]),
            ("🤲 手臂", ["PartArmA", "PartArmB"]),
        ]

        for group_name, params in groups:
            print(f"\n{group_name}:")
            for param in params:
                if param in latest["params"]:
                    value = latest["params"][param]
                    change = latest["changes"].get(param, 0)

                    # 颜色编码
                    color_code = ""
                    if abs(change) > 0.1:
                        color_code = "\033[91m"  # 红色 - 大变化
                    elif abs(change) > 0.01:
                        color_code = "\033[93m"  # 黄色 - 中变化
                    elif abs(change) > 0.001:
                        color_code = "\033[92m"  # 绿色 - 小变化

                    reset_code = "\033[0m"

                    # 变化符号
                    change_symbol = "▲" if change > 0 else "▼" if change < 0 else " "

                    print(f"  {param:10} {value:7.3f} {color_code}{change_symbol}{change:+.3f}{reset_code}")

    def _display_statistics(self):
        """显示统计信息"""
        if len(self.param_history) < 2:
            return

        print("\n📈 统计信息:")
        print("-" * 80)

        # 计算每个参数的平均值和方差
        params_to_check = ["eyeLeft", "mouth", "headX", "bodyX", "hair"]

        for param in params_to_check:
            values = [record["params"].get(param, 0) for record in self.param_history if param in record["params"]]
            if not values:
                continue

            avg = sum(values) / len(values)
            variance = sum((v - avg) ** 2 for v in values) / len(values)

            # 判断活跃度
            if variance > 0.1:
                activity = "高活跃"
            elif variance > 0.01:
                activity = "中活跃"
            elif variance > 0.001:
                activity = "低活跃"
            else:
                activity = "静止"

            print(f"  {param:10} 平均:{avg:6.3f} 方差:{variance:6.3f} 状态:{activity}")

    def _display_trends(self):
        """显示趋势信息"""
        if len(self.param_history) < 10:
            return

        print("\n📉 近期趋势:")
        print("-" * 80)

        # 检查最近几个点的变化趋势
        recent = self.param_history[-10:]

        trends = {}
        for i in range(len(recent) - 1):
            current = recent[i + 1]["params"]
            previous = recent[i]["params"]

            for key in current:
                if key in previous:
                    change = current[key] - previous[key]
                    trends[key] = trends.get(key, 0) + change

        # 显示主要趋势
        significant_trends = {k: v for k, v in trends.items() if abs(v) > 0.05}

        if significant_trends:
            for param, trend in sorted(significant_trends.items(), key=lambda x: abs(x[1]), reverse=True)[:5]:
                direction = "上升" if trend > 0 else "下降"
                print(f"  {param:10} {direction:4} 趋势强度:{abs(trend):.3f}")
        else:
            print("  无明显趋势变化")

        # 显示模式信息
        try:
            mode = self.live2d.animator.mode
            activity = self.live2d.animator.activity_smooth
            print(f"\n  🎭 当前模式: {mode} (活动度: {activity:.2f})")

            # 检查是否有外部控制
            has_external_control = any([
                self.live2d.animator._target_head_x is not None,
                self.live2d.animator._target_head_y is not None,
                self.live2d.animator._target_head_z is not None,
                self.live2d.animator._target_mouth is not None,
            ])

            if has_external_control:
                print("  ⚙️  检测到外部参数控制")
            else:
                print("  🤖 完全算法控制")

        except Exception as e:
            print(f"  模式信息获取失败: {e}")

    def stop_monitoring(self):
        """停止监控"""
        self.is_running = False

        # 显示最终统计
        print("\n" + "=" * 80)
        print("监控结束 - 最终统计")
        print("=" * 80)

        elapsed = time.time() - self.start_time if self.start_time else 0
        print(f"总运行时间: {elapsed:.1f}秒")
        print(f"总更新次数: {self.update_count}")
        print(f"平均更新频率: {self.update_count / elapsed if elapsed > 0 else 0:.1f} Hz")

        if self.param_history:
            print(f"收集数据点: {len(self.param_history)}")

            # 显示参数范围
            print("\n参数范围统计:")
            all_params = {}
            for record in self.param_history:
                for key, value in record["params"].items():
                    if key not in all_params:
                        all_params[key] = {"min": value, "max": value}
                    else:
                        all_params[key]["min"] = min(all_params[key]["min"], value)
                        all_params[key]["max"] = max(all_params[key]["max"], value)

            for param, ranges in sorted(all_params.items()):
                range_width = ranges["max"] - ranges["min"]
                print(f"  {param:10} {ranges['min']:7.3f} ~ {ranges['max']:7.3f} (范围: {range_width:.3f})")

    def interactive_config(self):
        """交互式配置"""
        print("\n配置选项:")
        print("1. 显示所有参数: ", "✓" if self.display_config["show_all"] else "✗")
        print("2. 显示变化值: ", "✓" if self.display_config["show_changes"] else "✗")
        print("3. 显示统计信息: ", "✓" if self.display_config["show_stats"] else "✗")
        print("4. 显示趋势: ", "✓" if self.display_config["show_trend"] else "✗")
        print("5. 刷新率: ", f"{self.display_config['refresh_rate']} Hz")

        choice = input("\n输入选项编号修改 (或直接回车开始监控): ").strip()

        if choice == "1":
            self.display_config["show_all"] = not self.display_config["show_all"]
        elif choice == "2":
            self.display_config["show_changes"] = not self.display_config["show_changes"]
        elif choice == "3":
            self.display_config["show_stats"] = not self.display_config["show_stats"]
        elif choice == "4":
            self.display_config["show_trend"] = not self.display_config["show_trend"]
        elif choice == "5":
            try:
                rate = float(input("输入新的刷新率 (Hz): "))
                if 1 <= rate <= 60:
                    self.display_config["refresh_rate"] = rate
                else:
                    print("刷新率必须在1-60 Hz之间")
            except ValueError:
                print("无效的输入")

def main():
    """主函数"""
    print("Live2D 参数实时监控器")
    print("=" * 80)

    # 配置监控参数
    try:
        interval = float(input("监控间隔 (秒, 默认 0.1): ") or "0.1")
        history = int(input("历史记录大小 (默认 50): ") or "50")

        monitor = Live2DMonitor(update_interval=interval, history_size=history)

        # 询问是否配置显示选项
        config = input("是否配置显示选项? (y/N): ").strip().lower()
        if config == "y":
            monitor.interactive_config()

        print("\n开始监控...")
        monitor.start_monitoring()

    except KeyboardInterrupt:
        print("\n监控被用户中断")
    except ValueError as e:
        print(f"参数错误: {e}")
    except Exception as e:
        print(f"监控器启动失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()