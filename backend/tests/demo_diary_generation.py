#!/usr/bin/env python3
"""
日记生成演示（仅生成，不清理）
演示 2026-04-14 的日记生成功能
"""

import asyncio
import json
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Mock LLM 客户端
class MockLLMClient:
    async def ask(self, prompt, temperature=0.7):
        return """今天调试工具还挺顺利的。

用户好像对我的新能力挺满意的，虽然一开始有点担心出问题。聊了聊音乐和网络梗，还挺放松的。不过说真的，"鸡你太美"那个梗确实挺洗脑的。

===DIARY_SPLIT===
[
    {"content": "用户调试工具挺辛苦的，终于搞定了", "emotion_label": "平静", "importance": 6},
    {"content": "聊了音乐和网络梗，氛围挺轻松的", "emotion_label": "开心", "importance": 5}
]"""


async def main():
    """演示日记生成"""
    from backend.core.long_term_memory.diary_writer import DiaryWriter

    print("=" * 60)
    print("日记生成演示 - 2026-04-14")
    print("=" * 60)

    # 初始化日记生成器
    mock_llm = MockLLMClient()
    writer = DiaryWriter(mock_llm)

    # 1. 提取短期记忆
    print("\n1. 提取 2026-04-14 的短期记忆...")
    draft = await writer.extract_short_term_by_date("2026-04-14")
    print(f"   提取到 {draft.count('[')} 条对话")

    if draft:
        print(f"   草稿长度: {len(draft)} 字符")
        print(f"   草稿预览: {draft[:100]}...")

    # 2. 生成日记（但不清理短期记忆）
    print("\n2. 生成日记（模拟LLM响应）...")

    # 检查是否已有日记文件（增量更新测试）
    memory_root = project_root / "backend" / "agent_memory"
    existing_diary = memory_root / "diary" / "daily" / "2026-04-14.md"

    if existing_diary.exists():
        print("   [INFO] 检测到已有日记文件，将执行增量更新")
        with open(existing_diary, 'r', encoding='utf-8') as f:
            existing_content = f.read()
        print(f"   现有日记长度: {len(existing_content)} 字符")

    # 模拟生成（不实际调用，仅演示流程）
    print("   [SIMULATED] 调用 LLM 生成日记...")
    print("   [SIMULATED] 日记已保存")
    print("   [SIMULATED] 碎片已提取 (2条)")

    # 3. 检查 FAISS 去重功能
    print("\n3. 检查 FAISS 去重功能...")
    print("   [INFO] LongTermIndexer.index_diary() 已实现去重逻辑:")
    print("     - 检查 doc_id == 'diary_2026-04-14' 的重复条目")
    print("     - 如果存在，删除旧条目并重建索引")
    print("     - 添加新向量，实现 Upsert")

    print("\n   [INFO] DeepRetriever.index_fragments() 已实现去重逻辑:")
    print("     - 基于 source_date 去重")
    print("     - 删除相同日期的旧碎片")
    print("     - 重建索引（参数伪装原则）")

    # 4. 检查短期记忆去重
    print("\n4. 检查短期记忆去重...")
    print("   [INFO] memory_core.add_short_term() 已添加去重逻辑:")
    print("     - 检查最后一条是否完全相同（role, content）")
    print("     - 如果完全相同，跳过写入")
    print("     - 防止同一条消息被写两次")

    # 5. 演示增量更新
    print("\n5. 增量更新演示...")
    print("   [INFO] DiaryWriter._build_diary_prompt() 支持增量更新:")
    print("     - 如果检测到已有日记文件，读取其内容")
    print("     - 在 Prompt 中添加补充说明")
    print("     - LLM 在已有内容基础上补充完善")

    print("\n" + "=" * 60)
    print("演示完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())