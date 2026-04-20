#!/usr/bin/env python3
"""快速测试模型加载"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from core.vector_memory import VectorMemory
import tempfile
import shutil
from pathlib import Path

print("测试 SentenceTransformer 模型加载...")
try:
    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    print(f"临时目录: {temp_dir}")

    # 创建 VectorMemory 实例
    vm = VectorMemory(model_name="all-MiniLM-L6-v2")

    # 修改存储目录为临时目录
    test_vector_root = Path(temp_dir) / "vector_db"
    test_vector_root.mkdir(parents=True, exist_ok=True)
    vm._vector_root = test_vector_root
    vm._index_path = test_vector_root / "faiss_index.index"
    vm._memory_path = test_vector_root / "vector_memory.json"

    # 尝试加载模型和索引
    print("正在加载模型和索引...")
    vm._load_model_and_index()

    print("✅ 模型加载成功！")
    print(f"模型维度: {vm._dimension}")
    print(f"索引已加载: {vm._index_loaded}")

    # 清理
    shutil.rmtree(temp_dir, ignore_errors=True)

except Exception as e:
    print(f"❌ 模型加载失败: {e}")
    import traceback
    traceback.print_exc()