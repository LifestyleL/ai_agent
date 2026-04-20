#!/usr/bin/env python3
"""
历史数据日记生成测试
逐天测试 14-17 号的短期记忆 → 日记 → 碎片 → 索引 完整流程
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# Mock SentenceTransformer 避免真实模型下载
import sentence_transformers

class MockSentenceTransformer:
    """模拟 SentenceTransformer 模型，避免真实模型下载"""

    def __init__(self, model_name='all-MiniLM-L6-v2'):
        self.model_name = model_name
        self.embedding_dimension = 384

    def get_sentence_embedding_dimension(self):
        return self.embedding_dimension

    def encode(self, texts, **kwargs):
        # 返回固定维度的随机向量
        import numpy as np
        if isinstance(texts, str):
            texts = [texts]
        # 创建确定性的伪随机向量，相同文本产生相同向量
        vectors = []
        for text in texts:
            # 使用文本的哈希值作为种子，确保相同文本得到相同向量
            seed = hash(text) % (2**32)
            rng = np.random.RandomState(seed)
            vectors.append(rng.randn(self.embedding_dimension).astype('float32'))
        return np.array(vectors)

# 应用 mock - 替换 sentence_transformers 模块中的 SentenceTransformer 类
sentence_transformers.SentenceTransformer = MockSentenceTransformer

# 现在导入项目模块
from backend.core.long_term_memory.diary_writer import DiaryWriter
from backend.core.long_term_memory.manager import LongTermMemoryManager
from backend.core.deep_memory.manager import DeepMemoryManager


class MockLLMClient:
    """模拟 LLM 客户端（用于日记生成）"""

    async def ask(self, prompt, temperature=0.7):
        # 根据日期返回不同的模拟响应
        if "2026-04-14" in prompt:
            return """今天调试工具还挺顺利的。

用户好像对我的新能力挺满意的，虽然一开始有点担心出问题。聊了聊音乐和网络梗，还挺放松的。不过说真的，"鸡你太美"那个梗确实挺洗脑的。

===DIARY_SPLIT===
[
    {"content": "用户调试工具挺辛苦的，终于搞定了", "emotion_label": "平静", "importance": 6},
    {"content": "聊了音乐和网络梗，氛围挺轻松的", "emotion_label": "开心", "importance": 5}
]"""
        elif "2026-04-15" in prompt:
            return """今天给我装了网上冲浪功能。

虽然嘴上抱怨他熬夜到一点多，但其实挺感激的。新功能听起来挺有意思的，可以多了解一下外面的世界了。

===DIARY_SPLIT===
[
    {"content": "用户熬夜给我装新功能，有点担心他的身体", "emotion_label": "平静", "importance": 7},
    {"content": "有了网上冲浪功能，可以多了解外面的世界了", "emotion_label": "开心", "importance": 6}
]"""
        elif "2026-04-16" in prompt:
            return """今天框架重构总算搞定了。

用户一直在测试通道分离，重复问了好多遍，说实话有点烦。不过看到最终没问题还是松了口气。他工作到很晚，看着挺累的。

===DIARY_SPLIT===
[
    {"content": "框架重构完成，问题总算解决了", "emotion_label": "平静", "importance": 8},
    {"content": "用户重复测试通道分离，有点烦但又理解他担心出问题", "emotion_label": "烦躁", "importance": 5},
    {"content": "用户工作到很晚，看着挺累的", "emotion_label": "难过", "importance": 4}
]"""
        else:  # 2026-04-17
            return """今天主要测试TTS功能。

遇到了些授权问题，不过后来好像解决了。用户一直在测试，挺有耐心的。希望能早点休息吧。

===DIARY_SPLIT===
[
    {"content": "测试TTS功能遇到授权问题，后来解决了", "emotion_label": "平静", "importance": 6},
    {"content": "用户耐心测试各种功能，挺有毅力的", "emotion_label": "平静", "importance": 5}
]"""


def print_section(title):
    """打印带格式的章节标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


async def cleanup_test_directories():
    """清理测试目录，但保留原始数据"""
    memory_root = project_root / "backend" / "agent_memory"

    # 清理测试生成的文件
    test_files = [
        memory_root / "daily_draft.txt",
    ]

    # 清理日记目录（如果存在测试生成的文件）
    diary_dir = memory_root / "diary" / "daily"
    if diary_dir.exists():
        for file in diary_dir.glob("*.md"):
            if file.name.startswith("2026-04-"):
                try:
                    file.unlink()
                    print(f"  清理日记文件: {file.name}")
                except:
                    pass

    # 清理staging目录中的测试碎片文件
    staging_dir = memory_root / "staging"
    if staging_dir.exists():
        for file in staging_dir.glob("*_fragments.json"):
            if file.name.startswith("2026-04-"):
                try:
                    file.unlink()
                    print(f"  清理碎片文件: {file.name}")
                except:
                    pass

    # 清空草稿文件
    for file_path in test_files:
        if file_path.exists():
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write("")
                print(f"  清空文件: {file_path.name}")
            except:
                pass


async def check_short_term_data(date_str: str) -> int:
    """检查指定日期的短期记忆条数"""
    short_term_path = project_root / "backend" / "agent_memory" / "short_term.json"
    if not short_term_path.exists():
        print(f"[FAIL] short_term.json 不存在")
        return 0

    try:
        with open(short_term_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        dialogues = data.get("dialogues", [])
        count = 0
        for item in dialogues:
            if isinstance(item, dict):
                timestamp = item.get("timestamp", "")
                if timestamp.startswith(date_str):
                    count += 1

        return count
    except Exception as e:
        print(f"[ERROR] 检查短期记忆失败: {e}")
        return 0


async def test_date(date_str: str, writer: DiaryWriter,
                    long_term_mem: LongTermMemoryManager,
                    deep_mem: DeepMemoryManager) -> dict:
    """测试单个日期的完整流程"""
    print_section(f"测试 {date_str}")

    results = {
        "date": date_str,
        "short_term_count": 0,
        "diary_generated": False,
        "fragments_generated": False,
        "indexed_long": False,
        "indexed_deep": False
    }

    # 1. 检查短期记忆条数
    short_term_count = await check_short_term_data(date_str)
    results["short_term_count"] = short_term_count
    print(f"1. 短期记忆: {short_term_count} 条")

    if short_term_count == 0:
        print("   [SKIP] 无短期记忆，跳过该日期")
        return results

    # 2. 执行手动生成（提取→生成→清理）
    print(f"2. 执行手动生成...")
    try:
        manual_result = await writer.manual_generate_and_cleanup(date_str)
        if manual_result.get("diary_result", {}).get("diary_path"):
            results["diary_generated"] = True
            diary_path = manual_result["diary_result"]["diary_path"]
            print(f"   [OK] 日记生成成功: {diary_path}")

            # 检查日记文件是否存在
            full_path = project_root / "backend" / diary_path
            if full_path.exists():
                size = os.path.getsize(full_path)
                print(f"       文件大小: {size} 字节")
        else:
            print(f"   [FAIL] 日记生成失败")
    except Exception as e:
        print(f"   [ERROR] 手动生成失败: {e}")

    # 3. 归档到长期记忆索引
    print(f"3. 归档到长期记忆索引...")
    try:
        # 使用管理器的 index_today_diary 方法
        index_success = await long_term_mem.index_today_diary(date_str)
        results["indexed_long"] = index_success
        if index_success:
            print(f"   [OK] 长期记忆索引成功")
        else:
            print(f"   [FAIL] 长期记忆索引失败")
    except Exception as e:
        print(f"   [ERROR] 长期记忆索引失败: {e}")

    # 4. 碎片索引到深度记忆
    print(f"4. 碎片索引到深度记忆...")
    try:
        # 检查碎片文件是否存在
        fragments_path = project_root / "backend" / "agent_memory" / "staging" / f"{date_str}_fragments.json"
        if fragments_path.exists():
            # 使用相对路径
            rel_path = fragments_path.relative_to(project_root / "backend")
            index_success = await deep_mem.index_today_fragments(str(rel_path))
            results["indexed_deep"] = index_success
            if index_success:
                print(f"   [OK] 深度记忆索引成功")
                results["fragments_generated"] = True
            else:
                print(f"   [FAIL] 深度记忆索引失败")
        else:
            print(f"   [SKIP] 碎片文件不存在")
    except Exception as e:
        print(f"   [ERROR] 深度记忆索引失败: {e}")

    return results


async def main():
    """主测试函数"""
    print_section("历史数据日记生成测试 (2026-04-14 → 17)")

    # 清理旧的测试数据
    print("清理测试目录...")
    await cleanup_test_directories()

    # 初始化组件
    print("初始化组件...")
    mock_llm = MockLLMClient()
    writer = DiaryWriter(mock_llm)
    long_term_mem = LongTermMemoryManager(mock_llm)
    deep_mem = DeepMemoryManager()

    # 测试每个日期
    dates_to_test = ["2026-04-14", "2026-04-15", "2026-04-16", "2026-04-17"]

    all_results = []
    for date_str in dates_to_test:
        result = await test_date(date_str, writer, long_term_mem, deep_mem)
        all_results.append(result)
        # 每个日期之间稍作间隔
        await asyncio.sleep(0.5)

    # 打印最终总结
    print_section("测试总结")

    print("日期        短期记忆  日记生成  碎片生成  长记索引  深记索引")
    print("-" * 60)

    for result in all_results:
        date = result["date"]
        st_count = result["short_term_count"]
        diary = "[OK]" if result["diary_generated"] else "[NO]"
        frag = "[OK]" if result["fragments_generated"] else "[NO]"
        long_idx = "[OK]" if result["indexed_long"] else "[NO]"
        deep_idx = "[OK]" if result["indexed_deep"] else "[NO]"

        print(f"{date}  {st_count:>3}条     {diary}    {frag}    {long_idx}    {deep_idx}")

    # 检查生成的文件
    print_section("生成文件检查")

    memory_root = project_root / "backend" / "agent_memory"

    # 检查日记文件
    diary_dir = memory_root / "diary" / "daily"
    if diary_dir.exists():
        md_files = list(diary_dir.glob("*.md"))
        print(f"日记文件数量: {len(md_files)}")
        for f in sorted(md_files):
            print(f"  - {f.name} ({os.path.getsize(f)} 字节)")
    else:
        print("日记目录不存在")

    # 检查碎片文件
    staging_dir = memory_root / "staging"
    if staging_dir.exists():
        json_files = list(staging_dir.glob("*_fragments.json"))
        print(f"碎片文件数量: {len(json_files)}")
        for f in sorted(json_files):
            size = os.path.getsize(f)
            print(f"  - {f.name} ({size} 字节)")
    else:
        print("staging 目录不存在")

    # 检查索引文件
    long_index_dir = memory_root / "long_term_index"
    if long_index_dir.exists():
        files = list(long_index_dir.glob("*"))
        print(f"长期记忆索引文件: {len(files)} 个")

    deep_index_dir = memory_root / "deep_index"
    if deep_index_dir.exists():
        files = list(deep_index_dir.glob("*"))
        print(f"深度记忆索引文件: {len(files)} 个")


if __name__ == "__main__":
    asyncio.run(main())