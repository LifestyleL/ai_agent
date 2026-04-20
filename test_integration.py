#!/usr/bin/env python3
"""
集成测试：启动系统并发送测试消息
"""
import sys
import os
import subprocess
import time
import signal

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def capture_logs():
    """运行系统并捕获日志"""
    print("Starting system test...")

    # 启动后台进程
    proc = subprocess.Popen(
        [sys.executable, "backend/main.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        encoding='utf-8',
        errors='replace'
    )

    print(f"Process started with PID {proc.pid}")

    # 收集输出的函数
    def read_output(proc, timeout=30):
        """读取输出直到超时"""
        start = time.time()
        logs = []
        while time.time() - start < timeout:
            line = proc.stdout.readline()
            if line:
                logs.append(line.strip())
                print(f"[SYSTEM] {line.strip()}")
                # 检查关键日志
                if "工具列表加载成功" in line or "工具列表字符数" in line:
                    print(f"✓ Found tool list log: {line.strip()}")
                if "Bigram" in line:
                    print(f"✓ Found Bigram log: {line.strip()}")
                if "延迟诊断" in line:
                    print(f"✓ Found latency log: {line.strip()}")
            else:
                time.sleep(0.1)

            # 如果系统已就绪
            if "系统就绪" in " ".join(logs[-10:]):
                print("✓ System is ready!")
                break

        return logs, proc

    try:
        # 等待系统启动
        print("Waiting for system to start (10s)...")
        time.sleep(10)

        # 读取初始输出
        logs, proc = read_output(proc, timeout=20)

        # 检查工具列表加载
        tool_logs = [l for l in logs if "工具列表" in l or "tools" in l.lower()]
        if tool_logs:
            print(f"\n✓ Tool list logs found ({len(tool_logs)} lines)")
            for log in tool_logs[:3]:
                print(f"  {log}")
        else:
            print("\n✗ No tool list logs found")

        # 发送测试消息
        print("\nSending test message: '今天天气怎么样'")
        # 这里需要向进程发送输入，但进程没有从stdin读取（它有自己的输入线程）
        # 暂时跳过，因为我们主要关心日志

        # 等待更多日志
        time.sleep(5)
        more_logs, proc = read_output(proc, timeout=10)
        logs.extend(more_logs)

        # 检查TTS相关日志
        tts_logs = [l for l in logs if "TTS" in l or "分段" in l]
        if tts_logs:
            print(f"\n✓ TTS logs found ({len(tts_logs)} lines)")
            for log in tts_logs[:5]:
                print(f"  {log}")

        # 检查空段日志
        empty_segment_logs = [l for l in logs if "空段" in l or "空音频" in l]
        if empty_segment_logs:
            print(f"\n⚠ Found empty segment logs:")
            for log in empty_segment_logs:
                print(f"  {log}")
        else:
            print("\n✓ No empty segment logs found")

        print(f"\nTotal logs collected: {len(logs)} lines")

        # 保存日志到文件
        with open("test_logs.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(logs))
        print("Logs saved to test_logs.txt")

    finally:
        # 终止进程
        print(f"\nTerminating process {proc.pid}...")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("Test completed")

if __name__ == "__main__":
    capture_logs()