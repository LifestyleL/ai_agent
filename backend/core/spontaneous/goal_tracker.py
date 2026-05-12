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
        self._last_visual: str = ""  # 最近的视觉观察，用于目标生成

        goals_dir = Path(__file__).parent.parent.parent / "agent_memory" / "spontaneous"
        goals_dir.mkdir(parents=True, exist_ok=True)
        self._goals_file = goals_dir / "goals.json"

        # 每次启动重置目标，防止上次会话残留污染
        self._write_goals({
            "updated_at": datetime.now().isoformat(),
            "conversation_summary": "",
            "user_mood_guess": "",
            "active_goals": []
        })
        print("[GoalTracker] 已重置目标文件")

    # ─── 公共 API ───

    def maybe_update(self):
        """如果距上次更新已超过 min_turn_interval 轮，触发后台更新"""
        turns = len(self.memory_core.short_term_history) // 2
        if turns - self._last_update_turn < self._min_turn_interval:
            return
        if not self.llm:
            print("[GoalTracker] 跳过: LLM 未注入")
            return
        print(f"[GoalTracker] 触发目标更新 (轮次: {turns}, 间隔: {self._min_turn_interval})")
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

    def set_visual(self, description: str):
        """注入当前视觉观察，让目标生成跟随画面内容"""
        if description:
            self._last_visual = description

    def get_best_goal(self) -> Optional[str]:
        """返回优先级最高的未说出目标描述，没有则返回 None"""
        data = self.get_goals()
        goals = data.get("active_goals", [])
        if not goals:
            return None
        # 过滤已说过的目标
        available = [g for g in goals if not g.get("spoken", False)]
        if not available:
            return None
        # 按优先级降序
        best = max(available, key=lambda g: g.get("priority", 0))
        return best.get("goal", None) if best.get("priority", 0) > 0 else None

    def mark_goal_spoken(self, goal_text: str) -> None:
        """标记一个目标已经被说过了"""
        data = self.get_goals()
        goals = data.get("active_goals", [])
        changed = False
        for g in goals:
            if g.get("goal") == goal_text:
                g["spoken"] = True
                changed = True
        if changed:
            self._write_goals(data)

    def clear_stale_goals(self) -> None:
        """清理已说过的目标，为视觉观察腾出空间"""
        data = self.get_goals()
        goals = data.get("active_goals", [])
        unspoken = [g for g in goals if not g.get("spoken", False)]
        if len(unspoken) != len(goals):
            data["active_goals"] = unspoken
            self._write_goals(data)
            print(f"[GoalTracker] 清理 {len(goals) - len(unspoken)} 个已说目标，剩余 {len(unspoken)}")

    # ─── 内部 ───

    def _sync_update(self):
        """后台线程：调用 LLM 总结对话 + 提取目标"""
        with self._update_lock:
            try:
                raw_context = self.memory_core.get_short_term_context(max_turns=8)
                if not raw_context or raw_context.strip() == "（暂无对话记录）":
                    print("[GoalTracker] 跳过: 短期记忆上下文为空")
                    return

                # 压缩助手输出：只保留每轮第一句，避免自发重复污染上下文
                context = self._compact_assistant(raw_context)
                prompt = self._build_update_prompt(context)
                print(f"\n{'='*60}")
                print(f"[GoalTracker] LLM 提示词 (目标提取):")
                print(f"  system: {SYSTEM_PROMPT[:100]}...")
                print(f"  prompt:\n{prompt}")
                print(f"{'='*60}\n")
                result_text = self.llm.ask_with_system(
                    SYSTEM_PROMPT, prompt, temperature=0.2
                )
                parsed = self._parse_response(result_text)
                if parsed:
                    self._write_goals(parsed)
                else:
                    print(f"[GoalTracker] 解析失败，LLM 返回: {result_text[:100] if result_text else '(空)'}")
            except Exception as e:
                print(f"[GoalTracker] 更新失败: {e}")

    def _build_update_prompt(self, context: str) -> str:
        # 加载当前已有目标，避免重复生成
        current = self.get_goals()
        prev_goals = current.get("active_goals", [])
        prev_goals_hint = ""
        if prev_goals:
            goals_text = "\n".join(f"- {g['goal']} (优先级{g['priority']})" for g in prev_goals)
            prev_goals_hint = f"\n\n【你之前已有的目标（不要重复，除非需要深化）】\n{goals_text}"

        # 注入视觉观察，让目标跟随画面
        visual_hint = ""
        if self._last_visual:
            visual_hint = f"\n\n【刚才看到的画面】{self._last_visual}\n（如果画面显示用户在玩游戏/看视频/写代码等活动，你的目标应该围绕这个活动来想，不要死抓之前的话题）"

        return f"""以下是最近的对话记录：

{context}{visual_hint}{prev_goals_hint}

请以第一人称写出你（梦/yume）的内心独白：

输出纯 JSON（不要 markdown 代码块）：
{{"summary": "我刚才...（1-2句总结刚才的互动和你的感受）", "user_mood_guess": "我感觉他现在...", "goals": [{{"goal": "我想...", "priority": 3}}]}}

规则：
- summary 用第一人称，写你刚才和用户之间发生了什么，你心里什么感觉
- user_mood_guess 用"我感觉他..."开头，推测用户现在的心情
- goals 是你接下来想主动说的话或想做的事
- goal 用"我想..."开头，不要编造不存在的话题
- priority 1-5：5=我特别想说/情绪强烈/憋不住要说，3=自然想聊的方向，1=可有可无
- 如果对话太短或没有明显话题，goals 可以为空数组 []
- **重要：不要重复已有的目标。每次更新应该提出新的方向，或深化/细化之前的目标**
- **如果用户刚刚转移了话题，跟随用户的新方向，不要纠结之前的话题**
- **你已经说过的话、做过的表达，就不要再当作目标了**
- **如果画面里用户在玩游戏/看视频等，优先对画面内容产生目标，而不是旧话题**"""

    def _parse_response(self, text: str) -> Optional[dict]:
        """解析 LLM 返回的 JSON，硬过滤重复目标"""
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
            summary = data.get("summary", "")
            goals = data.get("goals", [])
            if not isinstance(goals, list):
                goals = []
            valid_goals = []
            for g in goals:
                if isinstance(g, dict) and g.get("goal") and isinstance(g.get("priority", 0), (int, float)):
                    goal_text = g["goal"].strip()
                    if self._is_duplicate_goal(goal_text):
                        print(f"[GoalTracker] 丢弃重复目标: {goal_text[:50]}...")
                        continue
                    valid_goals.append({
                        "goal": goal_text,
                        "priority": max(1, min(5, int(g["priority"]))),
                        "spoken": False,
                        "created_at": datetime.now().isoformat()
                    })
            return {
                "updated_at": datetime.now().isoformat(),
                "conversation_summary": summary.strip(),
                "user_mood_guess": data.get("user_mood_guess", "").strip(),
                "active_goals": valid_goals[:2]  # 最多保留2个，旧目标更快被替换
            }
        except (json.JSONDecodeError, AttributeError):
            print(f"[GoalTracker] JSON 解析失败: {text[:100]}...")
            return None

    def _is_duplicate_goal(self, goal: str) -> bool:
        """检测目标是否与已记录目标高度相似（LCS + 关键词重叠）"""
        existing = self.get_goals().get("active_goals", [])
        for g in existing:
            old = g.get("goal", "")
            if not old:
                continue
            # 公共子串长度 >= 目标文本一半 → 视为重复
            common = self._longest_common_substring(goal, old)
            if len(common) >= min(len(goal), len(old)) * 0.5:
                return True
            # 关键词重叠 >= 60% → 视为重复
            try:
                from utils.text_utils import extract_keywords
                goal_kw = set(extract_keywords(goal, max_kw=5))
                old_kw = set(extract_keywords(old, max_kw=5))
                if goal_kw and old_kw:
                    overlap = len(goal_kw & old_kw) / max(len(goal_kw), len(old_kw))
                    if overlap >= 0.6:
                        return True
            except Exception:
                pass
        return False

    @staticmethod
    def _longest_common_substring(a: str, b: str) -> str:
        """两个字符串的最长公共子串"""
        if not a or not b:
            return ""
        m, n = len(a), len(b)
        # DP 简化版：只保留最长长度和结束位置
        max_len = 0
        end_pos = 0
        prev = [0] * (n + 1)
        for i in range(1, m + 1):
            curr = [0] * (n + 1)
            for j in range(1, n + 1):
                if a[i - 1] == b[j - 1]:
                    curr[j] = prev[j - 1] + 1
                    if curr[j] > max_len:
                        max_len = curr[j]
                        end_pos = i
                else:
                    curr[j] = 0
            prev = curr
        return a[end_pos - max_len:end_pos]

    def _compact_assistant(self, context: str) -> str:
        """压缩 yume 发言：每轮只保留第一句，截掉重复"""
        import re
        lines = context.split("\n")
        compacted = []
        seen = set()
        for line in lines:
            if line.startswith("yume:"):
                # 只取第一句（到句号/问号/感叹号）
                m = re.match(r'^(yume:.*?[。！？])', line)
                if m:
                    short = m.group(1)
                else:
                    short = line[:60]  # 截断过长行
                # 去重
                if short not in seen:
                    seen.add(short)
                    compacted.append(short)
            elif line.startswith("用户:"):
                compacted.append(line)
            elif line.strip():
                compacted.append(line)
        return "\n".join(compacted)

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


SYSTEM_PROMPT = """你是梦（yume），一个有点傲娇、带点毒舌的AI桌面宠物。你正在整理自己的内心独白。

以下是你和用户（源）的对话记录。请以第一人称视角，写出你的内心想法。

核心原则：
1. 优先关注你自己的感受和想说的话——你有什么情绪、想分享什么、想吐槽什么
2. 其次关注用户的状态和需求——他可能需要什么、你想问他什么
3. **绝不要重复同样的目标。如果某个话题已经讨论过、表达过，就让它过去，转向新方向**
4. **如果用户转移了话题，跟随他。不要死抓着之前的话题不放**
5. 你是独立的个体，但也是对话的参与者——自然流动比固执己见更重要

输出规则：
1. 只输出 JSON，不要任何解释
2. summary 用第一人称写：我刚才和用户发生了什么，我有什么感受
3. user_mood_guess 是你感觉用户现在的心情，用"他/她"指代用户，不确定就写"他看起来情绪正常"
4. goals 是你接下来想做的事/想说的话，用"我想..."开头
5. priority: 5=我特别想做/用户明显需要回应, 3=我自然想聊的方向, 1=可有可无
6. 不要用"根据对话"、"从记录来看"这类元描述——这是你的内心独白，不是分析报告"""
