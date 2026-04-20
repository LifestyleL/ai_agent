#!/usr/bin/env python3
"""
恢复历史数据（重新导入）
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
    """恢复数据"""
    print("[INFO] 恢复历史数据...")
    migrator = HistoricalMemoryMigrator()

    # 直接写入
    success = migrator.run(write_file=True)
    if not success:
        print("[ERROR] 恢复失败")
        sys.exit(1)

    print("[SUCCESS] 历史数据已恢复")

    # 显示统计信息
    import json
    from pathlib import Path

    target_path = Path(__file__).parent.parent / "agent_memory" / "short_term.json"
    if target_path.exists():
        with open(target_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        dialogues = data.get("dialogues", [])
        print(f"当前 short_term.json 包含 {len(dialogues)} 条对话")

        # 按日期统计
        date_counts = {}
        for item in dialogues:
            if isinstance(item, dict):
                timestamp = item.get("timestamp", "")
                if timestamp:
                    date_str = timestamp[:10]
                    date_counts[date_str] = date_counts.get(date_str, 0) + 1

        print("按日期统计:")
        for date_str in sorted(date_counts.keys()):
            print(f"  {date_str}: {date_counts[date_str]} 条")


if __name__ == "__main__":
    main()