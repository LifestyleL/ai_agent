"""
向量记忆管理模块
使用 FAISS 向量库和轻量级 SentenceTransformer 模型
实现条件触发检索与记忆入库
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import numpy as np


class VectorMemory:
    """向量记忆管理类，负责 FAISS 向量库的懒加载、入库和条件触发检索"""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        初始化向量记忆管理器
        :param model_name: SentenceTransformer 模型名称，默认使用轻量级模型
        """
        self.model_name = model_name
        self._model = None  # 懒加载的 Embedding 模型
        self._index = None  # FAISS 向量索引
        self._memory_items: List[Dict[str, Any]] = []  # 记忆映射列表
        self._index_loaded = False  # 索引是否已加载
        self._dimension = 384  # all-MiniLM-L6-v2 模型维度

        # 向量存储目录
        self._vector_root = Path(__file__).parent.parent / "agent_memory" / "vector_db"
        self._vector_root.mkdir(parents=True, exist_ok=True)

        # 文件路径
        self._index_path = self._vector_root / "faiss_index.index"
        self._memory_path = self._vector_root / "vector_memory.json"

    def _load_model_and_index(self) -> None:
        """
        懒加载模型和索引（第一次使用时加载）
        """
        if self._index_loaded:
            return

        try:
            # 懒加载 SentenceTransformer 模型
            if self._model is None:
                print(f"[VectorMemory] 加载 Embedding 模型: {self.model_name}")
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                # 验证模型维度
                test_embedding = self._model.encode(["test"])
                actual_dim = test_embedding.shape[1]
                if actual_dim != self._dimension:
                    print(f"[VectorMemory] 警告：模型维度为 {actual_dim}，调整为 {self._dimension}")
                    self._dimension = actual_dim

            # 加载或创建 FAISS 索引
            if self._index_path.exists():
                print("[VectorMemory] 加载已有 FAISS 索引")
                import faiss
                self._index = faiss.read_index(str(self._index_path))

                # 验证索引维度
                if self._index.d != self._dimension:
                    print(f"[VectorMemory] 警告：索引维度不匹配 ({self._index.d} != {self._dimension})，创建新索引")
                    # 维度不匹配，旧索引无效，创建新索引
                    self._index = faiss.IndexFlatL2(self._dimension)
                    # 备份旧索引文件
                    backup_index_path = self._index_path.with_suffix('.index.bak')
                    self._index_path.rename(backup_index_path)
                    print(f"[VectorMemory] 旧索引已备份到 {backup_index_path}")

                    # 备份旧记忆映射文件
                    if self._memory_path.exists():
                        backup_memory_path = self._memory_path.with_suffix('.json.bak')
                        self._memory_path.rename(backup_memory_path)
                        print(f"[VectorMemory] 旧记忆映射已备份到 {backup_memory_path}")
                        self._memory_items = []
                    else:
                        self._memory_items = []
                else:
                    # 维度匹配，正常加载记忆映射列表
                    if self._memory_path.exists():
                        with open(self._memory_path, 'r', encoding='utf-8') as f:
                            self._memory_items = json.load(f)
                        print(f"[VectorMemory] 加载 {len(self._memory_items)} 条向量记忆")
                    else:
                        self._memory_items = []
            else:
                print("[VectorMemory] 创建新的 FAISS 索引")
                import faiss
                self._index = faiss.IndexFlatL2(self._dimension)
                self._memory_items = []

            self._index_loaded = True
            print("[VectorMemory] 模型和索引加载完成")

        except Exception as e:
            print(f"[VectorMemory] 加载模型和索引失败: {e}")
            # 失败时创建空索引
            import faiss
            self._index = faiss.IndexFlatL2(self._dimension)
            self._memory_items = []
            self._index_loaded = True

    async def add_memory(self, memory_item: Dict[str, Any]) -> None:
        """
        添加记忆到向量库（异步）
        入库门槛：仅当 importance >= 5 时才入库
        :param memory_item: 记忆条目，需包含 id, content, emotion_type, scene_type, importance, create_time
        """
        try:
            # 检查重要性阈值
            importance = memory_item.get('importance', 0)
            if importance < 5:
                return  # 重要性不足，跳过入库

            # 确保模型和索引已加载
            self._load_model_and_index()

            content = memory_item.get('content', '')
            if not content.strip():
                print("[VectorMemory] 警告：记忆内容为空，跳过入库")
                return

            # 生成向量
            embedding = self._model.encode([content])
            vector = embedding.reshape(1, -1).astype('float32')

            # 添加到 FAISS 索引
            self._index.add(vector)

            # 添加到内存列表
            self._memory_items.append(memory_item)

            # 异步持久化
            await self._persist_memory()

            print(f"[VectorMemory] 记忆入库成功: {memory_item.get('id', '未知')}")

        except Exception as e:
            print(f"[VectorMemory] 记忆入库失败: {e}")

    async def _persist_memory(self) -> None:
        """异步持久化向量索引和记忆映射"""
        try:
            # 保存记忆映射列表
            await asyncio.to_thread(self._save_json, self._memory_path, self._memory_items)

            # 保存 FAISS 索引
            if self._index is not None:
                await asyncio.to_thread(self._save_index, self._index_path, self._index)

        except Exception as e:
            print(f"[VectorMemory] 持久化失败: {e}")

    def _save_json(self, file_path: Path, data: Any) -> None:
        """同步保存 JSON 文件"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _save_index(self, file_path: Path, index: Any) -> None:
        """同步保存 FAISS 索引"""
        import faiss
        faiss.write_index(index, str(file_path))

    def conditional_retrieve(
        self,
        current_emotion_type: int,
        current_emotion_strength: int,
        current_scene_type: str,
        query_text: str,
        top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """
        条件触发检索（门控检查 + FAISS 过滤）
        :param current_emotion_type: 当前情绪类型 (0-3)
        :param current_emotion_strength: 当前情绪强度 (0-10)
        :param current_scene_type: 当前场景类型 (A/B/C)
        :param query_text: 查询文本
        :param top_k: 返回结果数量
        :return: 符合条件的记忆列表
        """
        # 绝对红线：门控检查
        # 条件：情绪强度 >= 5 且场景类型为 B 时才触发检索
        if current_emotion_strength < 5 or current_scene_type != 'B':
            return []

        try:
            # 确保模型和索引已加载
            self._load_model_and_index()

            # 检查索引是否为空
            if self._index is None or self._index.ntotal == 0:
                return []

            # 生成查询向量
            query_embedding = self._model.encode([query_text])
            query_vector = query_embedding.reshape(1, -1).astype('float32')

            # FAISS 检索：先召回 top_k * 3 条结果
            retrieve_k = top_k * 3
            distances, indices = self._index.search(query_vector, min(retrieve_k, self._index.ntotal))

            # 获取检索结果的记忆条目
            retrieved_items = []
            for idx in indices[0]:
                if 0 <= idx < len(self._memory_items):
                    retrieved_items.append(self._memory_items[idx])

            if not retrieved_items:
                return []

            # 优先过滤：筛选出 emotion_type == current_emotion_type 的记忆
            same_emotion_items = [
                item for item in retrieved_items
                if item.get('emotion_type') == current_emotion_type
            ]

            # 如果同情绪的够 top_k 条，就返回这些
            if len(same_emotion_items) >= top_k:
                result = same_emotion_items[:top_k]
            else:
                # 如果不够，先用同情绪的，再用其他情绪的记忆补齐
                result = same_emotion_items.copy()
                remaining = top_k - len(result)

                # 从其他情绪的记忆中取
                other_emotion_items = [
                    item for item in retrieved_items
                    if item not in result
                ]
                result.extend(other_emotion_items[:remaining])

            # 简化返回格式
            simplified_result = []
            for item in result:
                simplified_result.append({
                    "content": item.get('content', ''),
                    "emotion_type": item.get('emotion_type', 0),
                    "scene_type": item.get('scene_type', 'A'),
                    "importance": item.get('importance', 1),
                    "create_time": item.get('create_time', '')
                })

            return simplified_result

        except Exception as e:
            print(f"[VectorMemory] 条件检索失败: {e}")
            return []

    async def get_stats(self) -> Dict[str, Any]:
        """获取向量库统计信息"""
        try:
            await self._load_model_and_index()

            stats = {
                "total_memories": len(self._memory_items),
                "index_size": self._index.ntotal if self._index else 0,
                "dimension": self._dimension,
                "model_name": self.model_name,
                "index_loaded": self._index_loaded
            }

            # 按情绪类型统计
            emotion_stats = {}
            for item in self._memory_items:
                emotion_type = item.get('emotion_type', 0)
                emotion_stats[emotion_type] = emotion_stats.get(emotion_type, 0) + 1

            stats["emotion_distribution"] = emotion_stats

            return stats

        except Exception as e:
            print(f"[VectorMemory] 获取统计信息失败: {e}")
            return {"error": str(e)}

    async def clear_all(self) -> None:
        """清空向量库（危险操作）"""
        try:
            import faiss
            self._index = faiss.IndexFlatL2(self._dimension)
            self._memory_items = []

            # 删除文件
            if self._index_path.exists():
                os.remove(self._index_path)
            if self._memory_path.exists():
                os.remove(self._memory_path)

            print("[VectorMemory] 向量库已清空")

        except Exception as e:
            print(f"[VectorMemory] 清空向量库失败: {e}")