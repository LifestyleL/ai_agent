#!/usr/bin/env python3
"""
简单测试工具列表加载
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.core.memory_core import MemoryCore

def main():
    print("Testing tool list loading...")
    try:
        tools_json = MemoryCore.load_files(["tools/tools_index.md"])
        print(f"Tool list length: {len(tools_json)} chars")

        if tools_json and len(tools_json) > 0:
            print("[PASS] Tool list loaded successfully (chars > 0)")
            # Print first 200 chars
            preview = tools_json[:200] + ("..." if len(tools_json) > 200 else "")
            print(f"Preview: {preview}")
            return True
        else:
            print("[FAIL] Tool list is empty or whitespace")
            return False
    except Exception as e:
        print(f"[ERROR] Failed to load tool list: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)