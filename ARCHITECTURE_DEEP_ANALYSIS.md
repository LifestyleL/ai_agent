# yume AI Agent 架构文档（Post-Phase-5）

> 分支: refactor/architecture-surgery | 日期: 2026-05-14

---

## 一、系统拓扑

```
┌────────────────────────────────────────────────────────────┐
│                     Entry Points                           │
│  ┌──────────────────────┐  ┌──────────────────────┐       │
│  │  main.py              │  │  run_qq.py            │       │
│  │  DI Container (18组件)│  │  手工 init (共享管线)  │       │
│  │  AgentScheduler + FSM │  │  GroupResponseDecider │       │
│  └──────────┬───────────┘  └──────────┬───────────┘       │
│             │                         │                    │
│             └─────────┬───────────────┘                    │
│                       ▼                                    │
│  ┌────────────────────────────────────────────────────┐   │
│  │              ThinkPipeline (ReAct 循环)              │   │
│  │                                                    │   │
│  │  Setup → [LLM ←→ ToolExec]×5 → Finalize            │   │
│  └──────────────────────┬─────────────────────────────┘   │
│                         │                                  │
│  ┌──────────────────────┴─────────────────────────────┐   │
│  │                 Channel 输出路由                     │   │
│  │  ┌────────────────┐  ┌────────────────┐            │   │
│  │  │ LocalChannel    │  │ QQChannel      │            │   │
│  │  │ TTS + Frontend  │  │ OneBot WS      │            │   │
│  │  │ 全量工具         │  │ 白名单工具      │            │   │
│  │  └────────────────┘  └────────────────┘            │   │
│  └────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────┘
```

## 二、管线流程

`ThinkPipeline.execute(ctx)` 四阶段：

| 阶段 | Stage | 职责 |
|------|-------|------|
| **A. 准备** | `MemoryRetrieveStage` → `SkillMatchStage` → `PromptBuildStage` | 记忆检索、技能匹配、构建 system_prompt |
| **B. 组装消息** | (内联) | `[system_prompt] + [messages] + [user_input]` |
| **C. ReAct 循环** | `LLMChatStage` ↔ `ToolExecStage` (最多 5 轮) | LLM 返回 tool_calls→执行→结果注入→循环；返回文本→退出 |
| **D. 收尾** | `FinalizeStage` | 记忆写入、目标追踪、Channel 输出 |

数据载体：`ThinkContext`（不可变 dataclass，通过 `ctx.replace()` 传递）。

## 三、Channel 抽象

| Channel | `is_external` | 输出目标 | 工具权限 |
|---------|--------------|---------|---------|
| `LocalChannel` | False | TTS + Live2D Frontend | 全量 (5 tools) |
| `QQChannel` | True | OneBot v11 WebSocket | 白名单 (3 tools) |

生命周期：`channel.pre_process(ctx)` → pipeline → `channel.post_process(ctx)` → `channel.send_response(ctx)`

- **LocalChannel**: `pre_process` 推情绪到 Live2D；`send_response` 调 dispatcher 推 TTS/Frontend
- **QQChannel**: `pre_process` 注入群聊上下文 + 意图关键词预搜索；`post_process` 做 `[PASS]` 检测；`send_response` 为空（WS handler 直接读 `ctx.response_text`）

## 四、工具系统

5 个内置工具，全部有 `inputSchema` 定义：

| 工具 | 参数 | 用途 |
|------|------|------|
| `search_memory` | `keyword` (必填) | 搜索长期记忆 |
| `read_file` | `filenames` (必填, array) | 读取文件 |
| `write_file` | `filename`, `content` (必填) | 写入文件 |
| `summarize_and_archive` | `max_lines` | 记忆归档 |
| `write_diary` | `target_date` | 日记生成 |

**安全层：**
- `ToolRegistry(allowlist={...})` — 白名单过滤（`list_tools()` + `call_tool()` 双端点）
- `_validate_params()` — 必填字段检查 + 类型警告
- `_resolve_safe_path()` — 路径遍历防护（拒绝 `../`/绝对路径/编码遍历）

执行流：`LLMChatStage` 传 tool definitions 给 LLM → LLM 返回 `tool_calls` → `ToolExecStage` → `registry.call_tool()` → 结果注入 `messages` 进入下一轮。

## 五、技能系统

3 个技能包（`backend/skills/*.md`）：

| 技能 | 触发关键词 | 绑定工具 |
|------|----------|---------|
| `search_memory` | 记得/以前/说过/聊过... | search_memory |
| `write_diary` | 日记/日志/记录... | write_diary |
| `read_file` | 读取/看看/打开/文件... | read_file |

匹配：`SkillMatchStage` → `SkillManager.match()` → LLM 语义分类（temperature=0, timeout=5s）→ 关键词兜底 → 匹配结果注入 `<skills>` 标签到 system_prompt。

生命周期：`load_all()` / `load_skill(path)` / `unload_skill(name)` / `reload()` — 支持热插拔。

## 六、状态机

6 状态 / 7 事件：

```
IDLE ──USER_INPUT──→ THINK ──TASK_COMPLETE──→ IDLE
THINK ──SPONTANEOUS_TRIGGER──→ THINK (自驱动快速通道)
IDLE ──SPONTANEOUS_TRIGGER──→ IDLE
```

`AgentScheduler.start()` → `setup_base_transitions(sm)` → 绑定 `State.THINK → orchestrator.think`。`orchestrator.think()` 组装 `ThinkContext`，调 `channel.pre_process()` → `pipeline.execute()` → `channel.post_process()` → `channel.send_response()`。

## 七、关键文件索引

| 层 | 文件 |
|----|------|
| **入口(本地)** | `backend/main.py` |
| **入口(QQ)** | `backend/run_qq.py` |
| **DI容器** | `backend/core/container.py` |
| **调度器** | `backend/core/agent/agent_scheduler.py` |
| **编排器** | `backend/core/agent/think_orchestrator.py` |
| **ReAct 管线** | `backend/core/think_pipeline/pipeline.py` |
| **LLM 阶段** | `backend/core/think_pipeline/llm_chat_stage.py` |
| **工具执行** | `backend/core/think_pipeline/tool_exec_stage.py` |
| **收尾** | `backend/core/think_pipeline/finalize.py` |
| **上下文** | `backend/core/think_pipeline/context.py` |
| **Channel ABC** | `backend/core/channel/base.py` |
| **本地频道** | `backend/core/channel/local_channel.py` |
| **QQ 频道** | `backend/core/channel/qq_channel.py` |
| **工具注册** | `backend/plugins/registry.py` |
| **工具实现** | `backend/plugins/builtin/adapters.py` |
| **技能管理** | `backend/core/skill/skill_manager.py` |
| **记忆 I/O** | `backend/core/memory/tools.py` |
| **状态机** | `backend/core/state_machine/state_machine.py` |
| **群聊决策** | `backend/adapters/qq/group_response_decider.py` |
| **技能包** | `backend/skills/*.md` |
| **系统提示词** | `backend/agent_memory/prompts/yume_system.md` |
| **QQ 提示词** | `backend/agent_memory/prompts/yume_qq_system.md` |

## 八、Phase 1-5 总结

| Phase | 目标 | 成果 |
|-------|------|------|
| **1** | MCP 化工具层 | `BaseTool.inputSchema` + `ToolRegistry.list_tools/call_tool` + `ToolResult` |
| **2** | ReAct 循环 | `LLMChatStage`(tools) ↔ `ToolExecStage` 替代固定 5 阶段 |
| **3** | Skill 系统 | `SkillManager` 热插拔 + LLM 语义匹配 + `skills/*.md` 文件加载 |
| **4** | Channel 抽象 | `Channel` ABC → LocalChannel/QQChannel → 消除 QQPipeline 双管线 |
| **5** | 安全与权限 | `allowlist` 白名单 + `_resolve_safe_path` 防遍历 + `_validate_params` 参数校验 |

从硬编码管线"应答器"到自主 ReAct"智能体"的架构手术完成。
