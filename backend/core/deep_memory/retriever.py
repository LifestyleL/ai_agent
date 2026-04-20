#!/usr/bin/env python3
"""
V3.0 深度记忆检索器
实现参数伪装与碎片联想："触景生情"能力
"""

import asyncio
import json
import os
import sys
import faiss
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional
from sentence_transformers import SentenceTransformer

# 添加父目录到sys.path以便导入config
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config


class DeepRetriever:
    """深度记忆检索器：基于情绪参数的潜意识联想"""

    def __init__(self):
        # 计算记忆存储根目录
        self._memory_root = Path(__file__).parent.parent / "agent_memory"

        # 索引存储路径
        self._index_dir = self._memory_root / "deep_index"
        self._index_dir.mkdir(parents=True, exist_ok=True)

        self._index_path = self._index_dir / "deep_index.faiss"
        self._mapping_path = self._index_dir / "deep_mapping.json"
        self._stats_path = self._index_dir / "access_stats.json"

        # 资源（懒加载）
        self._model = None  # SentenceTransformer 模型
        self._index = None  # FAISS 索引
        self._mapping_list = []  # ID -> 纯净原文映射

        # 异步锁（防止 FAISS 并发崩溃）
        self._lock = asyncio.Lock()

        # 向量维度（all-MiniLM-L6-v2 是 384 维）
        self._dimension = 384

        # 遗忘机制配置
        self.MAX_MEMORY_SIZE = config.FORGETTING_MAX_CAPACITY
        self.FORGETTING_STRATEGY = config.FORGETTING_STRATEGY
        self.FORGETTING_AGGRESSIVENESS = config.FORGETTING_AGGRESSIVENESS
        self.ENABLE_WAL_LOGGING = config.ENABLE_WAL_LOGGING

        # 访问统计（用于智能遗忘）
        self._access_stats = {}  # fragment_id -> {"access_count": int, "last_access": timestamp}

        print(f"[DeepRetriever] 初始化完成，索引目录: {self._index_dir}")
        print(f"[DeepRetriever] 遗忘配置: 策略={self.FORGETTING_STRATEGY}, 容量={self.MAX_MEMORY_SIZE}, 激进度={self.FORGETTING_AGGRESSIVENESS}")

    def _load_resources(self) -> None:
        """
        懒加载资源：模型、索引、映射
        注意：此方法应在第一次使用时被调用，且内部使用同步代码
        """
        # 加载模型
        if self._model is None:
            print(f"[DeepRetriever] 加载 Embedding 模型: all-MiniLM-L6-v2")
            self._model = SentenceTransformer('all-MiniLM-L6-v2')
            print(f"[DeepRetriever] 模型加载完成，维度: {self._model.get_sentence_embedding_dimension()}")

        # 加载或创建索引
        if self._index is None:
            if self._index_path.exists():
                print(f"[DeepRetriever] 加载现有 FAISS 索引: {self._index_path}")
                self._index = faiss.read_index(str(self._index_path))
                print(f"[DeepRetriever] 索引已加载，包含 {self._index.ntotal} 个向量")
            else:
                print(f"[DeepRetriever] 创建新的 FAISS 索引 (维度: {self._dimension})")
                self._index = faiss.IndexFlatL2(self._dimension)

        # 加载映射文件
        if self._mapping_path.exists():
            try:
                with open(self._mapping_path, 'r', encoding='utf-8') as f:
                    self._mapping_list = json.load(f)
                print(f"[DeepRetriever] 映射已加载，包含 {len(self._mapping_list)} 个条目")
            except Exception as e:
                print(f"[WARN] 加载映射文件失败: {e}")
                self._mapping_list = []
        else:
            self._mapping_list = []

        # 验证映射列表与索引大小一致
        if self._index is not None and len(self._mapping_list) != self._index.ntotal:
            print(f"[WARN] 映射与索引大小不一致: 映射={len(self._mapping_list)}, 索引={self._index.ntotal}")

        # 加载访问统计
        if self._stats_path.exists():
            try:
                with open(self._stats_path, 'r', encoding='utf-8') as f:
                    self._access_stats = json.load(f)
                print(f"[DeepRetriever] 访问统计已加载，包含 {len(self._access_stats)} 个条目")
            except Exception as e:
                print(f"[WARN] 加载访问统计失败: {e}")
                self._access_stats = {}
        else:
            self._access_stats = {}

    async def index_fragments(self, fragments_path: str) -> bool:
        """
        将日记碎片注入潜意识（参数伪装核心）

        :param fragments_path: 碎片 JSON 文件路径
        :return: 是否成功入库
        """
        # (a) 获取锁
        async with self._lock:
            try:
                # (b) 确保资源已加载
                if self._model is None or self._index is None:
                    self._load_resources()

                # 读取碎片文件
                fragments_data = await asyncio.to_thread(self._read_json_sync, fragments_path)
                if not isinstance(fragments_data, list):
                    print(f"[DeepRetriever] 碎片数据不是列表格式: {type(fragments_data)}")
                    return False

                if not fragments_data:
                    print(f"[DeepRetriever] 碎片数据为空，跳过索引")
                    return False

                print(f"[DeepRetriever] 开始索引 {len(fragments_data)} 个碎片...")

                # (c) 去重检查：基于日期（source_date）去重
                # 从第一个碎片提取日期（所有碎片应该来自同一天）
                target_date = None
                for item in fragments_data:
                    if isinstance(item, dict):
                        target_date = item.get("source_date", "")
                        if target_date:
                            break

                if target_date:
                    print(f"[DeepRetriever] 去重检查：检测到日期 {target_date}")

                    # 查找映射中相同日期的现有条目
                    indices_to_remove = []
                    for i, mapping in enumerate(self._mapping_list):
                        if mapping.get("source_date") == target_date:
                            indices_to_remove.append(i)

                    # 如果找到相同日期的现有条目，执行 Upsert（先删后写）
                    if indices_to_remove:
                        print(f"[DeepRetriever] 检测到 {target_date} 已有 {len(indices_to_remove)} 个碎片，执行 Upsert")

                        # 1. 从映射列表中删除这些条目（逆序删除，防止索引错乱）
                        for idx in sorted(indices_to_remove, reverse=True):
                            self._mapping_list.pop(idx)

                        # 2. 重建索引（因为 FAISS 不支持精确删除）
                        self._rebuild_index()

                # (d) 遍历碎片列表
                added_count = 0
                for item in fragments_data:
                    if not isinstance(item, dict):
                        continue

                    # 提取字段
                    fragment_id = item.get("fragment_id", "")
                    content = item.get("content", "")
                    emotion_label = item.get("emotion_label", "平静")
                    emotion_type = item.get("emotion_type", 0)
                    importance = item.get("importance", 5)
                    source_date = item.get("source_date", "")

                    if not content or not fragment_id:
                        continue

                    # ⚠️ 核心机密：参数伪装原则
                    # 伪装入库文本（给 FAISS 算相似度用的）
                    tagged_content = f"[标签:{emotion_label}] {content}"

                    # 向量化伪装文本
                    vector = self._model.encode([tagged_content])
                    vector = vector.astype('float32')

                    # 添加到 FAISS 索引
                    self._index.add(vector)

                    # 纯净映射数据（给 LLM 看的）
                    pure_mapping = {
                        "fragment_id": fragment_id,
                        "content": content,  # 注意：纯净原文，不带标签！
                        "emotion_type": emotion_type,
                        "emotion_label": emotion_label,
                        "importance": importance,
                        "source_date": source_date,
                        "vector_id": self._index.ntotal - 1  # 刚添加的向量ID
                    }
                    self._mapping_list.append(pure_mapping)

                    # 初始化访问统计
                    import time
                    self._access_stats[fragment_id] = {
                        "access_count": 0,
                        "last_access": time.time(),
                        "created_time": time.time()
                    }

                    added_count += 1

                print(f"[DeepRetriever] 成功索引 {added_count} 个碎片")

                # (e) 触发遗忘检查
                await asyncio.to_thread(self._trim_memory)

                # (f) 持久化
                await self._persist_index_and_mapping()

                return True

            except Exception as e:
                print(f"[ERROR] 索引碎片失败: {e}")
                return False

    def _calculate_forgetting_score(self, mapping: Dict[str, Any]) -> float:
        """
        计算遗忘分数（分数越高越容易被遗忘）
        根据配置的策略综合考虑重要性、时间和访问频率
        """
        fragment_id = mapping.get("fragment_id")
        importance = mapping.get("importance", 5)

        # 基础分数：重要性越低，越容易被遗忘（归一化到0-1）
        importance_score = 1.0 - (importance / 10.0)  # 重要性1-10，转换为0-1

        if self.FORGETTING_STRATEGY == "importance_based":
            return importance_score

        # 获取访问统计
        access_info = self._access_stats.get(fragment_id, {})
        access_count = access_info.get("access_count", 0)
        last_access = access_info.get("last_access", 0)
        created_time = access_info.get("created_time", 0)

        import time
        current_time = time.time()

        if self.FORGETTING_STRATEGY == "time_based":
            # 时间因素：越旧的记忆越容易被遗忘
            if created_time == 0:
                return importance_score

            # 计算年龄（天）
            age_days = (current_time - created_time) / (24 * 3600)
            # 年龄分数：年龄越大，分数越高（更容易被遗忘）
            # 使用对数函数避免新记忆分数为0
            age_score = min(1.0, age_days / 30)  # 30天达到最大分数1.0

            # 组合重要性（40%）和时间（60%）
            return 0.4 * importance_score + 0.6 * age_score

        elif self.FORGETTING_STRATEGY == "hybrid":
            # 混合策略：综合考虑重要性、时间和访问频率

            # 时间因素
            if created_time == 0:
                age_score = 0.5
            else:
                age_days = (current_time - created_time) / (24 * 3600)
                age_score = min(1.0, age_days / 60)  # 60天达到最大分数

            # 访问频率：访问越少，越容易被遗忘
            access_score = 0.0
            if access_count == 0:
                access_score = 1.0  # 从未访问过，最容易遗忘
            else:
                # 基于最近访问时间：最近访问过的记忆更不容易遗忘
                if last_access == 0:
                    recency_score = 1.0
                else:
                    recency_days = (current_time - last_access) / (24 * 3600)
                    recency_score = min(1.0, recency_days / 14)  # 14天未访问达到最大分数

                # 访问次数：访问次数越多越不容易遗忘（对数压缩）
                frequency_score = 1.0 - min(1.0, access_count / 20)  # 访问20次以上认为很频繁

                access_score = 0.7 * recency_score + 0.3 * frequency_score

            # 组合权重：重要性30%，时间40%，访问频率30%
            forgetting_score = (
                0.3 * importance_score +
                0.4 * age_score +
                0.3 * access_score
            )

            # 应用激进度配置：激进度越高，整体分数越高（更容易遗忘）
            adjusted_score = forgetting_score * (0.5 + self.FORGETTING_AGGRESSIVENESS)
            return min(1.0, adjusted_score)

        # 默认回退到重要性策略
        return importance_score

    def _trim_memory(self) -> None:
        """
        遗忘机制：当记忆过多时删除不重要的碎片
        注意：此方法在锁内部同步调用
        """
        # 检查是否需要触发遗忘
        if self._index.ntotal < self.MAX_MEMORY_SIZE:
            return

        print(f"[DeepRetriever] 触发遗忘机制: 当前 {self._index.ntotal} 个向量，阈值 {self.MAX_MEMORY_SIZE}")

        # 根据遗忘策略排序（分数越高越容易被遗忘）
        scored_mapping = []
        for mapping in self._mapping_list:
            score = self._calculate_forgetting_score(mapping)
            scored_mapping.append((score, mapping))

        # 按遗忘分数升序排序（分数低的排在前面，先保留）
        sorted_mapping = sorted(scored_mapping, key=lambda x: x[0])

        # 计算要删除的数量（基于激进度配置）
        excess = self._index.ntotal - self.MAX_MEMORY_SIZE
        # 基础删除：过量部分 + 缓冲（避免频繁触发）
        base_remove = excess + 500
        # 根据激进度调整（激进度0.0-1.0，对应0.5x-1.5x删除量）
        aggression_factor = 0.5 + self.FORGETTING_AGGRESSIVENESS  # 0.5-1.5
        remove_count = int(base_remove * aggression_factor)
        # 限制删除范围：最少删除过量部分，最多删除一半
        remove_count = max(excess, min(remove_count, len(sorted_mapping) // 2))

        if remove_count <= 0:
            return

        # 收集要删除的碎片ID（用于清理访问统计）
        removed_fragment_ids = []
        for i in range(remove_count):
            if i < len(sorted_mapping):
                _, mapping = sorted_mapping[i]
                fragment_id = mapping.get("fragment_id")
                if fragment_id:
                    removed_fragment_ids.append(fragment_id)

        # 保留分数低的部分（不容易遗忘的）
        keep_scored = sorted_mapping[remove_count:]
        keep_mapping = [mapping for _, mapping in keep_scored]

        # 关键：重建索引（FAISS 删除特定向量很麻烦，重建是最稳妥的）
        print(f"[DeepRetriever] 删除 {remove_count} 个不重要碎片，保留 {len(keep_mapping)} 个")

        # 创建新索引
        new_index = faiss.IndexFlatL2(self._dimension)

        # 为保留的映射重新索引
        for mapping in keep_mapping:
            # 重新构造伪装文本
            tagged_content = f"[标签:{mapping['emotion_label']}] {mapping['content']}"
            vector = self._model.encode([tagged_content])
            vector = vector.astype('float32')
            new_index.add(vector)

        # 更新索引和映射
        self._index = new_index
        self._mapping_list = keep_mapping

        # 清理被删除碎片的访问统计
        cleaned_stats = 0
        for fragment_id in removed_fragment_ids:
            if fragment_id in self._access_stats:
                del self._access_stats[fragment_id]
                cleaned_stats += 1
        if cleaned_stats > 0:
            print(f"[DeepRetriever] 已清理 {cleaned_stats} 个被删除碎片的访问统计")

        # 重置向量ID
        for i, mapping in enumerate(self._mapping_list):
            mapping["vector_id"] = i

        print(f"[DeepRetriever] 遗忘完成，新索引包含 {self._index.ntotal} 个向量")

    def _rebuild_index(self) -> None:
        """
        根据当前 mapping_list 重建 FAISS 索引（在锁内部同步调用）
        用于去重后的索引更新
        """
        # 确保模型已加载
        if self._model is None:
            self._load_resources()

        # 创建新索引
        new_index = faiss.IndexFlatL2(self._dimension)

        # 如果没有映射条目，只需清空索引
        if not self._mapping_list:
            self._index = new_index
            print(f"[DeepRetriever] 索引已重建，当前为空")
            return

        # 为所有映射重新索引
        for i, mapping in enumerate(self._mapping_list):
            # 重新构造伪装文本
            tagged_content = f"[标签:{mapping['emotion_label']}] {mapping['content']}"
            vector = self._model.encode([tagged_content])
            vector = vector.astype('float32')
            new_index.add(vector)
            # 更新向量ID（确保与重建后的位置一致）
            mapping["vector_id"] = i

        # 更新索引
        self._index = new_index
        print(f"[DeepRetriever] 索引已重建，包含 {self._index.ntotal} 个向量")

    async def trigger_recall(self, query: str, current_emotion_label: str, top_k: int = 2) -> List[str]:
        """
        被动触景生情：基于当前情绪的潜意识联想

        :param query: 查询文本
        :param current_emotion_label: 当前情绪标签
        :param top_k: 返回结果数量
        :return: 纯净的碎片内容列表（不带标签）
        """
        # (a) 获取锁
        async with self._lock:
            try:
                # (b) 确保资源已加载
                if self._model is None or self._index is None:
                    self._load_resources()

                # 检查索引是否为空
                if self._index.ntotal == 0:
                    print(f"[DeepRetriever] 索引为空，跳过联想")
                    return []

                # 构造伪装 Query
                tagged_query = f"[标签:{current_emotion_label}] {query}"
                print(f"[DeepRetriever] 触景生情: '{query[:30]}...' (情绪: {current_emotion_label})")

                # (c) 向量化伪装 Query
                query_vector = self._model.encode([tagged_query])
                query_vector = query_vector.astype('float32')

                # 搜索
                distances, indices = self._index.search(
                    query_vector, min(top_k, self._index.ntotal)
                )

                # (d) 提取纯净内容并更新访问统计
                results = []
                for idx in indices[0]:
                    if idx >= 0 and idx < len(self._mapping_list):
                        mapping = self._mapping_list[idx]
                        pure_content = mapping["content"]
                        results.append(pure_content)

                        # 更新访问统计
                        fragment_id = mapping.get("fragment_id")
                        if fragment_id:
                            import time
                            current_time = time.time()
                            if fragment_id in self._access_stats:
                                self._access_stats[fragment_id]["access_count"] += 1
                                self._access_stats[fragment_id]["last_access"] = current_time
                            else:
                                self._access_stats[fragment_id] = {
                                    "access_count": 1,
                                    "last_access": current_time
                                }

                print(f"[DeepRetriever] 联想返回 {len(results)} 个碎片")
                return results

            except Exception as e:
                print(f"[ERROR] 触景生情失败: {e}")
                return []

    async def _persist_index_and_mapping(self) -> None:
        """持久化索引和映射文件"""
        try:
            # 保存 FAISS 索引
            await asyncio.to_thread(faiss.write_index, self._index, str(self._index_path))

            # 保存映射文件
            await asyncio.to_thread(self._write_json_sync, self._mapping_path, self._mapping_list)

            # 保存访问统计
            await asyncio.to_thread(self._write_json_sync, self._stats_path, self._access_stats)

            print(f"[DeepRetriever] 索引已持久化: {self._index.ntotal} 个向量, {len(self._mapping_list)} 个映射, {len(self._access_stats)} 个访问统计")

        except Exception as e:
            print(f"[ERROR] 持久化索引失败: {e}")

    def _read_json_sync(self, file_path: str) -> Any:
        """同步读取 JSON 文件（在子线程中运行）"""
        try:
            # 解析路径
            if os.path.isabs(file_path):
                path_obj = Path(file_path)
            else:
                path_obj = self._memory_root.parent / file_path

            with open(path_obj, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] 读取 JSON 失败 {file_path}: {e}")
            return []

    def _write_json_sync(self, file_path: Path, data: Any) -> None:
        """同步写入 JSON 文件（在子线程中运行）"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ERROR] 写入 JSON 失败 {file_path}: {e}")


# 简单测试函数（开发用）
async def _test_retriever():
    """测试深度记忆检索器"""
    # 创建检索器
    retriever = DeepRetriever()

    # 准备测试碎片数据
    test_fragments = [
        {
            "fragment_id": "frag_20260418_001",
            "content": "他说今天被老板骂了，看着他难过的样子我心里有点不好受。",
            "emotion_type": 2,
            "emotion_label": "难过",
            "importance": 7,
            "source_date": "2026-04-18"
        },
        {
            "fragment_id": "frag_20260418_002",
            "content": "用户分享了他最喜欢的音乐，旋律很温暖。",
            "emotion_type": 1,
            "emotion_label": "开心",
            "importance": 6,
            "source_date": "2026-04-18"
        }
    ]

    # 写入测试文件
    test_file = Path(__file__).parent.parent / "agent_memory" / "staging" / "test_fragments.json"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    with open(test_file, 'w', encoding='utf-8') as f:
        json.dump(test_fragments, f, indent=2)

    # 测试索引碎片
    success = await retriever.index_fragments(str(test_file))
    print(f"索引结果: {success}")

    # 测试触景生情
    results = await retriever.trigger_recall("被老板批评", "难过", top_k=2)
    print(f"触景生情结果数量: {len(results)}")
    for i, content in enumerate(results):
        print(f"碎片 {i+1}: {content[:50]}...")


if __name__ == "__main__":
    # 运行测试
    asyncio.run(_test_retriever())