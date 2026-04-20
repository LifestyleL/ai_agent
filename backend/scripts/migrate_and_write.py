#!/usr/bin/env python3
"""
历史数据清洗并直接写入脚本
用于确认写入操作
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 直接导入 HistoricalMemoryMigrator 类
import importlib.util
spec = importlib.util.spec_from_file_location(
    "migrate_historical_memory",
    os.path.join(os.path.dirname(__file__), "migrate_historical_memory.py")
)
migrate_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migrate_module)
HistoricalMemoryMigrator = migrate_module.HistoricalMemoryMigrator


def main():
    """主函数 - 直接执行写入"""
    migrator = HistoricalMemoryMigrator()

    print("[确认模式] 直接写入清洗后的数据")
    print("=" * 60)

    # 执行并写入
    success = migrator.run(write_file=True)
    if not success:
        print("[ERROR] 清洗写入失败")
        sys.exit(1)

    print("\n[SUCCESS] 清洗写入完成！")
    print(f"已写入 agent_memory/short_term.json")

    # 显示写入后的文件信息
    import json
    from pathlib import Path

    target_path = Path(__file__).parent.parent / "agent_memory" / "short_term.json"
    if target_path.exists():
        with open(target_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"当前文件包含 {len(data.get('dialogues', []))} 条对话")


if __name__ == "__main__":
    main()