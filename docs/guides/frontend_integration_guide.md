# 前端对接指南（V1.0）

## 📋 概述

本文档为前端开发者提供与重构后后端系统的对接指导。后端已完成第一阶段架构重构，建立了完整的 JSON-RPC 2.0 多通道通信骨架，但**当前处于完全兼容模式**，前端不需要立即修改任何代码。

## 🟢 现状说明：兼容模式（当前状态）

### 关键信息
- **后端状态**：已完成参数标准化和消息路由重构
- **前端影响**：**零影响**，系统行为与重构前完全一致
- **通信协议**：保持原有 WebSocket 消息格式
- **参数命名**：后端发出的 Live2D 参数已全部使用标准名

### 为什么不需要修改？
后端设计了**安全开关机制**，默认关闭 JSON-RPC 包装功能：
```python
# config.py
ENABLE_JSONRPC_RESPONSE = False  # 默认值，保持兼容性
```

在此模式下，后端：
1. 接收前端消息时，同时支持新旧格式（自动转换）
2. 发送给前端的消息，保持原有格式
3. Live2D 参数使用标准名，但格式不变

## 🔧 参数规范对接（立即可用）

### Live2D 参数标准化
后端现在发出的 Live2D 参数已经是 100% 标准命名，前端可以**立即清理**掉自己代码中可能存在的别名兼容代码。

| 标准参数名 | 旧别名（可删除） | 取值范围 | 说明 |
|-----------|----------------|----------|------|
| `ParamAngleX` | `headX`, `angleX` | -30 ~ 30 | 头部左右转动 |
| `ParamAngleY` | `headY`, `angleY` | -30 ~ 30 | 头部上下点头 |
| `ParamAngleZ` | `headZ`, `angleZ` | -30 ~ 30 | 头部左右倾斜 |
| `ParamBodyAngleX` | `bodyX` | -10 ~ 10 | 身体左右转动 |
| `ParamBodyAngleY` | `bodyY` | -10 ~ 10 | 身体前后倾斜 |
| `ParamBodyAngleZ` | `bodyZ` | -10 ~ 10 | 身体左右倾斜 |
| `ParamMouthOpenY` | `mouth` | 0 ~ 1 | 嘴巴开合 |
| `ParamEyeLOpen` | `eyeLeft` | 0 ~ 1 | 左眼开合 |
| `ParamEyeROpen` | `eyeRight` | 0 ~ 1 | 右眼开合 |
| `ParamHairAhoge` | `hair` | -3 ~ 3 | 头发飘动 |
| `ParamArmLA` | `PartArmA` (左) | 0 ~ 1 | 左臂A部分显示度 |
| `ParamArmLB` | - | 0 ~ 1 | 左臂B部分显示度 |
| `ParamArmRA` | `PartArmB` (右) | 0 ~ 1 | 右臂A部分显示度 |
| `ParamArmRB` | - | 0 ~ 1 | 右臂B部分显示度 |

### 前端清理建议
```typescript
// 可以删除的兼容代码示例
function handleLive2DParams(params: any) {
  // 旧的兼容逻辑（可删除）
  const angleX = params.headX ?? params.angleX ?? params.ParamAngleX ?? 0;
  const mouth = params.mouth ?? params.ParamMouthOpenY ?? 0;
  
  // 新的标准逻辑（推荐）
  const angleX = params.ParamAngleX ?? 0;
  const mouth = params.ParamMouthOpenY ?? 0;
}
```

## 🚀 协议升级预告（未来准备）

### 何时升级？
当后端管理员开启 `ENABLE_JSONRPC_RESPONSE=true` 时，前端将开始接收 JSON-RPC 2.0 格式的消息。升级前会提前通知。

### 新协议格式示例

#### 1. 动画更新（Live2D参数）
```json
{
  "jsonrpc": "2.0",
  "method": "animation.update",
  "params": {
    "channel": "animation",
    "version": "1.0",
    "timestamp": 1776320174965,
    "data": {
      "ParamAngleX": 15,
      "ParamAngleY": -10,
      "ParamMouthOpenY": 0.5
    }
  }
}
```

#### 2. 音频流（TTS音频）
```json
{
  "jsonrpc": "2.0",
  "method": "audio.stream",
  "params": {
    "channel": "audio",
    "version": "1.0",
    "timestamp": 1776320175101,
    "data": {
      "type": "TTS_AUDIO",
      "audio_base64": "UklGRh4AAABXQVZFZm...",
      "visemes": [
        {"t": 0, "v": 0.1},
        {"t": 100, "v": 0.8}
      ]
    }
  }
}
```

#### 3. 控制指令（系统控制）
```json
{
  "jsonrpc": "2.0",
  "method": "control.command",
  "params": {
    "channel": "control",
    "version": "1.0",
    "timestamp": 1776320175200,
    "data": {
      "command": "reset",
      "action": "restart",
      "reason": "system_update"
    }
  }
}
```

### TypeScript 类型定义建议
```typescript
// JSON-RPC 2.0 基础接口
interface JsonRpcBase {
  jsonrpc: "2.0";
  id?: string | number;
}

// 成功响应
interface JsonRpcSuccess<T = any> extends JsonRpcBase {
  method: string;
  params: {
    channel: "animation" | "audio" | "control";
    version: string;
    timestamp: number;
    data: T;
  };
}

// 错误响应
interface JsonRpcError extends JsonRpcBase {
  error: {
    code: number;
    message: string;
    data?: any;
  };
}

// 类型守卫函数
function isJsonRpcSuccess(msg: any): msg is JsonRpcSuccess {
  return msg?.jsonrpc === "2.0" && msg?.method && msg?.params;
}

function isJsonRpcError(msg: any): msg is JsonRpcError {
  return msg?.jsonrpc === "2.0" && msg?.error;
}

// 通道特定数据类型
interface AnimationData {
  ParamAngleX?: number;
  ParamAngleY?: number;
  ParamAngleZ?: number;
  ParamBodyAngleX?: number;
  ParamBodyAngleY?: number;
  ParamBodyAngleZ?: number;
  ParamMouthOpenY?: number;
  ParamEyeLOpen?: number;
  ParamEyeROpen?: number;
  ParamHairAhoge?: number;
  ParamArmLA?: number;
  ParamArmLB?: number;
  ParamArmRA?: number;
  ParamArmRB?: number;
}

interface AudioData {
  type: "TTS_AUDIO";
  audio_base64: string;
  visemes: Array<{ t: number; v: number }>;
}

interface ControlData {
  command: string;
  action?: string;
  reason?: string;
  [key: string]: any;
}

// 消息处理器示例
class WebSocketHandler {
  handleMessage(rawMessage: string) {
    const msg = JSON.parse(rawMessage);
    
    // 检查是否为 JSON-RPC 格式
    if (msg.jsonrpc === "2.0") {
      if (isJsonRpcSuccess(msg)) {
        this.handleJsonRpcSuccess(msg);
      } else if (isJsonRpcError(msg)) {
        this.handleJsonRpcError(msg);
      }
    } else {
      // 旧格式消息处理（兼容模式）
      this.handleLegacyMessage(msg);
    }
  }
  
  private handleJsonRpcSuccess(msg: JsonRpcSuccess) {
    const { channel, data, timestamp } = msg.params;
    
    switch (channel) {
      case "animation":
        this.updateLive2D(data as AnimationData);
        break;
      case "audio":
        this.playAudio(data as AudioData);
        break;
      case "control":
        this.executeCommand(data as ControlData);
        break;
    }
  }
  
  private handleJsonRpcError(msg: JsonRpcError) {
    console.error(`JSON-RPC 错误: ${msg.error.code} - ${msg.error.message}`);
    // 显示错误提示给用户
  }
}
```

## 🚨 错误处理对接

### 错误响应格式
当后端发生错误时（仅在 JSON-RPC 模式开启后），前端将收到标准错误响应：

```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": 1001,
    "message": "动画参数超出范围",
    "data": {
      "param": "ParamAngleX",
      "value": 999,
      "range": "[-30, 30]"
    }
  }
}
```

### 常见错误码
| 错误码 | 类型 | 说明 | 前端处理建议 |
|--------|------|------|------------|
| `-32700` | JSON 解析错误 | 请求 JSON 格式无效 | 检查发送的数据格式 |
| `-32600` | 无效请求 | 缺少必需字段 | 检查请求结构 |
| `1001` | 动画参数超出范围 | Live2D 参数值越界 | 调整参数值 |
| `2001` | TTS 初始化失败 | 语音合成服务不可用 | 提示用户稍后重试 |
| `3001` | AI 模型不可用 | AI 服务暂时不可用 | 显示"思考中，请稍候" |
| `4001` | 控制指令无效 | 未知的控制命令 | 检查指令名称 |

### 错误处理示例
```typescript
// 错误码映射表
const ERROR_MESSAGES: Record<number, string> = {
  [-32700]: "JSON 格式错误，请检查数据",
  [-32600]: "请求格式无效，缺少必需字段",
  [1001]: "动画参数值超出范围",
  [2001]: "语音合成服务暂时不可用",
  [3001]: "AI 服务繁忙，请稍后重试",
  [4001]: "未知的控制指令",
};

function handleError(error: JsonRpcError) {
  const { code, message, data } = error.error;
  
  // 获取用户友好的错误消息
  const userMessage = ERROR_MESSAGES[code] || message;
  
  // 显示错误提示
  showNotification({
    type: "error",
    title: "操作失败",
    message: userMessage,
    details: data ? JSON.stringify(data) : undefined,
  });
  
  // 特定错误码的特殊处理
  switch (code) {
    case 2001: // TTS 失败
      disableVoiceFeature();
      break;
    case 3001: // AI 不可用
      setAIBusy(true);
      break;
  }
}
```

## 📋 升级检查清单

### 第一阶段（现在可做）
- [ ] 清理前端代码中的 Live2D 参数别名兼容逻辑
- [ ] 确认所有 Live2D 参数使用标准名：`ParamAngleX`、`ParamMouthOpenY` 等
- [ ] 测试系统在兼容模式下的正常运行

### 第二阶段（协议升级前准备）
- [ ] 实现 JSON-RPC 2.0 基础解析器
- [ ] 添加 TypeScript 类型定义
- [ ] 实现三通道消息分发逻辑
- [ ] 实现标准错误处理
- [ ] 与后端协调升级时间窗口

### 第三阶段（协议升级后）
- [ ] 启用 JSON-RPC 解析器
- [ ] 移除旧格式兼容代码（可选）
- [ ] 全面测试新协议下的所有功能

## 📞 技术支持

### 问题反馈
如果在对接过程中遇到问题，请提供以下信息：
1. 后端日志片段
2. 前端收到的原始消息
3. 浏览器控制台错误
4. 复现步骤

### 协调升级
协议升级需要前后端协调：
1. 前端完成 JSON-RPC 支持开发
2. 双方约定升级时间窗口
3. 后端开启 `ENABLE_JSONRPC_RESPONSE=true`
4. 双方同步监控系统状态

---
*文档版本：V1.0*
*最后更新：2026-04-16*
*对应后端版本：第一阶段重构完成*