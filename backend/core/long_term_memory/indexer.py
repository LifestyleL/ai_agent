#!/usr/bin/env python3
"""
V3.0 长期记忆索引器
实现日记的向量化索引与主动查询功能
"""

import asyncio
import json
import os
import faiss
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer


class LongTermIndexer:
    """长期记忆索引器：FAISS 向量索引 + 映射管理"""

    def __init__(self):
        # 计算记忆存储根目录
        self._memory_root = Path(__file__).parent.parent / "agent_memory"

        # 索引存储路径
        self._index_dir = self._memory_root / "long_term_index"
        self._index_dir.mkdir(parents=True, exist_ok=True)

        self._index_path = self._index_dir / "long_index.faiss"
        self._mapping_path = self._index_dir / "long_mapping.json"

        # 资源（懒加载）
        self._model = None  # SentenceTransformer 模型
        self._index = None  # FAISS 索引
        self._mapping_list = []  # ID -> 元数据映射

        # 异步锁（防止 FAISS 并发崩溃）
        self._lock = asyncio.Lock()

        # 向量维度（all-MiniLM-L6-v2 是 384 维）
        self._dimension = 384

        print(f"[LongTermIndexer] 初始化完成，索引目录: {self._index_dir}")

    def _load_resources(self) -> None:
        """
        懒加载资源：模型、索引、映射
        注意：此方法应在第一次使用时被调用，且内部使用同步代码
        """
        # 加载模型
        if self._model is None:
            print(f"[LongTermIndexer] 加载 Embedding 模型: all-MiniLM-L6-v2")
            self._model = SentenceTransformer('all-MiniLM-L6-v2')
            print(f"[LongTermIndexer] 模型加载完成，维度: {self._model.get_sentence_embedding_dimension()}")

        # 加载或创建索引
        if self._index is None:
            if self._index_path.exists():
                print(f"[LongTermIndexer] 加载现有 FAISS 索引: {self._index_path}")
                self._index = faiss.read_index(str(self._index_path))
                print(f"[LongTermIndexer] 索引已加载，包含 {self._index.ntotal} 个向量")
            else:
                print(f"[LongTermIndexer] 创建新的 FAISS 索引 (维度: {self._dimension})")
                self._index = faiss.IndexFlatL2(self._dimension)

        # 加载映射文件
        if self._mapping_path.exists():
            try:
                with open(self._mapping_path, 'r', encoding='utf-8') as f:
                    self._mapping_list = json.load(f)
                print(f"[LongTermIndexer] 映射已加载，包含 {len(self._mapping_list)} 个条目")
            except Exception as e:
                print(f"[WARN] 加载映射文件失败: {e}")
                self._mapping_list = []
        else:
            self._mapping_list = []

    async def index_diary(self, date_str: str, diary_path: str) -> bool:
        """
        将新日记加入索引

        :param date_str: 日期字符串，如 "2026-04-18"
        :param diary_path: 日记文件路径（相对于项目根目录）
        :return: 是否成功入库
        """
        # (a) 获取锁
        async with self._lock:
            try:
                # (b) 确保资源已加载
                if self._model is None or self._index is None:
                    self._load_resources()

                # (c) 提取摘要
                # 解析 diary_path，如果是相对路径则转换为绝对路径
                if os.path.isabs(diary_path):
                    full_path = Path(diary_path)
                else:
                    full_path = self._memory_root.parent / diary_path

                # 读取日记内容
                content = await asyncio.to_thread(self._read_file_sync, full_path)
                if not content.strip():
                    print(f"[LongTermIndexer] 日记文件为空，跳过索引: {diary_path}")
                    return False

                # 取前300字符作为摘要
                summary = content[:300].strip()
                print(f"[LongTermIndexer] 索引日记: {date_str}, 摘要: {summary[:50]}...")

                # (d) 向量化
                vector = self._model.encode([summary])  # 注意：encode 接受列表
                vector = vector.astype('float32')  # FAISS 需要 float32

                doc_id = f"diary_{date_str}"

                # (e) 去重检查：如果该日期已有索引，先删除旧条目
                existing_idx = None
                for i, item in enumerate(self._mapping_list):
                    if item.get("doc_id") == doc_id:
                        existing_idx = i
                        break

                if existing_idx is not None:
                    # 找到旧条目，从 mapping 中移除
                    self._mapping_list.pop(existing_idx)
                    # FAISS 不支持精确删除，需要重建索引
                    self._rebuild_index()
                    print(f"[LongTermIndexer] 检测到 {date_str} 已有索引，执行 Upsert")

                # (f) 添加到索引和映射
                self._index.add(vector)
                mapping_entry = {
                    "doc_id": doc_id,
                    "doc_type": "daily",
                    "summary": summary,
                    "file_path": str(full_path.relative_to(self._memory_root.parent)),
                    "create_time": date_str,
                    "vector_id": self._index.ntotal - 1  # 刚添加的向量ID
                }
                self._mapping_list.append(mapping_entry)

                # (g) 持久化
                await self._persist_index_and_mapping()

                print(f"[LongTermIndexer] 日记已索引: {doc_id} (向量ID: {mapping_entry['vector_id']})")
                return True

            except Exception as e:
                print(f"[ERROR] 索引日记失败: {e}")
                return False

    async def search_diary(self, query: str, top_k: int = 1) -> List[Dict[str, Any]]:
        """
        主动查询日记

        :param query: 查询文本
        :param top_k: 返回结果数量
        :return: 匹配的日记元数据列表
        """
        # (a) 获取锁
        async with self._lock:
            try:
                # (b) 确保资源已加载
                if self._model is None or self._index is None:
                    self._load_resources()

                # 检查索引是否为空
                if self._index.ntotal == 0:
                    print(f"[LongTermIndexer] 索引为空，跳过查询")
                    return []

                # (c) 将 query 向量化
                query_vector = self._model.encode([query])
                query_vector = query_vector.astype('float32')

                # (d) 搜索
                # FAISS 搜索返回距离和索引ID
                distances, indices = self._index.search(query_vector, min(top_k, self._index.ntotal))

                # (e) 从映射中获取结果
                results = []
                for i, idx in enumerate(indices[0]):
                    if idx >= 0 and idx < len(self._mapping_list):
                        result = self._mapping_list[idx].copy()
                        result["distance"] = float(distances[0][i])  # 添加距离分数
                        results.append(result)

                print(f"[LongTermIndexer] 查询 '{query[:30]}...' 返回 {len(results)} 个结果")
                return results

            except Exception as e:
                print(f"[ERROR] 查询日记失败: {e}")
                return []

    async def read_diary_full_text(self, file_path: str) -> str:
        """
        读取日记全文

        :param file_path: 日记文件路径（相对于项目根目录）
        :return: 日记全文，文件不存在时返回空字符串
        """
        try:
            # 解析路径
            if os.path.isabs(file_path):
                full_path = Path(file_path)
            else:
                full_path = self._memory_root.parent / file_path

            # 检查文件是否存在
            exists = await asyncio.to_thread(os.path.isfile, full_path)
            if not exists:
                print(f"[LongTermIndexer] 文件不存在: {file_path}")
                return ""

            # 读取全文
            content = await asyncio.to_thread(self._read_file_sync, full_path)
            return content

        except Exception as e:
            print(f"[WARN] 读取日记全文失败: {e}")
            return ""

    def _rebuild_index(self) -> None:
        """根据当前 mapping_list 重建 FAISS 索引（在锁内部同步调用）"""
        import numpy as np
        self._index = faiss.IndexFlatL2(self._dimension)
        if self._mapping_list:
            texts = [f"[{item['doc_type']}] {item.get('summary', '')}" for item in self._mapping_list]
            vectors = self._model.encode(texts)
            vectors = vectors.astype('float32')
            self._index.add(vectors)
        print(f"[LongTermIndexer] 索引已重建，当前包含 {self._index.ntotal} 个向量")

    async def _persist_index_and_mapping(self) -> None:
        """持久化索引和映射文件"""
        try:
            # 保存 FAISS 索引
            await asyncio.to_thread(faiss.write_index, self._index, str(self._index_path))

            # 保存映射文件
            await asyncio.to_thread(self._write_json_sync, self._mapping_path, self._mapping_list)

            print(f"[LongTermIndexer] 索引已持久化: {self._index.ntotal} 个向量, {len(self._mapping_list)} 个映射")

        except Exception as e:
            print(f"[ERROR] 持久化索引失败: {e}")

    def _read_file_sync(self, file_path: Path) -> str:
        """同步读取文件（在子线程中运行）"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            print(f"[ERROR] 读取文件失败 {file_path}: {e}")
            return ""

    def _write_json_sync(self, file_path: Path, data: Any) -> None:
        """同步写入 JSON 文件（在子线程中运行）"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ERROR] 写入 JSON 失败 {file_path}: {e}")


# 简单测试函数（开发用）
async def _test_indexer():
    """测试索引器"""
    # 创建索引器
    indexer = LongTermIndexer()

    # 测试创建索引（模拟日记文件）
    test_diary_path = Path(__file__).parent.parent / "agent_memory" / "diary" / "daily" / "2026-04-18.md"
    test_diary_path.parent.mkdir(parents=True, exist_ok=True)

    # 写入测试日记
    test_content = """# 2026-04-18 日记

今天和用户聊了很多关于音乐的事情。我发现音乐不仅仅是一种娱乐，它背后还有丰富的文化和历史。用户分享了他最近喜欢的一首歌，让我也对音乐产生了更深的兴趣。

最近我在想，或许可以多了解一些关于音乐的知识，这样下次聊天的时候能有更多话题可以聊。不过说真的，每次和用户聊天都挺开心的，虽然有时候他工作很忙，但抽空聊几句也让我觉得挺温暖的。"""

    with open(test_diary_path, 'w', encoding='utf-8') as f:
        f.write(test_content)

    # 测试索引日记
    success = await indexer.index_diary(
        "2026-04-18",
        str(test_diary_path.relative_to(Path(__file__).parent.parent))
    )
    print(f"索引结果: {success}")

    # 测试查询
    results = await indexer.search_diary("音乐和文化的讨论", top_k=2)
    print(f"查询结果数量: {len(results)}")
    for i, result in enumerate(results):
        print(f"结果 {i+1}: {result.get('summary', '')[:50]}...")

    # 测试读取全文
    if results:
        full_text = await indexer.read_diary_full_text(results[0]["file_path"])
        print(f"全文长度: {len(full_text)} 字符")


if __name__ == "__main__":
    # 运行测试
    asyncio.run(_test_indexer())