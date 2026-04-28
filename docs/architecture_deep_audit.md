# Yume AI Agent — 外科手术级架构深度审计报告

> 审计日期: 2026-04-28 | 审计人: 系统架构师视角 | 评级: **C**
> 这不是一份"改进建议清单"，这是一份**重构处方**。每一个问题都会追问"为什么有害"和"不改会怎样"。

---

## 第一步：深度项目扫描与精准解析

### 1.1 模块清单与职责

```
项目根目录 f:/AI/ai_agent/
│
├── backend/                          # ★ 核心后端 (Python)
│   ├── main.py                       # 入口：生命周期编排、依赖组装、信号处理
│   ├── config.py                     # 配置门面：YAML加载 + 150行属性导出 + CONFIG字典 + 验证
│   │
│   ├── core/                         # ★ 核心业务逻辑层
│   │   ├── agent/
│   │   │   ├── agent_driver.py       # YumeDriver：总调度 (~350行) — God Class
│   │   │   ├── agent_voice.py        # Voice：TTS说话委托
│   │   │   ├── tts_manager.py        # TTSManager：队列+后台消费线程+流式断句
│   │   │   ├── frontend_bridge.py    # FrontendBridge：Live2D指令+文本推送
│   │   │   └── agent_brain.py        # 遗留代码（call_tool 的20路if/elif）
│   │   │
│   │   ├── state_machine/
│   │   │   ├── state_machine.py      # StateMachine：6状态7事件FSM + 单例
│   │   │   ├── transitions.py        # 转移规则表（8条规则）
│   │   │   └── actions.py            # ★ 511行核心：THINK Action（God Function）+ DO_TOOL
│   │   │
│   │   ├── memory/
│   │   │   ├── memory_core.py        # ★ MemoryCore (~979行)：统一记忆 — God Class
│   │   │   ├── card_store.py         # CardStore：JSONL+邻接表+倒排索引+压缩
│   │   │   └── card.py               # Card数据类
│   │   │
│   │   ├── llm/
│   │   │   └── llm_api.py            # LLMAPI：同步+异步+流式（代码大量重复）
│   │   │
│   │   ├── emotion/
│   │   │   └── emotion_engine.py     # EmotionEngine：3行核心算法，56行总
│   │   │
│   │   ├── spontaneous/              # 自驱动引擎（沉默主动发言）
│   │   ├── event/                    # EventBus（50+事件类型发布订阅）
│   │   ├── behavior/                 # 驱动模型+人设+本能+嘟囔
│   │   └── skill/                    # 技能加载+匹配（未接入主流程）
│   │
│   ├── plugins/                      # 工具插件系统
│   │   ├── registry.py               # ToolRegistry：单例 + legacy schema兼容
│   │   ├── base_tool.py              # BaseTool：干净抽象（10行）
│   │   └── builtin/
│   │       ├── adapters.py           # 5个adapter实现
│   │       └── skills/               # 技能定义
│   │
│   ├── services/                     # ★ 服务层（3/4为空目录）
│   │   ├── tts/tts_service.py        # TTSService：DashScope CosyVoice
│   │   ├── llm/                      # 空（仅__init__.py）
│   │   ├── websocket/                # 空（仅__init__.py）
│   │   └── live2d/                   # 空（仅__init__.py）
│   │
│   ├── api/netwebsocket/
│   │   ├── ws_server.py              # WSServer：WebSocket + JSON-RPC
│   │   └── message_router.py         # 消息路由
│   │
│   ├── utils/
│   │   ├── config_loader.py          # YAML分层加载器（干净）
│   │   └── text_utils.py             # 文本工具
│   │
│   ├── config/
│   │   ├── default.yaml              # 完整YAML配置树
│   │   └── development.yaml          # 环境覆盖
│   │
│   ├── agent_memory/                 # 记忆文件存储
│   │   ├── cards/                    # 卡片记忆(JSONL+graph+index)
│   │   ├── diary/                    # 日记(daily/weekly/monthly/yearly)
│   │   ├── prompts/                  # LLM提示词文件
│   │   └── core/                     # personality/mood模板
│   │
│   ├── deprecated/                   # 废弃代码（仍占用空间）
│   ├── scripts/                      # 运维脚本
│   └── tests/                        # 测试（1个冒烟测试）
│
├── CubismSdkForWeb-5-r.4/            # ★ 前端 (TypeScript) — Live2D SDK
│   └── Samples/TypeScript/Demo/src/
│       ├── main.ts                   # 前端入口
│       ├── lapplive2dmanager.ts      # Live2D模型管理
│       ├── lappmodel.ts              # 模型定义
│       ├── lappdelegate.ts           # 应用委托
│       └── ai/                       # AI集成层
│           ├── AiWebSocket.ts         # WebSocket桥接 — 参数名双重定义
│           ├── AiAudioManager.ts      # 音频播放+口型
│           ├── AiIdleAnimator.ts      # 空闲动画
│           └── AiMicroNoise.ts        # 微噪声
│
├── agent_memory/                     # ★ 根级记忆目录（与backend/agent_memory重复概念）
├── deprecated/                       # 根级废弃（Live2D旧代码）
├── _deprecated_tests/                # 13个废弃测试脚本
├── docs/                             # 文档（含memory_evolution_roadmap.md）
└── *.md / *.mp3 / *.pcm              # 根目录散落大量临时文件
```

### 1.2 依赖关系图

```
                    ┌──────────────┐
                    │   main.py    │  (入口，依赖组装)
                    └──────┬───────┘
           ┌───────────────┼───────────────────┐
           ▼               ▼                    ▼
    ┌──────────┐   ┌──────────────┐    ┌──────────────┐
    │WSServer  │   │StateMachine  │    │  YumeDriver  │
    │(WebSocket│   │(FSM)         │    │  (总调度)     │
    │+JSON-RPC)│   └──────┬───────┘    └──────┬───────┘
    └──────────┘          │                   │
                          ▼                   │
                   ┌──────────────┐           │
                   │  actions.py  │◄──────────┘
                   │  (THINK+DO)  │──────┐
                   └──────┬───────┘      │
        ┌─────────────────┼───────┐      │
        ▼                 ▼       ▼      │
  ┌──────────┐   ┌──────────┐ ┌───────┐ │
  │LLMAPI    │   │MemoryCore│ │Plugin │ │
  │(sync+    │   │(God Class│ │Registry│ │
  │async+    │   │~979行)   │ │       │ │
  │stream)   │   └────┬─────┘ └───────┘ │
  └──────────┘        │                 │
                      ▼                 │
              ┌──────────────┐          │
              │  CardStore   │          │
              │  (存储引擎)   │          │
              └──────────────┘          │
                      │                 │
        ┌─────────────┼──────────┐      │
        ▼             ▼           ▼      │
  ┌──────────┐ ┌──────────┐ ┌────────┐  │
  │cards.jsonl│ │graph.json│ │index.  │  │
  │(追加写)   │ │(邻接表)  │ │json    │  │
  └──────────┘ └──────────┘ └────────┘  │
                                        │
  ┌─────────────────────────────────────┘
  │
  ▼
  ┌──────────────────────────────────────────┐
  │  前端 (TypeScript / Live2D SDK)           │
  │  AiWebSocket ◄── WebSocket ──► WSServer  │
  │  ├── TTS_AUDIO (Base64 PCM + visemes)    │
  │  ├── LIVE2D_CMD (emotion / motion)       │
  │  └── TEXT_CHUNK / TEXT_THINKING          │
  └──────────────────────────────────────────┘
```

### 1.3 数据流/调用链主路径

**用户输入 → 回复的主路径**：
```
用户输入(stdin或WebSocket)
  → main.py: stdin线程 → asyncio.run_coroutine_threadsafe
  → StateMachine.trigger(USER_INPUT)
  → IDLE → THINK
  → actions.action_think()  ← ★ 200行God Function
      ├─ Step 0: MemoryCore.build_structured_sections()
      │    ├─ detect_memory_intent()
      │    ├─ CardStore.retrieve() [BFS]
      │    └─ EmotionEngine.infer_from_text()
      ├─ Step 1: 构建system_prompt (persona + memory + diary + time)
      ├─ Step 2: 情绪标签 → TTSManager + FrontendBridge
      ├─ Step 3: chat_stream_async() + 逐句TTS入队
      ├─ Step 4: 检测缓冲信号 → 查询子LLM → 递归重入think
      └─ Step 5: 异步记忆写入 + GoalTracker
  → THINK → IDLE (TASK_COMPLETE)
```

**自驱动发言路径（绕过状态机）**：
```
SpontaneousEngine 定时检查
  → 沉默超过阈值
  → 生成发言内容（模板/LLM）
  → _on_spontaneous_speech() 回调
  → TTSManager.on_spontaneous_speech()
  → 直接TTS队列（不经过状态机！）
```

### 1.4 入口点、核心业务、基础设施识别

| 层 | 文件 | 行数 | 健康标签 |
|----|------|------|----------|
| **入口** | `main.py` | 223 | **混杂** — 依赖组装+生命周期+信号处理+调试打印混在一起 |
| **核心** | `actions.py:action_think` | ~200 | **致命** — God Function，做所有事 |
| **核心** | `YumeDriver` | ~350 | **过度耦合** — 持有所有子系统引用 |
| **核心** | `MemoryCore` | ~979 | **上帝类** — 记忆+日记+情绪+文件IO+兼容层 |
| **核心** | `CardStore` | ~550 | **清晰** — 职责明确，是最好的一部分 |
| **核心** | `StateMachine` | ~140 | **清晰但有冗余** — FSM本身干净，兼容方法混入 |
| **基础设施** | `LLMAPI` | ~238 | **混杂** — 同步/异步代码100%重复 |
| **基础设施** | `config.py` | ~200 | **过度耦合** — YAML门面+150行属性导出+CONFIG字典 |
| **基础设施** | `ToolRegistry` | ~55 | **清晰但弱** — 单例+legacy兼容拖累 |
| **基础设施** | `TTSManager` | ~222 | **混杂** — 队列管理+流式断句+缓冲语混在一起 |
| **前端** | `AiWebSocket.ts` | ~220 | **过度耦合** — 参数双重定义+解析+命令处理全在一个方法 |
| **前端** | `AiAudioManager.ts` | — | 待检查 |
| **废弃** | `deprecated/` 各处 | ~1000+ | **死代码** — 3个废弃目录未清理 |

---

## 第二步：混乱度与扩展性分析

### 2.1 致命问题 (BLOCKER)

#### [F1] `action_think()` — 200行God Function

**位置**: `backend/core/state_machine/actions.py:208-436`

这是整个系统中最危险的函数。它在一个闭包内完成了：
- 记忆意图检测 + 结构化搜索
- 情绪推断
- 提示词构建（persona + yume_system + 5个记忆分区）
- 情绪标签推送（TTS + Live2D）
- 流式LLM调用 + 逐句断句 + TTS入队
- 缓冲信号检测
- 查询子LLM启动（线程） + 递归重入
- 异步记忆写入
- 目标追踪器更新
- 状态机事件触发

**为什么是致命的**：
1. 无法单独测试任何一个步骤 — 要测试情绪推断就得mock LLM+Memory+TTS+Frontend
2. 修改任何一个步骤都可能破坏其他步骤 — 比如加一个记忆分区需要在6个地方修改
3. 递归调用 `await action_think(context)` (第412行) — 没有尾递归优化，context dict被当作可变状态随意修改
4. 错误处理粗糙 — 任何步骤失败就触发ERROR事件，没有局部降级

**场景推演**：
- 如果未来要加"图像理解"能力 → 需要在action_think中再加一个Step
- 如果要加"多轮工具调用链" → 现有的递归模式直接崩溃
- 如果要从DeepSeek换成Claude → 需要修改action_think中的LLM调用+prompt构建

#### [F2] MemoryCore — 979行God Class，违反单一职责原则

**位置**: `backend/core/memory/memory_core.py`

这个类承担了至少8种不同职责：
1. 短期记忆管理 (RAM buffer)
2. 卡片创建 (LLM提取 + 落盘)
3. 日记管理 (草稿写入 + 跨天归档)
4. 上下文组装 (5种不同context构建方法)
5. 记忆意图检测 (规则引擎)
6. 情绪管理 (通过持有的EmotionEngine)
7. 文件I/O工具 (原子写入 + 备份恢复)
8. 静态工具方法 (兼容旧工具系统的12+个静态方法)

**为什么是致命的**：
- 没有抽象边界 — 如果要换存储引擎（比如从JSONL换SQLite），需要重写整个类
- 测试不可能 — 979行中任何一行的修改都可能影响其他8个职责

#### [F3] 三方全局单例 + 模块级可变状态

```python
# state_machine.py
_global_state_machine: Optional[StateMachine] = None

# registry.py
_tool_registry_instance = ToolRegistry()

# agent_driver.py
_global_tts_queue = None

# main.py
ws_instance = WSServer()

# ws_server.py（推测）
ws_instance = ...  # 模块级实例
```

**为什么是致命的**：
- 测试隔离不可能 — 测试之间通过全局状态互相污染
- 无法创建多个Agent实例 — 整个系统被硬编码为单例
- 任何模块都可以随时修改全局状态，导致不可追踪的bug

### 2.2 严重问题 (CRITICAL)

#### [C1] LLMAPI实例到处创建 — 无法控池、无法Mock

在代码库中，`LLMAPI(...)` 被创建了至少 **5次**：
- `main.py:34` — llm_deepseek
- `actions.py:205-206` — llm_deepseek + llm_speaker（工厂函数内部）
- `actions.py:78` — `_run_memory_query()` 中的 query_llm
- `YumeDriver.__init__:42-51` — llm_thinker + llm_speaker
- `MemoryCore.__init__:53-57` — fallback llm_api

每个实例独立创建 httpx 连接池，无法共享、无法限流、无法统一Mock。

#### [C2] 配置系统双写灾难

`config.py` 维护了两套配置表示：
1. YAML树 → `get("ai", "deepseek", "api_key")`
2. 模块级常量 → `DEEPSEEK_API_KEY`
3. 兼容字典 → `CONFIG["deepseek"]["api_key"]`

每新增一个配置项，需要在 **3个地方** 修改代码：
- `default.yaml` — 声明默认值
- `config.py:22-101` — 导出模块级常量
- `config.py:112-149` — 更新CONFIG字典

当前有 **30+个模块级常量**（第22-101行），这意味着每加一个配置项要写3行代码。

#### [C3] 前端AiWebSocket参数双重定义

`AiWebSocket.ts` 的 `aiFaceParams` 对象中，每个Live2D参数定义了**两次**：
```typescript
// 第16-43行 — 使用Live2D原生名称
ParamEyeLOpen: 1.0,
ParamEyeROpen: 1.0,
// ...
// 第32-43行 — 使用短别名
eyeLeft: 1.0,
eyeRight: 1.0,
```

`_onMessage()` 方法（第109-204行，95行）同时处理 WebSocket消息解析、JSON-RPC协议检测、TTS音频分发、Live2D命令分发、参数映射、值裁剪——全部在一个方法里。

#### [C4] 线程模型混乱，没有统一并发策略

系统中同时存在：
- `asyncio` 事件循环（主线程）
- `threading.Thread` (daemon=True) — stdin线程、TTS后台消费线程、记忆写入线程、卡片创建线程
- `asyncio.run_coroutine_threadsafe()` — 跨线程调度
- `asyncio.to_thread()` — 异步到同步桥接
- `asyncio.create_task()` — 异步任务

没有一个明确的并发模型文档或架构约束。开发者需要猜测"这段代码在哪个线程执行"。

#### [C5] services目录3/4空壳 + deprecated代码未清理

```
services/llm/       → 空（仅__init__.py）
services/websocket/  → 空（仅__init__.py）
services/live2d/     → 空（仅__init__.py）

backend/deprecated/  → 含2个废弃文件+大量markdown
deprecated/          → 根级废弃目录
_deprecated_tests/   → 13个废弃测试脚本
```

这些目录是"意向性设计"的遗迹——创建时以为会放代码，后来代码放到了别处（core/、api/），但空目录从未删除。

### 2.3 一般问题 (MODERATE)

#### [M1] `main.py` 职责混乱

入口文件应该只做"组装+启动"，但 `main.py` 包含了：
- 工具注册（第50-58行）
- Action绑定（第63-66行）
- 调试打印（第74-77行）
- 终端输入线程（第93-144行，含特殊命令处理）
- 信号处理（第161-173行）
- 优雅关闭（第180-203行，含任务cancel+os._exit）

#### [M2] 流式断句逻辑重复

流式断句逻辑在 `actions.py:323-346` 和 `tts_manager.py:120-154` 各实现了一次，逻辑相似但不完全相同。

#### [M3] 硬编码遍布各处

```python
# actions.py
result = registry.execute_tool(tool_name, **all_params)
return str(result)[:500]  # 硬编码截断

# actions.py
async for token in llm_speaker.chat_stream_async(messages, temperature=0.7):  # 硬编码temperature

# memory_core.py
MIN_IMPORTANCE = 0.4  # 在roadmap中，尚未实现
```

#### [M4] `agent_brain.py` 的20路if/elif未删除

虽然查询子LLM已经走插件系统，`agent_brain.py` 的 `call_tool()` 中的20路if/elif链仍然存在，既是死代码又是混淆源。

#### [M5] 情绪-表情映射前后端重复定义

```
后端 emotion_engine.py: EMOTION_EXPRESSION_MAP
前端 AiWebSocket.ts: EMOTION_EXPRESSION_MAP  (完全相同的映射!)
```

---

## 第三步：问题根源与主流设计对比反思

### 3.1 为什么这些问题有害 — 具体阻碍场景推演

**场景A：增加"多模型支持"（如切换到Claude模型）**

当前代码中：
- `actions.py` 硬编码了DeepSeek的API调用格式
- `main.py` 创建了名为 `llm_deepseek` 的变量
- `YumeDriver` 的属性叫 `llm_thinker` 和 `llm_speaker`，但实际都是DeepSeek
- 如果换模型：(1)改main.py的创建参数 (2)改actions.py的调用 (3)改YumeDriver的创建 (4)改MemoryCore的fallback创建 — **至少4处修改，容易遗漏**

好的设计（依赖注入 + Provider模式）：
```python
# 只需在一处切换
llm = LLMFactory.create(provider="claude", config=claude_config)
agent = Agent(llm=llm)  # 所有内部组件通过注入获得
```

**场景B：增加"多模态输入"（图片+语音+文字）**

当前 `action_think(context)` 假设输入是 `context.get("user_input", "")` 字符串。要加图片理解，需要：
- 修改 `action_think` 的context解析
- 修改 MemoryCore 的记忆意图检测（当前只处理文本）
- 修改提示词构建（当前只注入文本）
- 修改 TTSManager（需要决定图片理解的结果是否要播报）

好的设计（Pipelines模式）：
```python
class ThinkPipeline:
    def __init__(self, stages: List[PipelineStage]):
        self.stages = stages
    
    async def execute(self, input: Message) -> Message:
        for stage in self.stages:
            input = await stage.process(input)
        return input
```

**场景C：增加"多角色/多Agent对话"**

当前 `_global_state_machine` 是单例，`ws_instance` 是模块级变量。要支持两个Agent同时运行：
- 所有全局变量必须改为实例变量
- WebSocket路由需要Agent标识
- 记忆系统需要隔离

好的设计（实例化架构）：
```python
class AgentRuntime:
    def __init__(self, agent_id: str, config: AgentConfig):
        self.state_machine = StateMachine()
        self.memory = MemoryCore(config.memory)
        self.llm = LLMAPI(config.llm)
        # 每个runtime完全隔离
```

### 3.2 深度反思：当前设计真的可行吗？

**直说：当前设计作为原型(Demo)可行，作为产品不可行。**

- `action_think` 的200行God Function在原型阶段"能跑"，但每加一个功能就多20行，一年后它会变成400行然后600行
- 全局单例在单用户场景"能跑"，但即使是单用户，测试也无法写
- 配置双写"能跑"，但每次加配置都是3倍的维护成本
- 线程混用"能跑"，直到某天出现一个race condition花3天调试

**当前设计不是"错误"的设计——它是"没有设计"。** 它是有机生长的结果：每需要一个功能，就在最近的函数里加一段代码。这不是架构问题，这是**架构缺失**问题。

### 3.3 与主流范式对比

| 维度 | 当前状态 | 整洁架构 | 六边形架构 | 模块化单体 |
|------|---------|---------|-----------|-----------|
| 依赖方向 | 无规则，随意import | 外层依赖内层 | 端口+适配器 | 模块间通过公开API通信 |
| 业务逻辑 | 散落在actions/agents/memory中 | 集中在UseCase层 | 在Domain中 | 在模块内部 |
| 基础设施 | 直接new LLMAPI() | 通过接口注入 | 通过端口注入 | 通过模块间契约 |
| 测试友好 | 无法单元测试 | 可mock外层 | 可mock适配器 | 模块独立测试 |
| 扩展方式 | 在现有函数中加代码 | 新增UseCase | 新增适配器 | 新增模块 |

**推荐方向：模块化单体 (Modular Monolith)**

对于当前项目规模（一个Agent、一个用户、一个模型），微服务或完整的整洁架构是过度工程。模块化单体是最佳选择：
- 按领域边界拆分为独立模块（对话引擎、记忆系统、TTS服务、Live2D驱动）
- 模块间通过明确的接口（Python Protocol/ABC）通信
- 每个模块内部可以有自己的小架构
- 未来如果需要拆分微服务，模块边界就是服务边界

### 3.4 这里这样真的好吗？更好的设计应该是什么？

**当前：**
```
action_think() —— 一个函数做所有事
  ├── 记忆检索
  ├── 情绪推断
  ├── 提示词构建
  ├── LLM调用
  ├── 流式断句
  ├── TTS入队
  ├── 缓冲检测
  └── 异步写入
```

**应该是：**
```
ThinkPipeline (编排器，~30行)
  ├── MemoryRetriever   → 返回 MemoryContext
  ├── EmotionAnalyzer   → 返回 EmotionState
  ├── PromptBuilder     → 返回 Prompt
  ├── LLMStreamer       → 返回 AsyncIterator[Token]
  ├── SentenceSplitter  → 切分为句子
  ├── TTSDispatcher     → 入队TTS
  └── RecallDetector    → 决定是否需要深挖
```

每个组件独立、可测试、可替换。Pipeline只是一个编排器，不包含任何业务逻辑。

---

## 第四步：融合记忆进化路线图与后记指导

### 4.1 推测的演进遗留债务

根据 `memory_evolution_roadmap.md` 的内容和代码现状，可以推测以下演进历史：

| 演进阶段 | 当时决策 | 遗留债务 |
|---------|---------|---------|
| **V1-V2：原型验证** | 快速堆叠功能，无架构设计 | God Function `action_think`、God Class `MemoryCore` |
| **V3：引入FAISS** | 引入向量搜索，过度工程 | 后来被移除，留下废弃代码和目录 |
| **V3：双LLM架构** | 引入查询子LLM | 但创建方式混乱（5次LLMAPI实例化） |
| **V4：简化** | 移除FAISS、移除Qwen | 但千问配置仍在config.py中（"已废弃"注释） |
| **V5：卡片记忆** | 引入CardStore图结构 | 但MemoryCore仍是979行上帝类，新旧逻辑共存 |
| **多次"修补"** | 每次修bug在最近处加代码 | 流式断句逻辑重复2次、参数双重定义 |

**核心判断**：
- "历史包袱"：deprecated目录、Qwen配置残留、agent_brain的if/elif链
- "原生设计缺陷"：全局单例架构、God Function action_think、配置双写
- "仓促妥协"：情绪系统未接入主流程、skill系统未集成、4.5个空服务目录

### 4.2 演进路线图 vs 现实差距

`memory_evolution_roadmap.md` 假设了一个"干净架构"：
```
MemoryCore (外观层, ~500行)
  ├── CardStore (存储引擎, ~553行)
  └── EmotionEngine (独立)
```

**现实是**：
- MemoryCore 是 979 行（roadmap说500行）
- CardStore 确实是干净的部分（roadmap描述准确）
- 但 MemoryCore 远超"外观层"——它做了日记、文件I/O、上下文组装、静态工具方法、意图检测
- roadmap中的 Phase 1-6 所有改造都假设 MemoryCore 只是一个Facade，**而实际上它是整个记忆系统本身**

这意味着：**roadmap中Phase 1的修改（在card_store.py改_auto_link）可以直接进行，但Phase 2+的所有修改（审核API、语义压缩、知识地形）都会因为在God Class上叠加功能而加剧问题。**

### 4.3 后记指导：重构行动纲领

#### 第一阶段：生命维持手术（1-2周，不中断业务）

**目标**：消除致命问题，建立安全重构基线

| 优先级 | 行动 | 影响范围 | 预计工作量 |
|--------|------|---------|-----------|
| **P0** | 拆分 `action_think` 为 Pipeline 模式（5个独立Stage） | actions.py | 3天 |
| **P0** | 引入 LLMAPI 单例工厂，消除5次实例化 | main.py, actions.py, agent_driver.py, memory_core.py | 1天 |
| **P0** | 消除全局单例：StateMachine + ToolRegistry 改为实例注入 | state_machine.py, registry.py, main.py | 2天 |
| **P0** | 删除3个deprecated目录 + agent_brain的call_tool链 | 多处 | 1天 |

**第一阶段核心抽象设计**：

```python
# ── Pipeline: action_think 的替代品 ──

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, List, Optional

@dataclass
class ThinkContext:
    """Pipeline 中流转的上下文对象"""
    user_input: str
    memory_context: dict = field(default_factory=dict)
    emotion_state: str = "neutral"
    system_prompt: str = ""
    response_tokens: List[str] = field(default_factory=list)
    full_response: str = ""
    recall_depth: int = 0
    max_recall_depth: int = 2

class PipelineStage(ABC):
    """Pipeline 阶段抽象"""
    @abstractmethod
    async def process(self, ctx: ThinkContext) -> ThinkContext:
        ...

class MemoryRetrieveStage(PipelineStage):
    """Stage 1: 记忆检索（CardStore BFS + 情绪推断）"""
    def __init__(self, memory_core: MemoryCoreProtocol):
        self._memory = memory_core
    
    async def process(self, ctx: ThinkContext) -> ThinkContext:
        ctx.memory_context = self._memory.build_structured_sections(ctx.user_input)
        return ctx

class PromptBuildStage(PipelineStage):
    """Stage 2: 提示词构建"""
    def __init__(self, template_loader: PromptTemplateLoader):
        self._templates = template_loader
    
    async def process(self, ctx: ThinkContext) -> ThinkContext:
        ctx.system_prompt = self._templates.render("yume_system", ctx.memory_context)
        return ctx

class LLMStreamStage(PipelineStage):
    """Stage 3: 流式LLM + 逐句分发"""
    def __init__(self, llm: LLMAPIProtocol, dispatcher: SentenceDispatcher):
        self._llm = llm
        self._dispatcher = dispatcher
    
    async def process(self, ctx: ThinkContext) -> ThinkContext:
        async for token in self._llm.chat_stream_async(...):
            ctx.response_tokens.append(token)
            ctx.full_response += token
            await self._dispatcher.on_token(token, ctx.emotion_state)
        return ctx

class RecallDetectStage(PipelineStage):
    """Stage 4: 缓冲语检测 + 递归深挖"""
    def __init__(self, query_llm_factory: QueryLLMFactory):
        self._query_factory = query_llm_factory
    
    async def process(self, ctx: ThinkContext) -> ThinkContext:
        if self._is_recall_signal(ctx.full_response) and ctx.recall_depth < ctx.max_recall_depth:
            result = await self._query_factory.run(ctx.user_input, ctx.full_response)
            ctx.memory_context["deep_recall"] = result
            ctx.recall_depth += 1
            # 递归重新走Pipeline
            return await pipeline.execute(ctx)
        return ctx

class ThinkPipeline:
    """编排器：组合所有Stage"""
    def __init__(self, stages: List[PipelineStage]):
        self._stages = stages
    
    async def execute(self, ctx: ThinkContext) -> ThinkContext:
        for stage in self._stages:
            ctx = await stage.process(ctx)
        return ctx
```

```python
# ── LLMAPI 工厂：单一实例管理 ──

from typing import Protocol

class LLMAPIProtocol(Protocol):
    """LLM API 抽象接口"""
    async def chat_stream_async(self, messages, temperature) -> AsyncIterator[str]: ...
    def ask(self, prompt: str) -> str: ...
    async def ask_async(self, prompt: str) -> str: ...

class LLMFactory:
    """LLM 实例工厂（确保每个配置只创建一次）"""
    _instances: dict = {}
    _lock = threading.Lock()
    
    @classmethod
    def get(cls, api_key: str, base_url: str, model: str) -> LLMAPIProtocol:
        key = f"{base_url}:{model}"
        with cls._lock:
            if key not in cls._instances:
                cls._instances[key] = LLMAPI(api_key, base_url, model)
        return cls._instances[key]
```

```python
# ── Config: 单一声源 ──

class AppConfig:
    """应用配置（单一数据源，不再有模块级常量和CONFIG字典）"""
    
    def __init__(self, yaml_config: dict, env_overrides: dict):
        self._raw = yaml_config
        self._apply_env(env_overrides)
    
    @property
    def deepseek_api_key(self) -> str:
        return self._raw["ai"]["deepseek"]["api_key"]
    
    # 不再需要30+个模块级常量
    # 调用方: config.deepseek_api_key 而不是 from config import DEEPSEEK_API_KEY
```

#### 第二阶段：架构归位（2-3周）

**目标**：建立正确的模块边界和依赖方向

| 优先级 | 行动 | 影响范围 |
|--------|------|---------|
| **P1** | MemoryCore 拆分为 5 个独立组件 | memory_core.py → memory/目录下5个文件 |
| **P1** | 配置系统重构：消除双写，单一Config对象 | config.py, default.yaml |
| **P1** | 情绪系统接入主对话流 | emotion_engine.py, actions.py |
| **P1** | 自驱动引擎接入状态机（新增SPONTANEOUS_TRIGGER事件） | spontaneous/engine.py, state_machine |
| **P1** | 清理services空目录，决定每个服务的位置 | services/ |

**MemoryCore拆分方案**：

```python
# 当前: memory_core.py (979行, 1个类)
# 目标: memory/ (6个文件, 每个<200行)

memory/
├── __init__.py
├── short_term.py        # ShortTermBuffer: RAM缓冲管理 (~80行)
├── card_manager.py      # CardManager: 卡片创建+审核 (~120行)
├── diary_writer.py      # DiaryWriter: 日记草稿+归档 (~100行)
├── context_builder.py   # ContextBuilder: 上下文组装 (~120行)
├── intent_detector.py   # IntentDetector: 记忆意图检测 (~80行)
└── memory_facade.py     # MemoryFacade: 统一门面 (~60行)
    # 只做委托，不包含逻辑:
    #   build_context() → self._context_builder.build()
    #   add_short_term() → self._short_term.add()
    #   create_card() → self._card_manager.create()
```

#### 第三阶段：长期演进（与memory_evolution_roadmap.md同步）

**目标**：在健康架构上实施roadmap中的Phase 1-6

**关键约束**：
- roadmap的Phase 1（图退化修复、质量门、读写锁）必须在MemoryCore拆分后进行，确保改在正确的组件上
- Phase 2（半自动化转型）的审核API应该作为CardManager的新方法，而不是在Facade上叠加
- Phase 3（语义压缩）的`_smart_compress`应该作为CardStore的内部实现，不暴露给上层

#### 新原则清单

1. **依赖方向规则**：`main(组装) → Pipeline(编排) → Stage(业务) → Service(基础设施)`。禁止反向依赖。
2. **模块边界规则**：每个模块只暴露一个公开类/函数，其余为模块私有（`_`前缀）。
3. **配置单一声源**：所有配置从 `AppConfig` 对象获取，不再有模块级常量。
4. **实例化规则**：`LLMAPI` 只能通过 `LLMFactory` 创建，禁止直接 `LLMAPI(...)`。
5. **状态机规则**：所有发言（用户回复+自驱动）必须经过状态机，禁止绕过。
6. **测试策略**：Pipeline的每个Stage必须能独立测试（通过注入Mock依赖）。
7. **前端规则**：Live2D参数名只定义一次，后端通过WebSocket发送的参数名是权威来源。
8. **废弃策略**：废弃代码必须在同一PR中删除，不允许保留"以防万一"。

#### 过渡策略：如何不中断业务逐步替换

1. **Strangler Fig Pattern（绞杀榕模式）**：
   - 新建 `think_pipeline/` 目录，实现Pipeline及所有Stage
   - 在 `actions.py` 中保留旧 `action_think`，同时新增 `action_think_v2`
   - 通过配置开关 `USE_PIPELINE_THINK=true/false` 控制使用哪个版本
   - 验证通过后，删除旧版本

2. **Facade保留兼容**：
   - MemoryCore 拆分后，保留 `MemoryCore` 类作为 Facade
   - Facade 内部委托给新组件，外部API不变
   - 逐步将调用方迁移到直接使用新组件

3. **双写验证**：
   - Config重构时，新的 `AppConfig` 和旧的模块级常量同时存在
   - 启动时验证两者一致性，不一致时告警
   - 验证期（2周）后删除旧常量

### 4.4 最终总结

**如果照此重构，一年后的系统形态**：

> 一年后，`main.py` 从223行缩减为40行纯组装代码。对话流程是一个5-stage Pipeline，每个Stage不到80行、有独立测试。记忆系统是6个职责清晰的组件，CardStore已支撑100K张卡片，压缩从截断升级为语义聚合。LLM实例通过工厂统一管理，连接池可观测。配置是单一AppConfig对象，新增配置只需在YAML加一行。前端AiWebSocket的`_onMessage`从95行拆分为5个独立handler。情绪系统与对话流打通，yume真的会高兴和生气。自驱动发言和用户回复走同一条状态机路径。任何新人看一遍Pipeline的Stage列表就能理解整个对话流程。

**如果不改，一年后的不可维护灾难**：

> `action_think` 变成400行，因为加了图片理解、工具链、多模态。`MemoryCore` 变成1500行，因为加了审核API、语义压缩、知识地形。全局单例导致一个bug花3天调试（两个测试互相污染状态）。配置系统有50+个模块级常量，没人敢删旧配置。services目录仍有空壳，没人记得哪个是真正的服务位置。3个deprecated目录仍在，加上新增的"临时"代码。每次加功能都在已有函数中追加，没有人知道完整的调用链。最终，唯一的选择是重写。

---

> **审计结论：项目有好的基因（CardStore的干净设计、Pipeline的思想萌芽、提示词文件化），但被仓促堆叠和缺乏架构纪律所掩盖。当前最紧迫的不是加功能，而是建立架构约束——让代码只能以健康的方式增长。建议立即启动第一阶段重构，在两周内消除致命问题，建立安全基线。**
