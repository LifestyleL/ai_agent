# Phase 5: 情绪系统 + 目标驱动自发言 + 配置文件化

> 日期: 2026-04-27 | 基于: Phase 4 (V4.0 双 LLM 架构) | 预估: 5-7 个改动日

---

## 目标

1. **配置文件参数化** — 硬编码参数迁移到 `config/default.yaml`
2. **情绪系统接入对话流** — `EmotionEngine` 不再孤岛，用户输入 → 情绪变化 → TTS 语气变化
3. **GoalTracker（新增）** — 后台 LLM 摘要对话 + 提取可聊目标，为自驱动提供动机
4. **自驱动引擎目标驱动化** — 沉默触发时基于 GoalTracker 的目标生成内容，不再随机模板
5. **清理死代码** — 删除 `agent_brain.py` 20 路 if/elif
6. **记忆溢出压缩** — 超上限改为 LLM 摘要而非直接丢弃

---

## 核心设计: GoalTracker —— 对话摘要 + 目标提取

### 问题

当前自驱动引擎是**纯反应式**的：沉默 → 随机概率 → 随机模板。没有"为什么要说话"的动机。

### 方案

新增 `core/spontaneous/goal_tracker.py`，负责在每次对话交换后，在后台用 LLM 总结对话状态、提取可继续聊的方向。

```
每次对话结束（daemon=False 后台线程, 不阻塞回复）:
┌──────────────────────────────────────────────────┐
│  GoalTracker._async_update()                      │
│  1. 取最近 N 条对话（从 short_term_history）        │
│  2. thinker LLM (temp=0.2):                       │
│     "总结对话内容, 识别用户状态/心情,               │
│      找出 1-3 个接下来可以自然聊到的方向"           │
│  3. 存入 spontaneous/goals.json                   │
│  4. 更新间隔: 每 2-3 轮对话更新一次                 │
└──────────────────────────────────────────────────┘

沉默触发时:
┌──────────────────────────────────────────────────┐
│  SpontaneousEngine                                │
│  1. 读 goals.json                                 │
│  2. 有目标 → speaker LLM: "你现在想聊[目标],       │
│     用自然的一句话开启对话"                        │
│  3. 无目标 → 退化为时间模板（兜底）                 │
└──────────────────────────────────────────────────┘
```

### 数据模型

```json
// agent_memory/spontaneous/goals.json
{
    "updated_at": "2026-04-27T18:30:00",
    "conversation_summary": "用户今天聊了老头环游戏，死了很多次，语气有点挫败但还在坚持。之前也聊了天气。",
    "user_mood_guess": "有点累但还在坚持",
    "active_goals": [
        {"goal": "问问老头环打到哪个boss了，表示理解挫败感", "priority": 3},
        {"goal": "[已过期] 聊天气", "priority": 0}
    ],
    "update_count": 12
}
```

### 设计约束

- **每次更新覆盖式替换** — 不追加，旧目标自动淘汰
- **目标最多 3 个** — LLM prompt 中明确限制
- **禁止编造** — prompt 约束"只基于对话中真实出现的内容"
- **LLM 调用限频** — 至少隔 2 轮对话才触发一次更新

---

## 任务 1: 配置文件参数化 `[基础]`

### 1.1 扩展 default.yaml

```yaml
spontaneous:
  enabled: true
  check_interval: 60
  min_silence: 600           # 最小沉默（秒），默认 10 分钟
  min_interval: 300          # 最小间隔（秒）
  max_per_hour: 3
  max_per_day: 10
  cool_down_after_reject: 120
  consecutive_max: 4
  goal_update_min_turns: 2   # 至少隔 N 轮对话才更新目标

emotion:
  smoothing_factor: 0.7
  decay_factor: 0.9
  switch_threshold: 2

memory:
  compression_threshold: 25
```

### 1.2 各模块从 config 读取

| 模块 | 原来 | 改为 |
|------|------|------|
| `spontaneous/engine.py` | `check_interval = 60` | config 读取 |
| `spontaneous/trigger_policy.py` | `silence < 1800` | config 读取 |
| `spontaneous/freq_limiter.py` | `self.rules = {...}` | config 读取 |
| `emotion/emotion_engine.py` | 因子硬编码 | config 读取（可选） |

---

## 任务 2: 情绪系统接入对话流

### 改动点

```
actions.py:
  用户输入 → emotion_engine.infer_from_text(user_input)
           → emotion_engine.update_emotion()
           → tts_manager.current_emotion = emotion_label
           → TTS 合成时传入变化后的 emotion

tts_manager.py:
  enqueue_text() / speak_final_text() 从 emotion_engine 读当前情绪
  而非固定 "neutral"

emotion_engine.py:
  新增 infer_from_text(text) → 基于关键词推断情绪类型
```

---

## 任务 3: GoalTracker `[新增核心]`

### 新建文件
- `core/spontaneous/goal_tracker.py` (~150 行)

### GoalTracker 类

```python
class GoalTracker:
    def __init__(self, memory_core, llm_thinker):
        self.memory_core = memory_core
        self.llm = llm_thinker        # temp=0.2, 适合推理
        self._last_update_turn = 0
        self._min_turn_interval = 2   # 至少隔 2 轮
        self._goals_file = Path(...) / "spontaneous/goals.json"

    def maybe_update(self):
        """如果距上次更新已超过 min_turn_interval 轮，触发后台更新"""
        current_turn = len(self.memory_core.short_term_history) // 2
        if current_turn - self._last_update_turn < self._min_turn_interval:
            return
        self._last_update_turn = current_turn
        t = threading.Thread(target=self._sync_update, daemon=False)
        t.start()

    def _sync_update(self):
        """后台线程: 调用 LLM 总结对话 + 提取目标"""
        ...

    def get_goals(self) -> dict:
        """读取当前目标和摘要"""
        ...

    def get_best_goal(self) -> Optional[str]:
        """返回优先级最高的目标描述"""
        ...
```

### 调用点

`actions.py:action_think()` → 在 Step 5 末尾，`start_async_memory_write` 之后，调用 `goal_tracker.maybe_update()`

### LLM Prompt 设计

```
你是对话分析助手。以下是最近的对话记录。

请完成两个任务：
1. 用 1-2 句话总结这段对话的内容和用户状态
2. 找出 1-3 个接下来可以自然聊到的方向（必须基于对话中真实出现的话题）

输出 JSON 格式：
{
  "summary": "...",
  "user_mood_guess": "...",
  "goals": [
    {"goal": "...", "priority": 3}
  ]
}

规则：
- goal 必须是对话中真实出现的话题或用户状态
- priority 1-5，越自然/越紧迫越高
- 不要编造用户没说过的事
- 如果对话太短或没话题，goals 可以为空数组
```

---

## 任务 4: 自驱动引擎目标驱动化

### 改动

`spontaneous/engine.py`:
- `_check_and_trigger()` 触发后，读 `goal_tracker.get_best_goal()`
- 有目标 → 调用 LLM 生成针对目标的发言
- 无目标 → 退化为时间模板

`spontaneous/content_generator.py`:
- 新增 `generate_from_goal(goal, context)` 方法
- 用 speaker LLM 根据目标生成自然的开场白

### 自驱动发言走状态机

新增 `Event.SPONTANEOUS_TRIGGER`，自驱动发言通过 FSM 的 THINK 状态处理，与用户输入共享同一队列，避免竞态。

---

## 任务 5: 删除 agent_brain 死代码

确认 `call_tool()` 无引用后删除 20 路 if/elif 链。保留 `generate_reply()` 如仍在使用。

---

## 任务 6: 记忆溢出压缩

`memory_core.py` 新增 `_compress_old_entries(n)` 方法：
1. 取最旧 N 条 → thinker LLM 生成 1-2 句摘要
2. 摘要写入长期记忆
3. 删除旧条目
4. LLM 失败时退化为 `pop(0)`

---

## 执行顺序

```
任务 1 (配置参数化) → 任务 2 (情绪接入) → 任务 3 (GoalTracker)
                                              ↓
                              任务 4 (自驱动目标化) 依赖 3
                                              ↓
                              任务 5 (删死代码) + 任务 6 (记忆压缩) 独立
```

## 预估影响

| 任务 | 新建 | 修改 | 风险 |
|------|------|------|------|
| 配置参数化 | 0 | 6+ | 低 |
| 情绪接入 | 0 | 4 | 低 |
| GoalTracker | 1 | 2 | 中（新 LLM 调用路径） |
| 自驱动目标化 | 0 | 3 | 中 |
| 删死代码 | 0 | 1 | 低 |
| 记忆压缩 | 0 | 1 | 低 |
