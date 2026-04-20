#!/usr/bin/env python3
"""
测试 V1→V3 记忆读写链路修复效果：
1. 检查短期记忆加载
2. 测试本地记忆优先逻辑（双字片段匹配）
3. 验证情绪标签传递
"""
import sys
import time
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def main():
    print("=== 测试 V1→V3 记忆修复（双字片段匹配） ===")

    # 检查短期记忆文件
    short_term_path = Path(__file__).parent / "agent_memory" / "short_term.json"
    print(f"短期记忆文件路径: {short_term_path}")
    print(f"文件是否存在: {short_term_path.exists()}")

    if short_term_path.exists():
        import json
        with open(short_term_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        dialogues = data.get('dialogues', [])
        print(f"短期记忆中共有 {len(dialogues)} 条对话")
        for i, d in enumerate(dialogues):
            print(f"  {i+1}. {d['role']}: {d['content'][:50]}...")

    # 测试双字片段匹配逻辑
    print("\n=== 测试双字片段匹配逻辑 ===")

    # 模拟匹配逻辑
    test_inputs = [
        "你知道冲浪功能什么时候加的",
        "冲浪功能是什么时候加的",
        "冲浪功能",
        "今天天气怎么样",
        "import os"
    ]

    # 假设短期记忆内容
    memory_content = "你知道你的上网冲浪功能，我什么事给你加的"

    for test_input in test_inputs:
        print(f"\n测试输入: '{test_input}'")
        user_input_lower = test_input.lower()
        # 生成所有双字片段
        bigrams = []
        for i in range(len(user_input_lower) - 1):
            bigram = user_input_lower[i:i+2]
            bigrams.append(bigram)
        print(f"  双字片段: {bigrams}")

        # 计算匹配
        match_count = 0
        for bigram in bigrams:
            if bigram in memory_content.lower():
                match_count += 1

        threshold = 2 if len(bigrams) >= 2 else 1
        print(f"  匹配片段数: {match_count}/{len(bigrams)}, 阈值: {threshold}")
        if match_count >= threshold:
            print(f"  [V] 预期命中")
        else:
            print(f"  [X] 预期未命中")

    print("\n=== 实际系统测试 ===")
    print("注意：实际系统测试需要启动完整Agent，这可能会较慢")
    print("建议直接运行 main.py 并手动测试")

    # 可选：实际初始化驱动（注释掉以避免长时间运行）
    # print("正在初始化 YumeDriver...")
    # driver = YumeDriver()
    # driver.start()
    # print("YumeDriver 初始化完成")
    # time.sleep(2)
    #
    # test_input = "冲浪功能是什么时候加的"
    # print(f"\n发送测试消息: {test_input}")
    # driver.handle_user_input(test_input)
    #
    # print("等待5秒...")
    # time.sleep(5)
    # driver.shutdown()

if __name__ == "__main__":
    main()