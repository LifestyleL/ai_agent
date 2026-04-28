"""
GoalTracker: 后台对话摘要 + 目标提取
每次对话交换后在后台线程中运行，不阻塞主回复流程
"""
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import config


class GoalTracker:
    """后台追踪对话状态，提取自驱动发言目标"""

    def __init__(self, memory_core, llm_thinker=None):
        self.memory_core = memory_core
        self.llm = llm_thinker
        self._last_update_turn = 0
        self._min_turn_interval = config.SPONTANEOUS_GOAL_UPDATE_MIN_TURNS
        self._update_lock = threading.Lock()

        goals_dir = Path(__file__).parent.parent.parent / "agent_memory" / "spontaneous"
        goals_dir.mkdir(parents=True, exist_ok=True)
        self._goals_file = goals_dir / "goals.json"

    # ─── 公共 API ───

    def maybe_update(self):
        """如果距上次更新已超过 min_turn_interval 轮，触发后台更新"""
        turns = len(self.memory_core.short_term_history) // 2
        if turns - self._last_update_turn < self._min_turn_interval:
            return
        if not self.llm:
            return
        self._last_update_turn = turns
        t = threading.Thread(target=self._sync_update, name="GoalTracker", daemon=False)
        t.start()

    def get_goals(self) -> dict:
        """读取当前目标和摘要"""
        if self._goals_file.exists():
            try:
                return json.loads(self._goals_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, IOError):
                pass
        return {
            "updated_at": "",
            "conversation_summary": "",
            "user_mood_guess": "",
            "active_goals": []
        }

    def get_best_goal(self) -> Optional[str]:
        """返回优先级最高的目标描述，没有则返回 None"""
        data = self.get_goals()
        goals = data.get("active_goals", [])
        if not goals:
            return None
        # 按优先级降序
        best = max(goals, key=lambda g: g.get("priority", 0))
        return best.get("goal", None) if best.get("priority", 0) > 0 else None

    # ─── 内部 ───

    def _sync_update(self):
        """后台线程：调用 LLM 总结对话 + 提取目标"""
        with self._update_lock:
            try:
                context = self.memory_core.get_short_term_context(max_turns=20)
                if not context or context.strip() == "（暂无对话记录）":
                    return

                prompt = self._build_update_prompt(context)
                result_text = self.llm.ask_with_system(
                    SYSTEM_PROMPT, prompt, temperature=0.2
                )
                parsed = self._parse_response(result_text)
                if parsed:
                    self._write_goals(parsed)
            except Exception as e:
                print(f"[GoalTracker] 更新失败: {e}")

    def _build_update_prompt(self, context: str) -> str:
        return f"""以下是最近的对话记录：

{context}

请完成：
1. 用 1-2 句话总结这段对话的内容和用户状态
2. 找出 1-3 个接下来可以自然聊到的方向

输出纯 JSON（不要 markdown 代码块）：
{{"summary": "...", "user_mood_guess": "...", "goals": [{{"goal": "...", "priority": 3}}]}}

规则：
- goal 必须基于对话中真实出现的话题或用户状态，禁止编造
- priority 1-5，越自然/越紧迫越高，5 表示用户明显需要关心
- 如果对话太短或没有明显话题，goals 可以为空数组 []
- 禁止提及"根据记忆"、"根据对话"等元描述"""

    def _parse_response(self, text: str) -> Optional[dict]:
        """解析 LLM 返回的 JSON"""
        if not text:
            return None
        # 切除可能的 markdown 代码块包装
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:]) if len(lines) > 1 else text
            if text.endswith("```"):
                text = text[:-3]
        try:
            data = json.loads(text)
            # 验证必要字段
            summary = data.get("summary", "")
            goals = data.get("goals", [])
            if not isinstance(goals, list):
                goals = []
            # 过滤无效 goal
            valid_goals = []
            for g in goals:
                if isinstance(g, dict) and g.get("goal") and isinstance(g.get("priority", 0), (int, float)):
                    valid_goals.append({
                        "goal": g["goal"].strip(),
                        "priority": max(1, min(5, int(g["priority"])))
                    })
            return {
                "updated_at": datetime.now().isoformat(),
                "conversation_summary": summary.strip(),
                "user_mood_guess": data.get("user_mood_guess", "").strip(),
                "active_goals": valid_goals[:3]
            }
        except (json.JSONDecodeError, AttributeError):
            print(f"[GoalTracker] JSON 解析失败: {text[:100]}...")
            return None

    def _write_goals(self, data: dict):
        """写入 goals.json"""
        try:
            self._goals_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            goals_count = len(data.get("active_goals", []))
            print(f"[GoalTracker] 目标已更新: {goals_count} 个目标, "
                  f"摘要: {data.get('conversation_summary', '')[:50]}...")
        except IOError as e:
            print(f"[GoalTracker] 写入失败: {e}")


SYSTEM_PROMPT = """你是对话分析助手。你的任务是分析对话记录，提取关键信息。

规则：
1. 只输出 JSON，不要任何解释
2. summary 必须基于对话真实内容，客观简洁
3. user_mood_guess 是推测的用户心情，不确定就写"无明显情绪"
4. goals 是可继续聊的方向，必须是对话中真实出现的，不要编造
5. priority: 5=用户明显需要关心/回应, 3=自然的话题延续, 1=可选项"""
