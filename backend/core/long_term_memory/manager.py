#!/usr/bin/env python3
"""
V3.0 长期记忆管理器
对外统一接口，包装日记生成器与索引器
"""

import asyncio
from pathlib import Path
from typing import Optional
from .diary_writer import DiaryWriter
from .indexer import LongTermIndexer


class LongTermMemoryManager:
    """长期记忆管理器：对外统一接口"""

    def __init__(self, llm_client):
        """
        初始化长期记忆管理器

        :param llm_client: LLM客户端实例（需有 ask 方法）
        """
        self.writer = DiaryWriter(llm_client)
        self.indexer = LongTermIndexer()

        # 计算记忆存储根目录
        self._memory_root = Path(__file__).parent.parent / "agent_memory"
        self._diary_dir = self._memory_root / "diary" / "daily"

        print(f"[LongTermMemoryManager] 初始化完成，日记目录: {self._diary_dir}")

    def get_writer(self) -> DiaryWriter:
        """
        获取日记生成器实例

        :return: DiaryWriter 实例
        """
        return self.writer

    async def search_and_read(self, query: str) -> str:
        """
        搜索并读取日记全文

        :param query: 查询文本
        :return: 匹配的日记全文，无结果时返回空字符串
        """
        print(f"[LongTermMemoryManager] 搜索日记: '{query[:50]}...'")

        # 搜索日记
        results = await self.indexer.search_diary(query, top_k=1)

        # 无结果时返回空字符串
        if not results:
            print(f"[LongTermMemoryManager] 未找到相关日记")
            return ""

        # 取第一条结果
        first_result = results[0]
        file_path = first_result.get("file_path", "")

        if not file_path:
            print(f"[LongTermMemoryManager] 结果中无文件路径")
            return ""

        # 读取全文
        full_text = await self.indexer.read_diary_full_text(file_path)

        if full_text:
            print(f"[LongTermMemoryManager] 成功读取日记，长度: {len(full_text)} 字符")
        else:
            print(f"[LongTermMemoryManager] 读取日记失败")

        return full_text

    async def index_today_diary(self, date_str: str) -> bool:
        """
        索引今日日记

        :param date_str: 日期字符串，如 "2026-04-18"
        :return: 是否成功索引
        """
        print(f"[LongTermMemoryManager] 索引今日日记: {date_str}")

        # 构建日记文件路径
        diary_file = self._diary_dir / f"{date_str}.md"
        if not diary_file.exists():
            print(f"[LongTermMemoryManager] 日记文件不存在: {diary_file}")
            return False

        # 转换为相对路径（相对于项目根目录）
        relative_path = diary_file.relative_to(self._memory_root.parent)

        # 调用索引器
        success = await self.indexer.index_diary(date_str, str(relative_path))

        if success:
            print(f"[LongTermMemoryManager] 日记已成功索引: {date_str}")
        else:
            print(f"[LongTermMemoryManager] 日记索引失败: {date_str}")

        return success

    async def generate_and_index_today_diary(self, date_str: str) -> dict:
        """
        生成并索引今日日记（一体化操作）

        :param date_str: 日期字符串，如 "2026-04-18"
        :return: 生成结果字典
        """
        print(f"[LongTermMemoryManager] 生成并索引今日日记: {date_str}")

        # 生成日记
        result = await self.writer.generate_daily_diary(date_str)

        # 如果生成失败，直接返回
        if result.get("skipped", False) or result.get("error") or not result.get("diary_path"):
            print(f"[LongTermMemoryManager] 日记生成失败或跳过，不进行索引")
            return result

        # 索引日记
        index_success = await self.index_today_diary(date_str)
        result["indexed"] = index_success

        return result


# 简单测试函数（开发用）
async def _test_manager():
    """测试管理器"""
    # 创建模拟 LLM 客户端
    class MockLLMClient:
        async def ask(self, prompt, temperature=0.7):
            return """测试日记内容...

===DIARY_SPLIT===
[
  {
    "content": "用户今天分享了喜欢的音乐。",
    "emotion_label": "开心",
    "importance": 7
  }
]"""

    # 初始化管理器
    manager = LongTermMemoryManager(MockLLMClient())

    # 测试获取 writer
    writer = manager.get_writer()
    print(f"Writer 类型: {type(writer).__name__}")

    # 测试生成日记
    result = await manager.generate_and_index_today_diary("2026-04-18")
    print(f"生成结果: {result}")

    # 测试搜索
    query_result = await manager.search_and_read("音乐")
    print(f"搜索结果长度: {len(query_result)} 字符")

    # 测试单独索引
    index_result = await manager.index_today_diary("2026-04-18")
    print(f"索引结果: {index_result}")


if __name__ == "__main__":
    # 运行测试
    asyncio.run(_test_manager())