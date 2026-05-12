"""
日记草稿追加 + 跨日归档
"""
import re
import os
from datetime import datetime
from typing import Dict
from pathlib import Path


class DiaryWriter:
    def __init__(self, memory_root: Path):
        self._memory_root = memory_root
        self._last_active_date = ""  # 冷启动：空字符串触发首次写入必定标注日期

    @property
    def last_active_date(self):
        return self._last_active_date

    @last_active_date.setter
    def last_active_date(self, value):
        self._last_active_date = value

    def append_diary_draft(self, text: str) -> None:
        draft_path = self._memory_root / "diary/drafts/daily_draft.txt"
        try:
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            today = datetime.now().strftime("%Y-%m-%d")
            with open(draft_path, 'a', encoding='utf-8') as f:
                if self._last_active_date != today:
                    f.write(f"\n--- {today} ---\n")
                    self._last_active_date = today
                timestamp = datetime.now().strftime("%H:%M")
                f.write(f"[{timestamp}] {text}\n")
        except Exception as e:
            print(f"[WARN] 日记草稿写入失败: {e}")

    def _catch_up_diary(self) -> list:
        draft_path = self._memory_root / "diary/drafts/daily_draft.txt"
        if not draft_path.exists() or draft_path.stat().st_size == 0:
            return []
        today = datetime.now().strftime("%Y-%m-%d")
        archived_dates: list = []
        try:
            draft_content = draft_path.read_text(encoding="utf-8")
            sections: Dict[str, list] = {}
            current_date = None
            guessed = False  # 标记是否从 mtime 推测（无 --- date --- 分隔符）
            for line in draft_content.split("\n"):
                m = re.match(r'^--- (\d{4}-\d{2}-\d{2}) ---$', line)
                if m:
                    current_date = m.group(1)
                    if current_date not in sections:
                        sections[current_date] = []
                    continue
                if current_date:
                    sections[current_date].append(line)
            if not sections:
                guessed = True
                mtime = draft_path.stat().st_mtime
                guessed_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
                sections[guessed_date] = draft_content.split("\n")

            diary_dir = self._memory_root / "diary" / "daily"
            diary_dir.mkdir(parents=True, exist_ok=True)
            archived_count = 0
            remaining_lines: list = []

            for dt, lines in sections.items():
                if dt == today:
                    remaining_lines = lines
                    continue
                body = "\n".join(lines).strip()
                # guessed 模式下 body 必然等于全文，不应跳过
                if not body or (not guessed and body == draft_content.strip()):
                    continue
                diary_path = diary_dir / f"{dt}.md"
                header = f"# {dt} 对话日记\n\n"
                if diary_path.exists():
                    existing = diary_path.read_text(encoding="utf-8")
                    with open(diary_path, 'w', encoding='utf-8') as f:
                        f.write(existing + "\n\n" + body)
                else:
                    with open(diary_path, 'w', encoding='utf-8') as f:
                        f.write(header + body)
                archived_count += 1
                archived_dates.append(dt)
                print(f"[日记] 启动补归档: {dt} ({len(body)} 字符)")

            if archived_count > 0:
                today_header = f"--- {today} ---\n" if remaining_lines else ""
                new_draft = today_header + "\n".join(remaining_lines) if remaining_lines else ""
                draft_path.write_text(new_draft, encoding="utf-8")

        except Exception as e:
            print(f"[WARN] 启动补归档异常: {e}")

        return archived_dates

    def check_cross_day_diary(self) -> list:
        """检测跨日并归档，返回本次归档的日期列表"""
        today = datetime.now().strftime("%Y-%m-%d")
        if self._last_active_date == today:
            return []
        self._last_active_date = today
        draft_path = self._memory_root / "diary/drafts/daily_draft.txt"
        if not draft_path.exists() or draft_path.stat().st_size == 0:
            return []
        archived_dates: list = []
        try:
            draft_content = draft_path.read_text(encoding="utf-8")
            sections: Dict[str, list] = {}
            current_date = None
            for line in draft_content.split("\n"):
                m = re.match(r'^--- (\d{4}-\d{2}-\d{2}) ---$', line)
                if m:
                    current_date = m.group(1)
                    if current_date not in sections:
                        sections[current_date] = []
                    continue
                if current_date:
                    sections[current_date].append(line)
            if not sections:
                # 无日期标签兜底：用文件 mtime 推测
                mtime = draft_path.stat().st_mtime
                guessed_date = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
                sections[guessed_date] = draft_content.split("\n")

            diary_dir = self._memory_root / "diary" / "daily"
            diary_dir.mkdir(parents=True, exist_ok=True)
            remaining: list = []

            for dt, lines in sections.items():
                if dt == today:
                    remaining = lines
                    continue
                body = "\n".join(lines).strip()
                if not body:
                    continue
                diary_path = diary_dir / f"{dt}.md"
                if diary_path.exists():
                    existing = diary_path.read_text(encoding="utf-8")
                    with open(diary_path, 'w', encoding='utf-8') as f:
                        f.write(existing + "\n\n" + body)
                else:
                    with open(diary_path, 'w', encoding='utf-8') as f:
                        f.write(f"# {dt} 对话日记\n\n{body}")
                archived_dates.append(dt)
                print(f"[日记] {dt} 日记已归档 ({len(body)} 字符)")

            today_header = f"--- {today} ---\n" if remaining else ""
            draft_path.write_text(today_header + "\n".join(remaining) if remaining else "", encoding="utf-8")

        except Exception as e:
            print(f"[WARN] 日记归档失败: {e}")

        return archived_dates
