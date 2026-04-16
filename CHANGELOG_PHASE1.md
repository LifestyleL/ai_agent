# 后端重构第一阶段（Phase 1）变更日志

## 概述
本项目按照《架构方案》第七章"第一阶段：稳定化"的要求，完成了核心技术债务清理和架构标准化。所有变更遵循"建立骨架，不伤筋骨"原则，确保系统在每一步都保持可运行状态。

## 变更分类

### 【新增】文件
| 文件路径 | 功能描述 |
|----------|----------|
| `my-react-app/my_agent/live2d/live2d_constants.py` | Live2D 参数标准化定义，包含参数范围、旧参数映射、参数钳制方法 |
| `my-react-app/my_agent/netwebsocket/message_router.py` | JSON-RPC 2.0 消息路由器，支持 `animation`、`audio`、`control` 三个通道的消息分发 |
| `my-react-app/my_agent/netwebsocket/json_rpc_builder.py` | JSON-RPC 2.0 响应构造器，提供标准化的成功/错误响应格式 |
| `my-react-app/my_agent/netwebsocket/error_code.py` | JSON-RPC 错误码常量定义，包含标准错误码和自定义错误码 |
| `_deprecated_tests/test_step2_params.py` | Step 2 阻断验证测试，验证参数标准化和范围限制机制 |
| `_deprecated_tests/test_step3_websocket.py` | Step 3 阻断验证测试，验证消息路由器和兜底逻辑 |
| `_deprecated_tests/test_step4_export.py` | Step 4 阻断验证测试，验证 JSON-RPC 出口包装层 |

### 【重构】文件
| 文件路径 | 重构内容 |
|----------|----------|
| `my-react-app/my_agent/live2d/animator.py` | 1. 移除暴力测试块（第215-220行）<br>2. 导入 Live2DConstants<br>3. 将 `PartArmA/B` 改为 `ParamArmLA/LB/RA/RB`<br>4. 在 `compute_params` 末尾添加 `params = Live2DConstants.clamp_params(params)` |
| `my-react-app/my_agent/live2d/live2d_manager.py` | 1. 移除暴力测试块（第101-106行）<br>2. 导入 Live2DConstants<br>3. 完全重写 `send_custom_params` 方法，使用 `normalize_params` 和标准参数名<br>4. 添加参数范围限制 |
| `my-react-app/my_agent/live2d/clean_face_driver.py` | 1. 添加 Live2DConstants 导入<br>2. 在 `compute` 方法末尾添加 `params = Live2DConstants.clamp_params(params)` |
| `my-react-app/my_agent/netwebsocket/ws_server.py` | 1. Step 3：集成消息路由器，添加降级逻辑<br>2. Step 4：添加 `_infer_channel_from_data` 方法<br>3. 修改 `_send` 方法，集成 JSON-RPC 包装开关<br>4. 添加错误响应包装 |
| `my-react-app/my_agent/config.py` | 添加 JSON-RPC 响应包装开关：<br>`ENABLE_JSONRPC_RESPONSE = os.environ.get("ENABLE_JSONRPC_RESPONSE", "false").strip().lower() in ("true", "1", "yes", "on")` |

### 【移除】文件
| 文件路径 | 移除原因 |
|----------|----------|
| `my-react-app/my_agent/live2d/live2d_behavior.py` | 实验性代码，已过时，包含暴力测试和参数名混淆逻辑 |

### 【修复】问题
1. **参数命名混乱**：统一了 Live2D 参数命名，废弃 `headX`、`mouth`、`PartArmA` 等别名，全面使用标准名（`ParamAngleX`、`ParamMouthOpenY`、`ParamArmLA` 等）
2. **参数范围失控**：建立了全链路参数钳制机制，确保所有参数值在合法范围内（头部角度 ±30°，身体角度 ±10°，嘴巴/眼睛/手臂 0-1）
3. **WebSocket 消息处理耦合**：解耦了消息处理逻辑，引入通道化路由架构
4. **错误处理简陋**：建立了 JSON-RPC 2.0 标准错误码体系
5. **编码问题**：修复了测试脚本中的 Unicode 编码错误（✅ 替换为 [PASS]，❌ 替换为 [FAIL]）

## 核心架构变更

### 1. Live2D 参数标准化
- **标准参数名**：`ParamAngleX`, `ParamAngleY`, `ParamAngleZ`, `ParamBodyAngleX`, `ParamBodyAngleY`, `ParamBodyAngleZ`, `ParamMouthOpenY`, `ParamEyeLOpen`, `ParamEyeROpen`, `ParamHairAhoge`, `ParamArmLA`, `ParamArmLB`, `ParamArmRA`, `ParamArmRB`
- **参数范围**：严格定义了每个参数的合法值范围
- **向后兼容**：通过 `OLD_PARAM_MAPPING` 支持旧参数名自动转换

### 2. WebSocket 消息路由架构
```
接收消息 → 路由器解析 → 通道分发 → 处理器执行
     ↓ 失败/异常
   降级到旧逻辑（安全网）
```
- **三个通道**：`animation`（Live2D参数）、`audio`（TTS音频）、`control`（控制指令）
- **兜底机制**：路由器失败时自动回退到原有的四种消息处理分支

### 3. JSON-RPC 2.0 出口包装层
- **安全开关**：`ENABLE_JSONRPC_RESPONSE`（默认 `false`，保持前端兼容性）
- **标准格式**：当开关开启时，所有出口数据包装为 JSON-RPC 2.0 格式
- **错误规范**：标准错误码 + 结构化错误消息

## 配置说明

### JSON-RPC 响应包装开关
```python
# config.py 中新增
ENABLE_JSONRPC_RESPONSE = os.environ.get("ENABLE_JSONRPC_RESPONSE", "false").strip().lower() in ("true", "1", "yes", "on")
```

**启用方式**（三选一）：
1. **环境变量**：`export ENABLE_JSONRPC_RESPONSE=true`
2. **.env 文件**：添加 `ENABLE_JSONRPC_RESPONSE=true`
3. **直接修改**：`config.py` 中设置 `ENABLE_JSONRPC_RESPONSE = True`

**重要提醒**：
- 默认状态：**禁用**，系统行为与重构前完全一致，确保前端兼容性
- 启用条件：仅在前端完成 JSON-RPC 2.0 解析支持后开启

## 测试验证
所有变更均通过阻断验证测试：
- ✅ `test_step2_params.py`：参数标准化和范围限制
- ✅ `test_step3_websocket.py`：消息路由和兜底逻辑
- ✅ `test_step4_export.py`：JSON-RPC 包装和错误规范

## Git 提交建议
```
feat: 完成第一阶段架构重构

新增：
- live2d_constants.py: Live2D 参数标准化定义
- netwebsocket/message_router.py: JSON-RPC 2.0 消息路由器
- netwebsocket/json_rpc_builder.py: JSON-RPC 响应构造器
- netwebsocket/error_code.py: 错误码常量定义
- 测试脚本：test_step{2,3,4}_*.py

重构：
- animator.py: 移除实验代码，统一参数命名，添加范围限制
- live2d_manager.py: 重写参数处理方法，使用标准参数名
- clean_face_driver.py: 添加参数钳制
- ws_server.py: 集成消息路由，添加 JSON-RPC 包装开关
- config.py: 添加 ENABLE_JSONRPC_RESPONSE 开关

移除：
- live2d_behavior.py: 实验性代码清理

修复：
- 参数命名混乱问题
- 参数范围失控问题
- WebSocket 消息处理耦合
- 错误处理简陋问题
- 测试脚本编码问题

架构变更：
1. Live2D 参数标准化（100% 标准名，全链路钳制）
2. WebSocket 消息路由架构（三通道 + 兜底机制）
3. JSON-RPC 2.0 出口包装层（安全开关控制）

注意：系统保持完全向后兼容，ENABLE_JSONRPC_RESPONSE 默认关闭。
```

---
*生成时间：2026-04-16*
*对应架构方案：第七章"第一阶段：稳定化"*