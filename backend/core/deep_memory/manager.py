#!/usr/bin/env python3
"""
V3.0 深度记忆管理器
对外统一接口，包装检索器
"""

import asyncio
from typing import List
from .retriever import DeepRetriever


class DeepMemoryManager:
    """深度记忆管理器：对外统一接口"""

    def __init__(self):
        """
        初始化深度记忆管理器
        """
        self.retriever = DeepRetriever()
        print(f"[DeepMemoryManager] 初始化完成，检索器已就绪")

    async def index_today_fragments(self, fragments_path: str) -> bool:
        """
        供流水线调用：将今天的碎片入库

        :param fragments_path: 碎片 JSON 文件路径
        :return: 是否成功入库
        """
        print(f"[DeepMemoryManager] 索引今日碎片: {fragments_path}")

        # 调用检索器进行索引
        success = await self.retriever.index_fragments(fragments_path)

        if success:
            print(f"[DeepMemoryManager] 碎片已成功索引")
        else:
            print(f"[WARN] 碎片索引失败")

        return success

    async def subconscious_recall(self, query: str, emotion_label: str) -> List[str]:
        """
        供主流程调用：潜意识联想，返回纯净文字列表

        :param query: 查询文本
        :param emotion_label: 当前情绪标签（平静/开心/难过/烦躁）
        :return: 纯净的碎片内容列表
        """
        print(f"[DeepMemoryManager] 潜意识联想: '{query[:30]}...' (情绪: {emotion_label})")

        # 调用检索器进行联想
        results = await self.retriever.trigger_recall(query, emotion_label)

        if results:
            print(f"[DeepMemoryManager] 联想返回 {len(results)} 条碎片")
        else:
            print(f"[DeepMemoryManager] 无联想结果")

        return results


# 简单测试函数（开发用）
async def _test_manager():
    """测试管理器"""
    # 初始化管理器
    manager = DeepMemoryManager()

    # 创建测试碎片文件路径
    from pathlib import Path
    memory_root = Path(__file__).parent.parent / "agent_memory"
    staging_dir = memory_root / "staging"

    # 确保目录存在
    staging_dir.mkdir(parents=True, exist_ok=True)

    # 创建测试碎片数据
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
    test_file = staging_dir / "test_fragments.json"
    import json
    with open(test_file, 'w', encoding='utf-8') as f:
        json.dump(test_fragments, f, indent=2)

    print(f"测试文件已创建: {test_file}")

    # 测试索引碎片
    success = await manager.index_today_fragments(str(test_file))
    print(f"索引结果: {success}")

    # 测试潜意识联想
    results = await manager.subconscious_recall("被老板批评", "难过")
    print(f"潜意识联想结果数量: {len(results)}")
    for i, content in enumerate(results):
        print(f"碎片 {i+1}: {content[:50]}...")


if __name__ == "__main__":
    # 运行测试
    asyncio.run(_test_manager())