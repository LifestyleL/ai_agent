#!/usr/bin/env python3
"""
测试MemoryCore路径
"""
import sys
import os
from pathlib import Path

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.core.memory_core import MemoryCore

def test_paths():
    print("Testing MemoryCore paths...")

    # 检查agent_memory目录
    memory_root = Path(__file__).parent / "backend" / "agent_memory"
    print(f"Expected memory_root: {memory_root}")
    print(f"Exists: {memory_root.exists()}")

    # 检查tools目录
    tools_dir = memory_root / "tools"
    print(f"Tools dir: {tools_dir}")
    print(f"Exists: {tools_dir.exists()}")

    # 检查文件
    tool_index = tools_dir / "tools_index.md"
    print(f"Tool index: {tool_index}")
    print(f"Exists: {tool_index.exists()}")

    if tool_index.exists():
        try:
            with open(tool_index, 'r', encoding='utf-8') as f:
                content = f.read()
                print(f"File content length: {len(content)}")
                print(f"First 100 chars: {content[:100]}")
        except Exception as e:
            print(f"Error reading file: {e}")

    # 现在测试MemoryCore
    print("\nTesting MemoryCore.load_files(['tools/tools_index.md'])...")
    try:
        result = MemoryCore.load_files(["tools/tools_index.md"])
        print(f"Result length: {len(result)}")
        if len(result) > 0:
            print(f"First 100 chars of result: {result[:100]}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_paths()