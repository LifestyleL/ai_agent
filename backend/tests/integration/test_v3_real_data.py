#!/usr/bin/env python3
"""
V3.0 真实数据端到端测试
使用 agent_memory/short_term.json 中的真实短期记忆数据测试增量更新、索引去重等完整流程
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.core.long_term_memory.diary_writer import DiaryWriter
from backend.core.long_term_memory.manager import LongTermMemoryManager
from backend.core.deep_memory.manager import DeepMemoryManager


def print_section(title):
    """打印带格式的章节标题"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)


async def data_exploration():
    """第一步：数据探查，仅查看不修改"""
    print_section("第一步：数据探查")

    # 路径定义
    memory_root = project_root / "backend" / "agent_memory"
    short_term_path = memory_root / "short_term.json"
    diary_dir = memory_root / "diary" / "daily"
    long_term_index_dir = memory_root / "long_term_index"
    deep_index_dir = memory_root / "deep_index"

    # 1. 检查 short_term.json 结构
    print(f"1. 检查短期记忆文件: {short_term_path}")
    if not short_term_path.exists():
        print("   [FAIL] 文件不存在")
        return False

    try:
        with open(short_term_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        print(f"   [OK] 文件存在，大小: {os.path.getsize(short_term_path)} 字节")

        # 检查结构
        if "dialogues" in data:
            dialogues = data.get("dialogues", [])
            print(f"   - dialogues 字段: {len(dialogues)} 条记录")

            # 显示前3条样例
            print(f"   - 前3条记录样例:")
            for i, item in enumerate(dialogues[:3]):
                if isinstance(item, dict):
                    role = item.get("role", "unknown")
                    content = item.get("content", "")[:50]
                    timestamp = item.get("timestamp", "")
                    print(f"     {i+1}. role={role}, content='{content}...', timestamp={timestamp}")

        if "current_emotion" in data:
            emotion = data.get("current_emotion", {})
            print(f"   - current_emotion: {emotion}")

        if "updated_at" in data:
            print(f"   - updated_at: {data.get('updated_at')}")

    except Exception as e:
        print(f"   [FAIL] 读取失败: {e}")
        return False

    # 2. 按日期统计短期记忆
    print(f"\n2. 按日期统计短期记忆:")
    dates_to_check = ["2026-04-14", "2026-04-15", "2026-04-16", "2026-04-17", "2026-04-18"]

    if "dialogues" in data:
        dialogues = data.get("dialogues", [])
        for date_str in dates_to_check:
            count = 0
            for item in dialogues:
                if isinstance(item, dict):
                    timestamp = item.get("timestamp", "")
                    if timestamp.startswith(date_str):
                        count += 1
            print(f"   - {date_str}: {count} 条记录")
    else:
        print("   [FAIL] 没有 dialogues 字段")

    # 3. 检查日记目录
    print(f"\n3. 检查日记目录: {diary_dir}")
    if diary_dir.exists():
        md_files = list(diary_dir.glob("*.md"))
        print(f"   - 现有日记文件: {len(md_files)} 个")
        for md_file in sorted(md_files)[:5]:  # 显示最多5个
            print(f"     - {md_file.name} ({os.path.getsize(md_file)} 字节)")
    else:
        print("   [FAIL] 目录不存在")

    # 4. 检查长期记忆索引
    print(f"\n4. 检查长期记忆索引目录: {long_term_index_dir}")
    if long_term_index_dir.exists():
        files = list(long_term_index_dir.glob("*"))
        print(f"   - 文件数量: {len(files)}")
        for f in files:
            size = os.path.getsize(f) if f.is_file() else "dir"
            print(f"     - {f.name} ({size})")
    else:
        print("   [FAIL] 目录不存在")

    # 5. 检查深度记忆索引
    print(f"\n5. 检查深度记忆索引目录: {deep_index_dir}")
    if deep_index_dir.exists():
        files = list(deep_index_dir.glob("*"))
        print(f"   - 文件数量: {len(files)}")
        for f in files:
            size = os.path.getsize(f) if f.is_file() else "dir"
            print(f"     - {f.name} ({size})")
    else:
        print("   [FAIL] 目录不存在")

    print("\n" + "="*60)
    print("数据探查完成，请检查以上信息是否正常")
    print("="*60)

    return True


async def main():
    """主测试函数"""
    print_section("V3.0 真实数据端到端测试")

    # 先执行数据探查
    success = await data_exploration()
    if not success:
        print("数据探查失败，终止测试")
        return False

    print("\n\n下一步计划:")
    print("1. 配置有效的 DeepSeek API 密钥")
    print("2. 执行 14 号日记生成")
    print("3. 归档 14 号到索引")
    print("4. 自动执行 15 号和 16 号")
    print("5. 增量更新测试（17 号）")
    print("6. 最终验证（主动查询 + 深度回忆）")

    print("\n[WARN] 请确认以上探查结果正常，然后继续执行后续测试。")
    print("   在继续之前，请确保:")
    print("   - DeepSeek API 密钥有效")
    print("   - short_term.json 中有 14-17 号的数据")
    print("   - 了解后续步骤会修改 short_term.json（删除已处理的条目）")

    return True


if __name__ == "__main__":
    # 仅执行数据探查，等待用户确认后再继续
    asyncio.run(main())