# 修改日志 (CHANGES)

> 本次改动范围: 后端 Python + 前端 TypeScript (Live2D)

---

## Phase 1: 止血清理

### 1.1 删除死代码 (DONE)

| 操作 | 文件 | 说明 |
|------|------|------|
| DELETE | `backend/core/agent/agent.py` | 导入即崩溃的死代码，确认无引用后删除 |

### 1.2 修复 WebSocket 忙等轮询 (DONE)

| 操作 | 文件 | 行 | 说明 |
|------|------|-----|------|
| REPLACE | `backend/api/netwebsocket/ws_server.py` | 101-106 | `while empty(): sleep(0.01)` → `await loop.run_in_executor(None, self.send_queue.get)` |

### 1.3 修复 search_memory 重复定义 (DONE)

| 操作 | 文件 | 行 | 说明 |
|------|------|-----|------|
| DELETE | `backend/core/agent/agent_brain.py` | 210-213 | 第二个 `search_memory` 定义（永不被命中） |

### 1.4 添加配置验证调用 (DONE)

| 操作 | 文件 | 行 | 说明 |
|------|------|-----|------|
| ADD | `backend/main.py` | 24 | `validate_config()` 调用，在 main() 开始处 |

### 1.5 统一 LLMAPI 实例创建 (DONE)

| 操作 | 文件 | 行 | 说明 |
|------|------|-----|------|
| ADD | `backend/main.py` | 28-29 | 创建共享 llm_deepseek, llm_qwen 实例 |
| MODIFY | `backend/core/state_machine/actions.py` | 142, 391 | 工厂函数接受可选 llm_deepseek/llm_qwen 参数 |
| UPDATE | `backend/main.py` | 58-59 | 传入 llm 实例到 action 工厂函数 |

---

## Phase 2: Live2D 架构重构

### 2.1 删除 Live2DManager 空桩 (DONE)

| 操作 | 文件 | 说明 |
|------|------|------|
| DELETE | `backend/deprecated/live2d/live2d_manager.py` | 整个文件删除 |
| DELETE | `backend/deprecated/live2d/` | 目录删除 |

### 2.2 清理 agent_driver 的 Live2D 引用 (DONE)

| 操作 | 文件 | 行 | 说明 |
|------|------|-----|------|
| DELETE | `backend/core/agent/agent_driver.py` | 23 | 移除 `from deprecated.live2d.live2d_manager import Live2DManager` |
| DELETE | `backend/core/agent/agent_driver.py` | 136 | 移除 `self.live2d = Live2DManager()` |
| DELETE | `backend/core/agent/agent_driver.py` | 160 | 移除 Voice() 的 `live2d=self.live2d` 参数 |
| ADD | `backend/core/agent/agent_driver.py` | 278-289 | 新增 `_send_live2d_cmd()` 方法，发送高层指令 |
| REPLACE | `backend/core/agent/agent_driver.py` | ~984-985 | `set_emotion_mode()` → `_send_live2d_cmd("emotion", ...)` |
| REPLACE | `backend/core/agent/agent_driver.py` | ~1050-1051 | 同上（自言自语分支） |

### 2.3 简化 agent_voice.py TTS 发送 (DONE)

| 操作 | 文件 | 行 | 说明 |
|------|------|-----|------|
| DELETE | `backend/core/agent/agent_voice.py` | 15 | 移除 `live2d` 构造函数参数 |
| REPLACE | `backend/core/agent/agent_voice.py` | 103-188 | ~90 行三重冗余 fallback → 5 行 send_queue 直接入队 |
| REPLACE | `backend/core/agent/agent_voice.py` | 277 | `self.live2d.set_emotion_mode()` → `send_queue.put({LIVE2D_CMD})` |

### 2.4 清理 ws_server / main / tts_service (DONE)

| 操作 | 文件 | 行 | 说明 |
|------|------|-----|------|
| DELETE | `backend/api/netwebsocket/ws_server.py` | 7 | 移除 Live2DManager import |
| DELETE | `backend/api/netwebsocket/ws_server.py` | 32 | 移除 `self.live2d = None` |
| DELETE | `backend/api/netwebsocket/ws_server.py` | 68-71 | 移除 `_handle_client` 中的 Live2D 初始化 |
| DELETE | `backend/main.py` | 40-44 | 移除 live2d 挂载代码 |
| DELETE | `backend/services/tts/tts_service.py` | 397-419 | 移除 `speak_to_live2d()` 死代码 |

### 2.5 前端：LAppAIWebSocket 新增指令处理 (DONE)

| 操作 | 文件 | 说明 |
|------|------|------|
| ADD | `CubismSdkForWeb-5-r.4/.../LAppAIWebSocket.ts` | `expressionQueue`, `motionQueue` 队列字段 |
| ADD | `CubismSdkForWeb-5-r.4/.../LAppAIWebSocket.ts` | `EMOTION_EXPRESSION_MAP` 情绪→表达式映射表 |
| ADD | `CubismSdkForWeb-5-r.4/.../LAppAIWebSocket.ts` | `_handleCommand()` 方法 |
| ADD | `CubismSdkForWeb-5-r.4/.../LAppAIWebSocket.ts` | `LIVE2D_CMD` 分支在 `_onMessage()` 中 |

### 2.6 前端：激活完整 AI 参数控制 (DONE)

| 操作 | 文件 | 说明 |
|------|------|------|
| REPLACE | `CubismSdkForWeb-5-r.4/.../lappmodel.ts:562-585` | 当前只控制嘴型 → 完整控制：嘴型+头部+身体+眨眼+手臂+指令队列 |
| 新增 | lappmodel.update() | 头部姿态平滑 (lerpHead x10)，身体姿态平滑 (lerpBody x5)，自动眨眼，手臂参数 |
| 新增 | lappmodel.update() | 消费 expressionQueue / motionQueue，调用 SDK setExpression/startRandomMotion |

---

## 架构变更总结

```
旧架构:                                 新架构:
─────────                              ─────────
Live2DManager (空桩)                   (删除)
agent_voice → 3 条路径发 TTS           agent_voice → send_queue (单路径)
agent_driver → set_emotion_mode(stub)  agent_driver → _send_live2d_cmd("emotion")
前端仅控制嘴型                         前端控制全部参数 + 表情 + 动作
```

## 后端 → 前端协议

```
TTS 音频:  {"type": "TTS_AUDIO", "audio_base64": "...", "visemes": [...]}
Live2D 指令: {"type": "LIVE2D_CMD", "cmd": "emotion", "emotion": "happy", "strength": 0.7}
Live2D 指令: {"type": "LIVE2D_CMD", "cmd": "motion", "motion": "idle"}
```

---

## Phase 3: 记忆系统重构 + 单模型简化

### 3.1 新建 context_builder.py — 自动上下文组装 (DONE)

| 操作 | 文件 | 说明 |
|------|------|------|
| CREATE | `backend/core/memory/context_builder.py` | 新建模块，替代旧的 "LLM 决策→工具调用→结果注入" 模式 |

核心功能：
- `build_context(user_input)` — 自动组装完整上下文
- `load_personality()` — 加载 `agent_memory/personality.md`
- `load_short_term_history(n)` — 从 `short_term.json` 加载最近 N 轮对话
- `_extract_keywords(text)` — 从用户输入提取关键词（过滤停用词）
- `search_long_term(keywords)` — 在 `agent_memory/` 目录下 grep 搜索相关记忆片段
- 输出格式化的上下文字符串，可直接注入 LLM prompt

### 3.2 memory_core.py 假桩替换为真实实现 (DONE)

| 操作 | 方法 | 说明 |
|------|------|------|
| REPLACE | `search_memory()` | 模拟字符串 → 真实 grep `agent_memory/` 目录 |
| REPLACE | `search_by_date()` | 模拟 → 真实读取 `diary/daily/` 目录按日期过滤 |
| REPLACE | `search_specific_memory()` | 委托给 `search_memory()` |
| REPLACE | `update_memory()` | 模拟 → 真实追加写入 `agent_memory/` 文件 |
| REPLACE | `update_long_term_memory()` | 模拟 → 返回"已由日记系统管理" |
| REPLACE | `write_daily_diary()` | 模拟 → 返回"已由日记流水线自动生成" |
| REPLACE | `auto_write_diary()` | 模拟 → 返回"已废弃" |
| REPLACE | `create_file()` | 模拟 → 真实创建文件 |
| REPLACE | `clear_file()` | 空操作 → 真实清空文件（带备份） |
| REPLACE | `write_file()` | 空操作 → 真实覆盖写入 |
| REPLACE | `append_to_file()` | 空操作 → 真实追加写入 |
| REPLACE | `set_short_term_memory_cache()` | 空操作 → 真实同步到 `short_term.json` |
| REPLACE | `tool_write_file()` | 模拟 → 委托 `create_file()` |
| REPLACE | `tool_read_file()` | 模拟 → 委托 `load_files()` |
| REPLACE | `tool_search_memory()` | 模拟 → 委托 `search_memory()` |
| ADD | `delete_memory_file()` | 新增：真实删除文件 |

### 3.3 agent_brain.py — 移除 ReAct 循环 (DONE)

| 操作 | 说明 |
|------|------|
| DELETE | `THINKING_PROMPT_TEMPLATE` (~80 行) — ReAct 思考提示词模板 |
| DELETE | `react_think()` (~70 行) — ReAct 主循环函数 |
| SIMPLIFY | `PERSONA_PROMPT_TEMPLATE` — 精简为只有人设 + 上下文字段 |
| REWRITE | `generate_reply()` — 使用 `context_builder.build_context()` 自动组装上下文 |

### 3.4 agent_driver.py — 移除双模型依赖 (DONE)

| 操作 | 行 | 说明 |
|------|-----|------|
| DELETE | 28 | 移除 `from services.llm.llm_collaborator import create_collaborator` |
| REPLACE | 107-115 | `self.collaborator = create_collaborator()` → 三个 DeepSeek 温度变体实例 |
| REPLACE | 132 | `llm_qwen = self.collaborator.llm_qwen` → 使用 `self.llm_speaker` |
| REPLACE | 139 | `Voice(tts=..., collaborator=self.collaborator)` → `Voice(tts=..., llm=self.llm_speaker)` |
| REPLACE | 183 | `SpontaneousEngine(..., llm_collaborator=self.collaborator)` → `SpontaneousEngine(..., llm=self.llm_speaker)` |
| REPLACE | 187 | `instinct_handler.init_instinct_handler(llm_qwen)` → `self.llm_speaker` |
| REPLACE | ~711 | Discovery handler: `self.collaborator.llm_qwen.ask()` → `self.llm_speaker.ask()` |
| REPLACE | ~752 | SurfingReview handler: `self.collaborator.llm_qwen.ask()` → `self.llm_speaker.ask()` |

### 3.5 单模型化 — 移除 Qwen 依赖 (DONE)

| 操作 | 文件 | 说明 |
|------|------|------|
| REPLACE | `backend/core/state_machine/actions.py` | 移除 Qwen import，`create_real_think_action` 不再接受 `llm_qwen` 参数 |
| REPLACE | `backend/core/state_machine/actions.py` | `can_answer` 分支：Qwen 回复生成 → DeepSeek speaker 变体 + `context_builder` |
| REPLACE | `backend/main.py` | 移除 Qwen import，移除 `llm_qwen` 实例创建 |
| REPLACE | `backend/config.py` | Qwen 配置改为可选（不再强制验证），移除错误提示中的 Qwen 引用 |
| REPLACE | `backend/utils/check_config.py` | 移除 Qwen 检查项，LLM 检查改为 DeepSeek 单模型 |
| REWRITE | `backend/core/spontaneous/content_generator.py` | `llm_collaborator` 参数 → `llm` 参数，`collaborate()` → `ask()` |
| REWRITE | `backend/core/spontaneous/engine.py` | `llm_collaborator` → `llm` 参数透传 |

### 3.6 llm_collaborator.py 彻底废弃 (DONE)

| 操作 | 文件 | 说明 |
|------|------|------|
| DEPRECATE | `backend/services/llm/llm_collaborator.py` | 已有废弃标记，零引用，保留文件仅供参考 |

---

## 架构变更总结 (Phase 3)

```
旧架构:                                 新架构:
─────────                              ─────────
双模型 Qwen + DeepSeek                  单模型 DeepSeek (3 温度变体)
Qwen: 人设对话生成                       thinker(0.2) + speaker(0.7) + writer(0.5)
DeepSeek: 工具调用决策
                                        
记忆检索: LLM 决策 → tool call → 注入    记忆检索: context_builder 自动组装 → 直接注入 prompt
react_think() 最多 8 步循环              generate_reply() 单次 LLM 调用

~15 个 MemoryCore 假桩方法              真实 grep 搜索 + 文件读写
返回 "模拟结果" 或空操作                 
```
