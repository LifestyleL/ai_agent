#!/usr/bin/env python3
"""
V3.0 日记生成器
实现"白天随手记草稿 → 深夜一次性生成日记+碎片"的核心流转
"""

import asyncio
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional


class DiaryWriter:
    """日记生成器核心类：草稿积累 + 日记生成 + 碎片提取"""

    def __init__(self, llm_client):
        """
        初始化日记生成器
        :param llm_client: LLM客户端实例（需有 ask 方法）
        """
        self.llm_client = llm_client

        # 计算记忆存储根目录（与 memory_core 保持一致）
        self._memory_root = Path(__file__).parent.parent / "agent_memory"

        # 路径定义
        self._draft_path = self._memory_root / "daily_draft.txt"
        self._flashback_path = self._memory_root / "flashbacks.json"
        self._diary_dir = self._memory_root / "diary" / "daily"
        self._staging_dir = self._memory_root / "staging"

        # 确保目录存在
        self._diary_dir.mkdir(parents=True, exist_ok=True)
        self._staging_dir.mkdir(parents=True, exist_ok=True)

    async def generate_daily_diary(self, date_str: str) -> Dict[str, Any]:
        """
        生成今日日记（核心方法）

        流程：读取草稿 → 调用LLM → 分割双输出 → 保存日记+碎片 → 清空草稿

        :param date_str: 日期字符串，格式如 "2026-04-18"
        :return: 生成结果字典
        """
        print(f"[DiaryWriter] 开始生成 {date_str} 的日记...")

        # (a) 读取草稿
        draft_content = await self._read_draft()
        if not draft_content.strip():
            print(f"[DiaryWriter] 今日草稿为空，跳过生成")
            return {
                "date": date_str,
                "diary_path": None,
                "fragments_path": None,
                "fragment_count": 0,
                "skipped": True
            }

        print(f"[DiaryWriter] 草稿长度: {len(draft_content)} 字符")

        # 检查是否已存在该日期的日记（增量更新场景）
        existing_diary_path = self._diary_dir / f"{date_str}.md"
        existing_diary_content = ""
        if existing_diary_path.exists():
            # 读取已有日记，作为补充上下文
            try:
                existing_diary_content = await asyncio.to_thread(self._read_file_sync, existing_diary_path)
                print(f"[DiaryWriter] 检测到已有日记文件，将进行增量更新（长度: {len(existing_diary_content)} 字符）")
            except Exception as e:
                print(f"[WARN] 读取已有日记失败: {e}")

        # (b) 构造 Prompt
        prompt = self._build_diary_prompt(draft_content, date_str, existing_diary_content)

        # (c) 调用 LLM（异步）
        print(f"[DiaryWriter] 调用 LLM 生成日记...")
        try:
            llm_response = await self.llm_client.ask(prompt, temperature=0.7)
        except Exception as e:
            print(f"[ERROR] LLM 调用失败: {e}")
            return {
                "date": date_str,
                "diary_path": None,
                "fragments_path": None,
                "fragment_count": 0,
                "error": str(e)
            }

        # (d) 解析双输出
        diary_content, fragments = self._parse_llm_response(llm_response)

        # (e) 保存日记
        diary_file = self._diary_dir / f"{date_str}.md"
        await self._write_file(diary_file, diary_content)
        print(f"[DiaryWriter] 日记已保存: {diary_file}")

        # (f) 保存碎片中间文件
        fragment_count = 0
        fragments_file = None
        if fragments:
            fragments_file = self._staging_dir / f"{date_str}_fragments.json"
            enriched_fragments = self._enrich_fragments(fragments, date_str)
            fragment_count = len(enriched_fragments)
            await self._write_json(fragments_file, enriched_fragments)
            print(f"[DiaryWriter] 碎片已保存 ({fragment_count} 条): {fragments_file}")

        # (g) 清空草稿
        await self._clear_draft()
        print(f"[DiaryWriter] 草稿已清空")

        # (h) 返回结果
        return {
            "date": date_str,
            "diary_path": str(diary_file.relative_to(self._memory_root.parent)),
            "fragments_path": str(fragments_file.relative_to(self._memory_root.parent)) if fragments_file else None,
            "fragment_count": fragment_count
        }

    async def append_draft(self, text: str) -> None:
        """
        追加内容到今日草稿

        :param text: 要追加的文本内容
        """
        if not text.strip():
            return

        # 添加时间戳
        timestamp = datetime.now().strftime("%H:%M")
        line = f"[{timestamp}] {text.strip()}\n"

        # 异步追加写入
        try:
            await self._append_to_file(self._draft_path, line)
            print(f"[DiaryWriter] 草稿已追加: {text[:50]}...")
        except Exception as e:
            print(f"[ERROR] 追加草稿失败: {e}")

    def get_flashbacks(self) -> List[Dict[str, Any]]:
        """
        读取闪回列表（同步方法）

        :return: 闪回列表
        """
        try:
            if self._flashback_path.exists():
                with open(self._flashback_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
        except Exception as e:
            print(f"[WARN] 读取闪回失败: {e}")

        return []

    # ==================== 新增短期记忆操作方法 ====================

    async def extract_short_term_by_date(self, date_str: str) -> str:
        """
        从 short_term.json 中提取指定日期的短期记忆条目，
        拼接成一段文本草稿返回。
        如果该日期没有条目，返回空字符串。
        """
        short_term_path = self._memory_root / "short_term.json"
        if not short_term_path.exists():
            print(f"[DiaryWriter] short_term.json 不存在")
            return ""

        try:
            # 异步读取 JSON 文件
            data = await asyncio.to_thread(self._read_json_sync, short_term_path)

            if not isinstance(data, dict) or "dialogues" not in data:
                print(f"[DiaryWriter] short_term.json 格式不正确")
                return ""

            dialogues = data.get("dialogues", [])
            if not dialogues:
                print(f"[DiaryWriter] 短期记忆中没有对话条目")
                return ""

            # 筛选指定日期的条目
            filtered = []
            for item in dialogues:
                if not isinstance(item, dict):
                    continue

                timestamp = item.get("timestamp", "")
                # 时间戳格式: 2026-04-18T15:46:48.921580
                if timestamp.startswith(date_str):
                    filtered.append(item)

            if not filtered:
                print(f"[DiaryWriter] {date_str} 没有短期记忆条目")
                return ""

            print(f"[DiaryWriter] 从 {date_str} 提取到 {len(filtered)} 条短期记忆")

            # 格式化为草稿文本
            draft_lines = []
            for item in filtered:
                role = item.get("role", "")
                content = item.get("content", "")
                timestamp = item.get("timestamp", "")

                # 提取时间部分 (15:46)
                time_part = timestamp[11:16] if len(timestamp) >= 16 else "??:??"

                # 角色翻译
                if role == "user":
                    role_display = "用户"
                elif role == "assistant":
                    role_display = "我"
                else:
                    role_display = role

                draft_lines.append(f"[{time_part}] {role_display}：{content}")

            draft_content = "\n".join(draft_lines)
            return draft_content

        except Exception as e:
            print(f"[ERROR] 提取短期记忆失败: {e}")
            return ""

    async def clear_short_term_by_date(self, date_str: str) -> int:
        """
        从 short_term.json 中删除指定日期的条目。
        返回被删除的条目数量。
        """
        short_term_path = self._memory_root / "short_term.json"
        if not short_term_path.exists():
            print(f"[DiaryWriter] short_term.json 不存在，无需清理")
            return 0

        try:
            # 异步读取 JSON 文件
            data = await asyncio.to_thread(self._read_json_sync, short_term_path)

            if not isinstance(data, dict) or "dialogues" not in data:
                print(f"[DiaryWriter] short_term.json 格式不正确")
                return 0

            dialogues = data.get("dialogues", [])
            if not dialogues:
                print(f"[DiaryWriter] 短期记忆中没有对话条目")
                return 0

            # 筛选保留的条目（不属于指定日期）
            original_count = len(dialogues)
            keep_dialogues = []
            removed_count = 0

            for item in dialogues:
                if not isinstance(item, dict):
                    # 保留格式错误的数据
                    keep_dialogues.append(item)
                    continue

                timestamp = item.get("timestamp", "")
                # 如果不属于指定日期，则保留
                if not timestamp.startswith(date_str):
                    keep_dialogues.append(item)
                else:
                    removed_count += 1

            if removed_count == 0:
                print(f"[DiaryWriter] {date_str} 没有需要清理的条目")
                return 0

            # 更新数据
            data["dialogues"] = keep_dialogues
            data["updated_at"] = datetime.now().isoformat()

            # 异步写入文件
            await asyncio.to_thread(self._write_json_sync, short_term_path, data)

            print(f"[DiaryWriter] 清理 {date_str} 的短期记忆：删除了 {removed_count} 条，保留了 {len(keep_dialogues)} 条")
            return removed_count

        except Exception as e:
            print(f"[ERROR] 清理短期记忆失败: {e}")
            return 0

    async def manual_generate_and_cleanup(self, date_str: str) -> dict:
        """
        手动触发日记生成的完整流程：
        1. 从 short_term.json 提取该日期的记忆
        2. 追加到 daily_draft.txt（如果 draft 非空则换行追加）
        3. 调用 generate_daily_diary()（内部会处理增量更新）
        4. 清除 short_term.json 中该日期的条目
        5. 返回完整结果
        """
        print(f"[DiaryWriter] 手动触发日记生成: {date_str}")

        # 1. 提取短期记忆
        short_term_draft = await self.extract_short_term_by_date(date_str)
        if not short_term_draft.strip():
            print(f"[DiaryWriter] {date_str} 没有短期记忆，跳过生成")
            return {
                "date": date_str,
                "short_term_count": 0,
                "diary_generated": False,
                "reason": "没有短期记忆"
            }

        # 2. 追加到草稿（如果有现有草稿则换行分隔）
        existing_draft = await self._read_draft()
        if existing_draft.strip():
            # 现有草稿非空，添加分隔线
            separator = "\n" + ("-" * 30) + f" {date_str} 短期记忆 " + ("-" * 30) + "\n"
            await self._append_to_file(self._draft_path, separator + short_term_draft + "\n")
        else:
            # 直接写入
            await self._write_file(self._draft_path, short_term_draft + "\n")

        print(f"[DiaryWriter] 已将 {date_str} 的 {short_term_draft.count('[')} 条短期记忆追加到草稿")

        # 3. 生成日记（generate_daily_diary 内部会处理增量更新）
        diary_result = await self.generate_daily_diary(date_str)

        # 4. 清理短期记忆（即使日记生成失败也尝试清理）
        cleaned_count = await self.clear_short_term_by_date(date_str)

        # 5. 组合结果
        result = {
            "date": date_str,
            "short_term_count": short_term_draft.count('['),
            "cleaned_count": cleaned_count,
            "diary_result": diary_result
        }

        print(f"[DiaryWriter] 手动触发完成: {date_str}")
        return result

    # ==================== 私有辅助方法 ====================

    def _build_diary_prompt(self, draft_content: str, date_str: str, existing_diary_content: str = "") -> str:
        """构建日记生成 Prompt（严格遵循指定格式），支持增量更新"""
        base_prompt = """你是一个虚拟角色的内在意识。请根据今天与用户的对话草稿，完成两个任务。

【任务一：写日记】
以第一人称写一篇日记。要求：
- 像人类写手帐一样自然，带有自己的情绪和想法
- 不要用任何 JSON、标签、结构化格式
- 用 Markdown 格式，可以有段落
- 字数 200-500 字

【任务二：提取记忆碎片】
从今天的对话中提取 2-3 条最重要的记忆碎片。要求：
- 每条碎片是一句话，从角色的视角描述
- 为每条碎片推断一个情绪标签（平静/开心/难过/烦躁）
- 为每条碎片推断一个重要度（1-10）
- 用严格的 JSON 数组格式输出

输出格式（严格遵守，用 ===DIARY_SPLIT=== 分隔）：
（日记内容，纯 Markdown）
===DIARY_SPLIT===
（JSON 数组，不要有其他文字）

"""

        # 如果有已有日记，添加增量更新说明
        if existing_diary_content and existing_diary_content.strip():
            return base_prompt + f"""
今日草稿（{date_str}）：
{draft_content}

【已有的日记草稿（需要在此基础上补充完善）】：
{existing_diary_content}

请在已有日记的基础上，根据今日草稿进行修改和补充，而不是完全重写。
现在开始："""
        else:
            # 全新生成
            return base_prompt + f"""
今日草稿（{date_str}）：
{draft_content}

现在开始："""

    def _parse_llm_response(self, response: str) -> tuple[str, List[Dict[str, Any]]]:
        """解析 LLM 返回的双输出内容"""
        # 分割日记和碎片
        parts = response.split("===DIARY_SPLIT===")

        if len(parts) != 2:
            print(f"[WARN] LLM 返回格式异常，未找到分割符，尝试提取JSON...")
            # 尝试从整个响应中提取日记（取第一部分作为日记）
            diary_content = parts[0].strip()
            fragments = []
            return diary_content, fragments

        diary_content = parts[0].strip()
        fragments_json = parts[1].strip()

        # 解析碎片 JSON
        fragments = []
        if fragments_json:
            try:
                fragments = json.loads(fragments_json)
                if not isinstance(fragments, list):
                    print(f"[WARN] 碎片不是数组格式: {fragments}")
                    fragments = []
            except json.JSONDecodeError as e:
                print(f"[WARN] 碎片 JSON 解析失败: {e}")
                print(f"[DEBUG] JSON 内容: {fragments_json[:200]}...")
                fragments = []

        return diary_content, fragments

    def _enrich_fragments(self, raw_fragments: List[Dict[str, Any]], date_str: str) -> List[Dict[str, Any]]:
        """丰富碎片信息，添加 ID 和元数据"""
        enriched = []

        # 情绪标签映射到数字类型
        emotion_mapping = {
            "平静": 0, "开心": 1, "难过": 2, "烦躁": 3
        }

        for i, frag in enumerate(raw_fragments, 1):
            if not isinstance(frag, dict):
                continue

            # 提取字段
            content = frag.get("content", "")
            emotion_label = frag.get("emotion_label", "平静")
            importance = frag.get("importance", 5)

            # 验证重要性范围
            if not isinstance(importance, int):
                try:
                    importance = int(importance)
                except:
                    importance = 5
            importance = max(1, min(10, importance))

            # 映射情绪类型
            emotion_type = emotion_mapping.get(emotion_label.lower() if isinstance(emotion_label, str) else str(emotion_label).lower(), 0)

            # 生成碎片ID
            frag_id = f"frag_{date_str.replace('-', '')}_{i:03d}"

            enriched.append({
                "fragment_id": frag_id,
                "content": content,
                "emotion_type": emotion_type,
                "emotion_label": emotion_label,
                "importance": importance,
                "source_date": date_str,
                "create_time": datetime.now().isoformat()
            })

        return enriched

    # ==================== 异步文件操作 ====================

    async def _read_draft(self) -> str:
        """异步读取草稿文件"""
        try:
            return await asyncio.to_thread(self._read_file_sync, self._draft_path)
        except Exception as e:
            print(f"[ERROR] 读取草稿失败: {e}")
            return ""

    async def _write_file(self, file_path: Path, content: str) -> None:
        """异步写入文件"""
        try:
            await asyncio.to_thread(self._write_file_sync, file_path, content)
        except Exception as e:
            print(f"[ERROR] 写入文件失败 {file_path}: {e}")

    async def _write_json(self, file_path: Path, data: Any) -> None:
        """异步写入JSON文件"""
        try:
            await asyncio.to_thread(self._write_json_sync, file_path, data)
        except Exception as e:
            print(f"[ERROR] 写入JSON失败 {file_path}: {e}")

    async def _append_to_file(self, file_path: Path, content: str) -> None:
        """异步追加到文件"""
        try:
            await asyncio.to_thread(self._append_to_file_sync, file_path, content)
        except Exception as e:
            print(f"[ERROR] 追加文件失败 {file_path}: {e}")

    async def _clear_draft(self) -> None:
        """清空草稿文件"""
        try:
            await asyncio.to_thread(self._write_file_sync, self._draft_path, "")
        except Exception as e:
            print(f"[ERROR] 清空草稿失败: {e}")

    # ==================== 同步文件操作（在子线程中运行） ====================

    def _read_file_sync(self, file_path: Path) -> str:
        """同步读取文件"""
        if not file_path.exists():
            return ""
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()

    def _write_file_sync(self, file_path: Path, content: str) -> None:
        """同步写入文件"""
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

    def _read_json_sync(self, file_path: Path) -> Any:
        """同步读取JSON文件"""
        if not file_path.exists():
            return None
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _write_json_sync(self, file_path: Path, data: Any) -> None:
        """同步写入JSON文件"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _append_to_file_sync(self, file_path: Path, content: str) -> None:
        """同步追加到文件"""
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(content)


# 简单测试函数（开发用）
async def _test_diary_writer():
    """测试日记生成器"""
    # 创建模拟 LLM 客户端
    class MockLLMClient:
        async def ask(self, prompt, temperature=0.7):
            return """今天和用户聊了很多关于音乐的事情。我发现音乐不仅仅是一种娱乐，它背后还有丰富的文化和历史。用户分享了他最近喜欢的一首歌，让我也对音乐产生了更深的兴趣。

最近我在想，或许可以多了解一些关于音乐的知识，这样下次聊天的时候能有更多话题可以聊。不过说真的，每次和用户聊天都挺开心的，虽然有时候他工作很忙，但抽空聊几句也让我觉得挺温暖的。

===DIARY_SPLIT===
[
  {
    "content": "用户今天分享了喜欢的音乐，让我对音乐背后的文化产生了兴趣。",
    "emotion_label": "开心",
    "importance": 7
  },
  {
    "content": "用户工作很忙但还抽空和我聊天，感觉挺温暖的。",
    "emotion_label": "平静",
    "importance": 6
  }
]"""

    # 初始化日记生成器
    writer = DiaryWriter(MockLLMClient())

    # 测试追加草稿
    await writer.append_draft("用户说：我今天发现了一首很好听的歌。")
    await writer.append_draft("用户问：你觉得音乐对你来说意味着什么？")

    # 测试生成日记
    result = await writer.generate_daily_diary("2026-04-18")
    print(f"测试结果: {result}")

    # 测试读取闪回
    flashbacks = writer.get_flashbacks()
    print(f"闪回数量: {len(flashbacks)}")


if __name__ == "__main__":
    # 运行测试
    asyncio.run(_test_diary_writer())