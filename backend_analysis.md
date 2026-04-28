# Yume AI Agent — 系统架构分析

> 分析日期: 2026-04-27 | 版本: V4.0 双 LLM 记忆查询架构 | 健康度: **B-**

---

## 一、总览

| 维度 | 评级 | 变化 | 说明 |
|------|------|------|------|
| 架构健康度 | **B-** | D→B- | 上帝对象已拆分，假实现已替换 |
| 线程安全 | **C+** | D→C+ | asyncio+threading 混用但有关键锁保护 |
| 代码质量 | **B-** | C-→B- | 旧代码已清理，注释块大幅减少 |
| 功能完整度 | **C+** | D→C+ | 记忆搜索/日记已真实化，部分功能仍为空桩 |
| 可维护性 | **B** | D-→B | 驱动拆分、提示词文件化、FSM 类型安全化 |

---

## 二、整体架构

```
main.py (入口 + 生命周期)
├── WSServer ─── MessageRouter ─── JSON-RPC 2.0 协议
│   └── send_queue (普通 Queue，非 asyncio)
│
├── StateMachine (FSM)
│   ├── State: IDLE / THINK / DO_TOOL / ASK_USER / WAIT_CONFIRM / FINISH
│   ├── Event: USER_INPUT / NEED_TOOL / TOOL_RETURN / TASK_COMPLETE / ERROR / TIMEOUT
│   └── actions.py: THINK Action (双LLM) + DO_TOOL Action (工具执行)
│
├── YumeDriver (总调度，~400 行)
│   ├── LLM (DeepSeek, think=0.2 / speak=0.7)
│   ├── MemoryCore (统一记忆)
│   ├── TTSManager (TTS 队列 + 后台消费)
│   ├── FrontendBridge (Live2D 指令 + 文本推送)
│   └── SpontaneousEngine (沉默主动发言)
│
├── Plugin System
│   ├── ToolRegistry → 5 adapters (读写文件/搜索记忆/写日记/归档)
│   └── 查询子 LLM 直接调用工具，不经过 call_tool 链
│
├── EventBus (50+ 事件类型的发布订阅)
│   ├── ComfortModel (舒适度/心情/冲动)
│   ├── EmotionEngine (情绪平滑 0-3)
│   └── InstinctHandler (本能触发)
│
└── Services
    ├── TTSService (DashScope CosyVoice, WebSocket 长连接)
    └── LLMAPI (httpx, 同步+异步+流式)
```

---

## 三、已完成功能（可直接使用）

### 3.1 双 LLM 对话架构 ★ 核心

| 组件 | 实现 | 状态 |
|------|------|------|
| 主 LLM（yume） | DeepSeek, temp=0.7, 无工具定义, 纯角色对话 | ✅ 完成 |
| 查询子 LLM | 独立 LLMAPI 实例, 带工具 schema, 线程内执行→销毁 | ✅ 完成 |
| 预检索（grep） | 关键词搜索日记/长期记忆, ~50ms, 注入主 LLM 上下文 | ✅ 完成 |
| 缓冲信号检测 | 正则匹配 "让我想想……" 等, 自动触发深挖 | ✅ 完成 |
| 流式输出 + TTS 流水线 | `chat_stream_async` 逐 token, 遇句号即入 TTS 队列 | ✅ 完成 |
| 提示词文件化 | `agent_memory/prompts/yume_system.md` + `query_system.md` | ✅ 完成 |

### 3.2 记忆系统

| 功能 | 实现 | 状态 |
|------|------|------|
| 短期记忆 | `short_term_history` 列表, 实时同步写 `core/short_term.json` | ✅ 完成 |
| 长期记忆 | `core/memories.md` 追加, 按天分段 | ✅ 完成 |
| 日记系统 | 跨天自动归档 → `diary/daily/YYYY-MM-DD.md` | ✅ 完成 |
| grep 全文搜索 | `search_diary()`, `search_memories()` 真实文件搜索 | ✅ 完成 |
| 上下文构建 | `build_context()` 组装记忆+时间+人格注入主 LLM | ✅ 完成 |
| 遗忘机制 | 重要度/时间/混合 三种策略（框架已实现） | ✅ 完成 |
| 记忆落盘兜底 | `flush()` 强刷 + `daemon=False` 写入线程 + `join(timeout=3)` | ✅ 完成 |

### 3.3 TTS 语音合成

| 功能 | 实现 | 状态 |
|------|------|------|
| CosyVoice 实时合成 | DashScope QwenTtsRealtime, WebSocket 长连接复用 | ✅ 完成 |
| 心跳保活 | 30s 间隔检查, 断线自动重连 | ✅ 完成 |
| 统一播报队列 | `TTSManager._tts_queue`, 后台消费线程, 一句一锁 | ✅ 完成 |
| 口型同步 | 24000Hz PCM → RMS 计算 → visemes 帧 | ✅ 完成 |
| 情绪语音指导 | 6 种情绪的中文语音指导词, `_build_instructions()` | ✅ 完成 |
| 文本分段 | `_split_tts_sentences()`, 标点断句 + 长句强制切分 | ✅ 完成 |
| 连接池管理 | `_all_connections` 追踪所有 WebSocket, 退出全关闭 | ✅ 完成 |

### 3.4 状态机

| 功能 | 实现 | 状态 |
|------|------|------|
| 6 状态 7 事件 | IDLE/THINK/DO_TOOL/ASK_USER/WAIT_CONFIRM/FINISH | ✅ 完成 |
| 转移规则注册 | `register_transition(from_state, event, to_state)` | ✅ 完成 |
| Action 绑定 | `register_action(state, callable)`, async action 支持 | ✅ 完成 |
| 类型安全键 | `TransitionKey = Tuple[str, str]` (避免跨模块 enum 不一致) | ✅ 完成 |

### 3.5 自驱动引擎

| 功能 | 实现 | 状态 |
|------|------|------|
| 沉默检测 | TriggerPolicy 基于静默时长+时段+上下文丰富度 | ✅ 完成 |
| 频率限制 | FreqLimiter: 最小间隔 300s, 最大 3次/时, 10次/天 | ✅ 完成 |
| 内容生成 | 模板(low priority) + LLM(high priority) 双模式 | ✅ 完成 |
| 连续发言模式 | 指数回退延迟, 概率递减自动停止 | ✅ 完成 |
| 用户响应追踪 | ResponseTracker 正向/中性/负向/无视 分类 | ✅ 完成 |

### 3.6 插件系统

| 功能 | 实现 | 状态 |
|------|------|------|
| 工具注册 | `ToolRegistry` 单例, 5 个 adapter 已注册 | ✅ 完成 |
| Legacy Schema 生成 | `get_legacy_schema()` → OpenAI function-calling JSON | ✅ 完成 |
| 查询子 LLM 工具调用 | 在线程内直接 `registry.execute_tool()` | ✅ 完成 |

### 3.7 前端通信

| 功能 | 实现 | 状态 |
|------|------|------|
| WebSocket 服务 | `ws_server.py`, JSON-RPC 2.0 协议, 8765 端口 | ✅ 完成 |
| TTS 音频推送 | Base64 PCM → `{"type": "TTS_AUDIO", ...}` → send_queue | ✅ 完成 |
| Live2D 指令 | `{"type": "LIVE2D_CMD", "cmd": "emotion", ...}` → send_queue | ✅ 完成 |
| 文本推送（打字机） | `{"type": "TEXT_CHUNK", ...}` / `{"type": "TEXT_THINKING", ...}` | ✅ 完成 |
| 终端输入 | stdin 线程 + `asyncio.run_coroutine_threadsafe` | ✅ 完成 |

---

## 四、部分实现（功能可用但有局限）

### 4.1 情绪系统 `[P1]`

**文件**: `core/emotion/emotion_engine.py` (56 行)

| 现状 | 问题 |
|------|------|
| 3 行核心算法（平滑+切换+衰减） | 对话中几乎不使用，`current_emotion` 固定为 `"neutral"` |
| `_build_instructions()` 支持 6 种情绪 | 实际传入的情绪只有 neutral |
| EmotionEngine 实例存在 | 没有与主对话流程打通——用户说的话不改变情绪 |

**改进方向**: 在 `action_think` 中根据用户输入内容调用 `emotion_engine.update_emotion()`, 并将当前情绪传入 TTS。

### 4.2 查询子 LLM 工具系统 `[P1]`

**文件**: `core/state_machine/actions.py` (`_run_memory_query`, `_execute_single_tool`)

| 现状 | 问题 |
|------|------|
| 5 个工具 adapter 已注册 | 查询子 LLM 实际只用过 search_memory, 其他未充分测试 |
| 工具结果截断为 500 字符 | 可能丢失关键信息 |
| `agent_brain.py` 仍有 20 路 if/elif 的 `call_tool()` | 查询子 LLM 不经过它，但旧路径仍存在 |

**改进方向**: 删除 `agent_brain.py:call_tool()` 的 if/elif 链(已被 plugin + query sub-LLM 替代); 工具结果长度可配置。

### 4.3 自驱动引擎与状态机的整合 `[P1]`

**文件**: `core/spontaneous/engine.py`, `core/agent/agent_driver.py`

| 现状 | 问题 |
|------|------|
| 引擎正常运行, 回调 → `_on_spontaneous_speech()` → TTS | 绕过状态机——如果引擎触发时状态机正忙(THINK), 会冲突 |
| `manual_trigger()` 方法 | 内部使用 `asyncio.run()` 在已有 event loop 中会崩溃 |
| `interrupt_handler.py` | 占位符, ASR 打断逻辑为空 |

**改进方向**: 自驱动发言也走状态机(新增 `SPONTANEOUS_TRIGGER` 事件); `manual_trigger` 改用 `asyncio.create_task`。

### 4.4 技能系统 `[P2]`

**文件**: `core/skill/skill_loader.py`, `core/skill/skill_matcher.py`

| 现状 | 问题 |
|------|------|
| `SkillLoader` 从 `skills/*.md` 加载 3 个 skill | 未集成到主对话流——skill 匹配结果未注入 LLM 上下文 |
| `SkillMatcher` 返回分级的 skill + experience text | experience text 的注入点不明确 |

**改进方向**: 在 `action_think` 中调用 `skill_matcher.match()` → 匹配到的 skill 提示注入 system prompt。

### 4.5 记忆压缩 `[P2]`

| 现状 | 问题 |
|------|------|
| `short_term_history` 上限裁剪 (`pop(0)`) | 旧的对话直接丢弃, 没有先压缩/摘要 |
| 跨天日记有 `check_cross_day_diary()` | diary 写入后不减少短期记忆量 |

**改进方向**: 超过 N 条时, 先用 LLM 对旧对话做摘要(1-2 句), 保留语义而非直接丢弃。

### 4.6 事件总线的 `send_queue` 忙等 `[P2]`

**文件**: `api/netwebsocket/ws_server.py`

```python
while self.send_queue.empty():   # 忙等
    await asyncio.sleep(0.01)    # 每秒 100 次无效唤醒
```

应改为 `asyncio.Queue` 用 `await queue.get()` 自然阻塞。

### 4.7 配置文件利用率低 `[P2]`

**文件**: `config/default.yaml` (完整的 YAML 配置树)

| 配置项 | 代码是否使用 |
|------|------|
| `ai.providers.*.temperature` | 部分（actions.py 硬编码 temperature 值） |
| `memory.*` (capacity, forgetting, WAL) | 框架存在但参数未从 YAML 读取 |
| `emotion.mappings` | 未使用，TTS emotion 硬编码在 `_build_instructions()` |
| `live2d.*` (animation_ranges, smoothing) | `FrontendBridge` 发送指令但参数未读取 YAML |

**改进方向**: 将硬编码的参数迁移到 YAML 配置读取。

---

## 五、未实现 / 空桩

### 5.1 `agent.py` 死代码 `[已解决]`

~~**文件**: `core/agent/agent.py`~~ — 文件已不存在，之前已删除。

### 5.2 `llm_collaborator.py` 废弃代码 `[已解决]`

~~**文件**: `services/llm/llm_collaborator.py` (585 行)~~ — 已删除（零 import 引用）。

### 5.3 ASR（语音识别）`[未来]`

`interrupt_handler.py` 有 `InterruptType`(VOICE_START, VOICE_CONTENT, MANUAL_STOP, TIMEOUT) 占位符, 但无任何 ASR 集成代码。

### 5.4 语义/向量搜索 `[未来]`

V4.0 中移除了 FAISS, 目前纯 grep 文本搜索。对于模糊语义匹配("上次聊到的那个有趣的话题")无能为力。

**可选方案**: 轻量级本地 embedding (如 `all-MiniLM-L6-v2` + numpy 余弦相似度), 或直接让查询子 LLM 读文件做语义判断。

### 5.5 用户认证 / 多用户 `[未来]`

`user/user_info.json` 为空, 无任何用户管理代码。当前为单用户设计。

### 5.6 测试覆盖 `[P1]`

| 模块 | 测试状态 |
|------|------|
| `memory_core` | 1 个冒烟测试 (`test_memory_closed_loop.py`) |
| `state_machine` | 无 |
| `actions` (双 LLM) | 无 |
| `TTS` | 无 |
| `WebSocket` | 无 |
| `spontaneous_engine` | 无 |

---

## 六、技术债务清单

| ID | 问题 | 严重度 | 文件 |
|------|------|------|------|
| D1 | `agent_brain.py:call_tool()` 20路 if/elif 未删除(已被插件替代) | P1 | `core/agent/agent_brain.py` |
| D4 | `ws_server.py` send_queue 忙等轮询 | P2 | `api/netwebsocket/ws_server.py` |
| D5 | `actions.py` 工厂函数内 `LLMAPI()` 直接新建(应注入) | P2 | `core/state_machine/actions.py:207-209` |
| D6 | 情绪系统与主对话流未打通 | P1 | `core/emotion/emotion_engine.py` |
| D7 | 自驱动引擎绕过状态机 | P1 | `core/spontaneous/engine.py` |
| D8 | 配置文件参数大量未使用 | P2 | `config/default.yaml` |
| D9 | 记忆溢出直接丢弃, 无压缩 | P2 | `core/memory/memory_core.py` |
| D10 | `manual_trigger()` 的 `asyncio.run()` 在运行 loop 中会崩溃 | P2 | `core/spontaneous/engine.py:453` |
| D11 | `[V1→V3]` 残留迁移标记 + 注释掉的旧代码 | P3 | 多个文件 |
| D12 | 工具返回截断 500 字符硬编码 | P3 | `core/state_machine/actions.py:186` |

---

## 七、当前能力矩阵

| 能力 | 水平 | 说明 |
|------|------|------|
| 角色对话 | ★★★★☆ | 人设稳定, 回复自然, 有记忆辅助 |
| 记忆检索 | ★★★☆☆ | grep 搜索可用, 缺语义搜索 |
| 语音合成 | ★★★★★ | CosyVoice 高质量, 口型同步, 流式 |
| 情绪表达 | ★★☆☆☆ | 框架存在但未接入对话流 |
| 主动发言 | ★★★☆☆ | 沉默触发可用, 但绕过状态机 |
| 工具调用 | ★★★☆☆ | 5 个工具可用, 但未充分测试 |
| 前端集成 | ★★★★☆ | TTS音频+Live2D指令+文本推送 |
| 可运维性 | ★★★☆☆ | 优雅退出已修复, 缺监控日志 |
| 扩展性 | ★★★☆☆ | 插件系统框架好, 但 skill 未接入 |

---

## 八、下一阶段建议优先级

```
P0 (立即):
  (无 — 已完成)

P1 (本周):
  1. 情绪系统接入主对话流（让 yume 真的有情绪变化）
  2. 删除 agent_brain.py:call_tool() 的 if/elif 链
  3. 自驱动引擎接入状态机
  4. 记忆溢出 → LLM 压缩摘要而非直接丢弃

P2 (本月):
  5. ws_server.py send_queue → asyncio.Queue
  6. 配置文件参数接入代码
  7. skill 系统接入主对话流
  8. 测试: 状态机 + actions 的端到端测试

P3 (按需):
  9. 语义搜索（轻量 embedding）
  10. ASR 语音输入集成
  11. 多用户支持
```
