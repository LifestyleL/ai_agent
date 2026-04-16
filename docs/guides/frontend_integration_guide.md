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

## 🎬 动画架构变更（重要更新）

### 去动画化重构
后端已完成**去动画化**重构，彻底改变动画处理方式：

| 重构前（旧架构） | 重构后（新架构） |
|-----------------|-----------------|
| 后端计算 `sin(t)` 呼吸动画 | **后端只发送目标值** |
| 30fps 轮询持续更新 | **事件驱动**：`set_head()` 后立即发送 |
| 后端处理平滑过渡 | **前端负责所有平滑动画** |
| 双引擎冲突（前后端都做动画） | **单一职责**：前端唯一动画引擎 |

### 对前端的影响

#### 1. 参数语义变化
现在后端发送的参数是 **"干巴巴的目标值"**，例如：
- `{ "ParamAngleX": 15 }` 表示"头部应该转到 15 度"
- **不再是**一个正在变化中的中间值

#### 2. 前端职责
前端必须自己实现：
- **平滑过渡（Lerp）**：从前一个值平滑过渡到新目标值
- **呼吸动画**：如果需要呼吸效果，前端自己计算 `sin(t)` 叠加
- **眨眼动画**：前端自己控制眨眼频率和幅度
- **所有时间相关的动画效果**

#### 3. 消息频率
- **之前**：30fps 恒定流，包含动画中间值
- **现在**：事件驱动，仅当参数变化时发送
- **心跳**：每 2 秒发送一次当前参数（仅用于保活）

### 前端实现建议

```typescript
// 1. 平滑过渡示例（线性插值）
class Live2DAnimator {
  private currentParams: Record<string, number> = {};
  private targetParams: Record<string, number> = {};
  
  update(deltaTime: number) {
    // 对每个参数进行线性插值
    for (const [key, targetValue] of Object.entries(this.targetParams)) {
      const currentValue = this.currentParams[key] || targetValue;
      const speed = 5.0; // 插值速度
      this.currentParams[key] = lerp(currentValue, targetValue, speed * deltaTime);
    }
    
    // 应用参数到 Live2D 模型
    this.applyParams(this.currentParams);
  }
  
  setTargetParams(newParams: Record<string, number>) {
    // 后端发送的目标值直接设置为目标参数
    this.targetParams = { ...this.targetParams, ...newParams };
  }
}

// 2. 呼吸动画叠加示例
function addBreathAnimation(baseParams: Record<string, number>, time: number): Record<string, number> {
  const breath = Math.sin(time * 2) * 0.2; // 呼吸幅度
  return {
    ...baseParams,
    ParamBodyAngleY: (baseParams.ParamBodyAngleY || 0) + breath,
    ParamBodyAngleZ: (baseParams.ParamBodyAngleZ || 0) + breath * 0.5,
  };
}

// 3. 眨眼动画示例
class BlinkController {
  private nextBlinkTime: number = 0;
  
  update(time: number, params: Record<string, number>): Record<string, number> {
    if (time >= this.nextBlinkTime) {
      // 执行眨眼
      params.ParamEyeLOpen = 0.2;
      params.ParamEyeROpen = 0.2;
      
      // 设置下一次眨眼时间（2-6秒后）
      this.nextBlinkTime = time + 2 + Math.random() * 4;
    } else if (params.ParamEyeLOpen < 1.0) {
      // 恢复睁眼
      params.ParamEyeLOpen = 1.0;
      params.ParamEyeROpen = 1.0;
    }
    return params;
  }
}
```

### 兼容性说明
- **向后兼容**：前端无需立即修改，现有代码仍能工作
- **逐步迁移**：建议逐步实现平滑过渡，提升用户体验
- **性能优化**：事件驱动减少了网络流量，前端动画更流畅

## 🚀 协议升级预告（未来准备）

### 何时升级？
当后端管理员开启 `ENABLE_JSONRPC_RESPONSE=true` 时，前端将开始接收 JSON-RPC 2.0 格式的消息。升级前会提前通知。

### 新协议格式示例

#### 1. 动画更新（Live2D参数）
**注意**：这些参数是**目标值**，前端需要自己实现平滑过渡。
```json
{
  "jsonrpc": "2.0",
  "method": "animation.update",
  "params": {
    "channel": "animation",
    "version": "1.0",
    "timestamp": 1776320174965,
    "data": {
      "ParamAngleX": 15,      // 🔥 目标值：头部应该转到15度
      "ParamAngleY": -10,     // 🔥 目标值：头部应该转到-10度
      "ParamMouthOpenY": 0.5  // 🔥 目标值：嘴巴应该开到0.5
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
  // 🔥 所有参数都是目标值，前端负责平滑过渡
  ParamAngleX?: number;      // 目标头部X角度 (-30~30)
  ParamAngleY?: number;      // 目标头部Y角度 (-30~30)
  ParamAngleZ?: number;      // 目标头部Z角度 (-30~30)
  ParamBodyAngleX?: number;  // 目标身体X角度 (-10~10)
  ParamBodyAngleY?: number;  // 目标身体Y角度 (-10~10)
  ParamBodyAngleZ?: number;  // 目标身体Z角度 (-10~10)
  ParamMouthOpenY?: number;  // 目标嘴巴开合 (0~1)
  ParamEyeLOpen?: number;    // 目标左眼开合 (0~1, -1表示前端眨眼)
  ParamEyeROpen?: number;    // 目标右眼开合 (0~1, -1表示前端眨眼)
  ParamHairAhoge?: number;   // 目标头发飘动 (-3~3)
  ParamArmLA?: number;       // 目标左臂A显示度 (0~1)
  ParamArmLB?: number;       // 目标左臂B显示度 (0~1)
  ParamArmRA?: number;       // 目标右臂A显示度 (0~1)
  ParamArmRB?: number;       // 目标右臂B显示度 (0~1)
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
- [ ] **新增**：理解动画架构变更，后端现在只发送目标值，前端负责所有平滑动画

### 第二阶段（协议升级前准备）
- [ ] 实现 JSON-RPC 2.0 基础解析器
- [ ] 添加 TypeScript 类型定义
- [ ] 实现三通道消息分发逻辑
- [ ] 实现标准错误处理
- [ ] **新增**：实现前端平滑动画引擎（Lerp 过渡）
- [ ] **新增**：实现呼吸、眨眼等时间相关动画（可选）
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
*文档版本：V1.1*
*最后更新：2026-04-16*
*对应后端版本：第一阶段重构完成（含去动画化）*
*主要更新：新增"动画架构变更"章节，说明后端只发送目标值*