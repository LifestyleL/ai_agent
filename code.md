# 项目背景
你是一个资深的全栈开发工程师，现在需要根据一份详细的架构方案，从零搭建一个“虚拟智能体系统”。
该系统包含：Live2D角色动画、双模型AI对话(Qwen+DeepSeek)、实时语音合成(TTS)、语音识别(ASR)。

# 核心技术栈（硬性要求，不可更改）
- 前端：TypeScript + Vite + Cubism SDK for Web
- 后端：Python + FastAPI (异步)
- 通信协议：WebSocket + JSON-RPC 2.0 (多通道分离：animation, audio, control)
- AI模型：Qwen (人格化) + DeepSeek (工具调用)
- 数据库：PostgreSQL + Redis
- 向量库：Milvus 或 Chroma
- 部署：Docker + docker-compose

# 第一阶段执行指令：项目脚手架与基础通信
请严格按照以下步骤执行，每完成一步再进行下一步：

## Step 1: 初始化工程目录
严格按照以下结构创建目录树（仅创建空目录和.gitkeep，暂不写业务代码）：
virtual_agent_project/
├── frontend/
│ ├── src/ (含 components/, core/, services/, utils/)
│ ├── public/
│ └── tests/
├── backend/
│ ├── core/
│ ├── services/
│ ├── plugins/
│ ├── api/
│ └── utils/
├── config/ (存放 default.yaml, development.yaml, production.yaml)
├── deploy/ (存放 docker/, scripts/)
├── docs/
└── tests/ (含 unit/, integration/, e2e/)

## Step 2: 初始化后端环境与基础配置
1. 在 backend/ 下初始化 Python 环境，生成 requirements.txt（包含 fastapi, websockets, pyyaml 等）。
2. 在 config/default.yaml 中编写基础配置结构，需包含：server, websocket, ai_models(qwen/deepseek), tts, asr, database, redis 等分区。
3. 编写一个 config_loader.py，实现多环境 YAML 配置的加载与合并逻辑。

## Step 3: 搭建后端 WebSocket 骨架与 JSON-RPC 规范
在 backend/api/ 下建立 WebSocket 服务，要求：
1. 实现基础的 WebSocket 连接管理。
2. 实现严格的 JSON-RPC 2.0 解析器，能识别 `jsonrpc`, `method`, `params`, `id`。
3. 实现多通道分发机制：根据 params.channel ('animation', 'audio', 'control') 将消息路由到不同的处理器。
4. 实现统一的错误处理响应格式（遵循 JSON-RPC 2.0 的 code, message, data 结构）。

## Step 4: 定义 Live2D 参数常量映射
在后端创建一个专门的常量文件（如 backend/core/live2d_constants.py），定义标准参数的枚举或字典，必须包含以下规范：
- ParamAngleX: [-30, 30] (头部左右)
- ParamAngleY: [-30, 30] (头部上下)
- ParamAngleZ: [-30, 30] (头部倾斜)
- ParamEyeLOpen / ParamEyeROpen: [0, 1] (眼睛开合)
- ParamMouthOpenY: [0, 1] (嘴巴开合)
- ParamBodyAngleX: [-10, 10] (身体左右)

---
# 注意事项
1. 代码必须有完整的 Type Hinting (Python)。
2. 添加必要的中文注释，解释架构设计的意图（如：为什么要做通道分离）。
3. 完成上述 4 个 Step 后，向我汇报，等待我下达“第二阶段：AI代理与记忆模块设计”的指令。
