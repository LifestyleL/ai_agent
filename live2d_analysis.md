# Live2D Cubism SDK for Web v5 深度分析

> 分析对象: `CubismSdkForWeb-5-r.4/` | 日期: 2026-04-27

---

## 一、SDK 分层架构

```
┌─────────────────────────────────────────────────────┐
│  Samples/TypeScript/Demo/src/                       │
│  LAppModel, LAppDelegate, LAppView, ...             │  ← 示例应用层
├─────────────────────────────────────────────────────┤
│  @framework/                                        │
│  CubismUserModel, CubismMotion, CubismBreath,       │  ← TypeScript 框架层
│  CubismEyeBlink, CubismPhysics, CubismPose,         │
│  CubismRenderer, CubismModelMatrix                  │
├─────────────────────────────────────────────────────┤
│  Core/live2dcubismcore.js (WASM)                    │  ← C++ 编译的 WebAssembly
│  Core/live2dcubismcore.d.ts                         │  ← 核心类型定义
└─────────────────────────────────────────────────────┘
```

- **Core 层**: C++ 编译为 WASM，负责模型加载(.moc3)、参数计算、顶点变形。暴露 `Moc`, `Model`, `Parameters`, `Parts`, `Drawables` 等底层 API。
- **Framework 层**: TypeScript 封装，提供动作管理、物理引擎、呼吸/眨眼、渲染器等高层抽象。
- **示例应用层**: Demo 演示如何使用 Framework 层。

---

## 二、核心渲染管线

### 2.1 渲染循环

```
requestAnimationFrame(loop)
  └→ LAppPal.updateTime()              // 计算 deltaTime
  └→ LAppSubdelegate.update()          // 每帧更新
       └→ gl.clear()                   // WebGL 清屏
       └→ LAppView.render()
            └→ LAppLive2DManager.onUpdate()
                 └→ LAppModel.update()         // ★ 参数更新
                 │    ├→ model.loadParameters()    // 恢复默认参数
                 │    ├→ motionManager.updateMotion()  // 动作动画覆盖
                 │    ├→ physics.evaluate()         // 物理飘动
                 │    ├→ pose.updateParameters()    // 骨骼防穿模
                 │    ├→ breath.updateParameters()  // 呼吸起伏
                 │    ├→ [AI参数设置点]             // ★ 这是我们介入的位置
                 │    ├→ model.saveParameters()
                 │    └→ model.update()             // 顶点计算
                 └→ LAppModel.draw(projection)
                      └→ getRenderer().drawModel()  // WebGL 绘制
```

**关键代码** ([lappmodel.ts:543-585](CubismSdkForWeb-5-r.4/Samples/TypeScript/Demo/src/lappmodel.ts#L543-L585)):

```typescript
public update(): void {
    this._model.loadParameters();  // ① 恢复模型默认参数

    // ② 官方引擎组件更新（依次叠加参数修改）
    this._motionManager.updateMotion(this._model, dt);  // 动作动画
    this._physics.evaluate(this._model, dt);              // 物理飘动
    this._pose.updateParameters(this._model, dt);         // 骨骼防穿模
    this._breath.updateParameters(this._model, dt);       // 呼吸起伏

    // ③ AI 参数覆盖（在官方引擎之后，确保最高优先级）
    this._model.setParameterValueById(idMouth, mouthValue);

    this._model.saveParameters();  // ④ 保存最终参数
    this._model.update();          // ⑤ 触发顶点变形计算
}
```

### 2.2 渲染方式

- **WebGL 1.0** 渲染，通过 `LAppSubdelegate.createShader()` 定义简单的纹理着色器
- 模型贴图从 PNG 文件加载到 WebGL 纹理单元
- `CubismRenderer_WebGL.drawModel()` 遍历所有 Drawable，逐网格绑定纹理并 `drawElements()`
- **SDK 的渲染管线可以直接复用** — 创建 Canvas、初始化 CubismFramework、加载模型、在 requestAnimationFrame 中调用 update+draw 即可

---

## 三、参数系统深度解析

### 3.1 参数到底能控制什么？

Live2D 模型的参数是**预定义的变形目标权重**。每个参数有 ID、默认值、最小值、最大值。这个范围是在模型制作时由建模师设定的。

Core 层暴露的参数结构 ([live2dcubismcore.d.ts:168-196](CubismSdkForWeb-5-r.4/Core/live2dcubismcore.d.ts#L168-L196)):

```typescript
class Parameters {
    count: number;             // 参数总数
    ids: Array<string>;        // 参数名称列表
    minimumValues: Float32Array;  // 各参数最小值
    maximumValues: Float32Array;  // 各参数最大值
    defaultValues: Float32Array;  // 各参数默认值
    values: Float32Array;         // ★ 当前参数值（直接可写！）
    keyCounts: Int32Array;       // 关键帧数量
    keyValues: Array<Float32Array>; // 关键帧值
}
```

**参数 ID 命名规范** (来自框架常量 `CubismDefaultParameterId`):

| 参数 ID | 作用 | 典型范围 |
|---------|------|---------|
| `ParamAngleX` | 头部左右旋转（Yaw） | -30 ~ 30 |
| `ParamAngleY` | 头部上下旋转（Pitch） | -30 ~ 30 |
| `ParamAngleZ` | 头部左右倾斜（Roll） | -30 ~ 30 |
| `ParamBodyAngleX` | 身体左右摇摆 | -10 ~ 10 |
| `ParamBodyAngleY` | 身体前后俯仰 | -10 ~ 10 |
| `ParamBodyAngleZ` | 身体旋转 | -10 ~ 10 |
| `ParamEyeLOpen` | 左眼开合 | 0 ~ 1 |
| `ParamEyeROpen` | 右眼开合 | 0 ~ 1 |
| `ParamMouthOpenY` | 嘴巴纵向开合 | 0 ~ 1 |
| `ParamEyeBallX` | 眼球水平方向 | -1 ~ 1 |
| `ParamEyeBallY` | 眼球垂直方向 | -1 ~ 1 |
| `ParamHairAhoge` | 呆毛飘动 | -3 ~ 3 |
| `ParamArmLA/RA` | 左右上臂 A | 0 ~ 1 |
| `ParamArmLB/RB` | 左右上臂 B | 0 ~ 1 |
| `ParamBreath` | 呼吸幅度 | 0 ~ 1 |

### 3.2 回答你的核心问题：为什么参数映射只能做小幅度动作？

**原因不在 SDK，而在模型本身。**

1. **参数范围是模型制作时设定的**。如果建模师把 `ParamBodyAngleX` 的范围设为 `[-10, 10]`，你传 30 的结果和传 10 一样（被 Clamp）。
2. **大幅度身体动作（如挥手、转身、弯腰）需要多个参数协同变化**。单个 `ParamBodyAngleX` 只能做侧倾。真正的"挥手"需要 `ParamArmLA + ParamArmLB + ParamArmRA + ParamArmRB` 同时配合时间曲线变化——这正是 `.motion3.json` 文件做的事。
3. **物理引擎需要时间去推演**。直接写参数值是瞬时的、没有惯性的。`.motion3.json` + `physics3.json` 的组合才能产生自然的摇晃。

**结论**: **完全可以靠参数映射控制 AI 数字人身体**，但需要：
- A) 正确的参数组合（不是 1-2 个参数）
- B) 参数平滑过渡（指数衰减 lerp）
- C) 保留物理引擎的叠加效果

现有前端代码已经实现了这个机制（见 [lappmodel.ts:543-585](CubismSdkForWeb-5-r.4/Samples/TypeScript/Demo/src/lappmodel.ts#L543-L585)），只是当前只激活了嘴型控制。查看注释掉的代码（615-798 行），之前有完整的 AI 参数控制：

```typescript
// 注释掉的代码显示完整的 AI 控制已经实现过：
["ParamAngleX", "ParamAngleY", "ParamAngleZ", "ParamHairAhoge"].forEach(key => {
    this._smoothedAI[key] = current + (targetVal - current) * lerpFactorHead;
});
["ParamBodyAngleX", "ParamBodyAngleY", "ParamBodyAngleZ"].forEach(key => {
    this._smoothedAI[key] = current + (targetVal - current) * lerpFactorBody;
});
```

---

## 四、Motion 文件 vs 实时参数控制

### 4.1 `.motion3.json` 是什么？

它是**预先制作的关键帧动画曲线**，格式为参数列表在时间轴上的值变化：

```json
{
  "Version": 3,
  "Meta": { "Duration": 3.0, "Fps": 30, "Loop": true },
  "Curves": [
    {
      "Target": "Parameter",
      "Id": "ParamAngleX",
      "Segments": [0, 1.0, 1, 0.5, 2, -0.3, 3, 0]
    }
  ]
}
```

由动画师在 Live2D Cubism Editor 中制作，定义复杂动作（如挥手、跳舞、坐下）。

### 4.2 实时参数控制 vs Motion 文件

| 维度 | 实时参数控制 | .motion3.json |
|------|-------------|---------------|
| 复杂度 | 需自行处理时间曲线 | SDK 自动插值 |
| 灵活性 | 完全自由，任意帧任意值 | 仅限于预设动作 |
| 自然度 | 需手写平滑算法 | 已包含缓动曲线 |
| AI 适应性 | ✅ 完美适配 | ❌ 只能用预设 |
| 工作流 | 后端计算 → WebSocket → 前端 | 只能播放文件 |

**推荐策略**: **混合使用**。
- **口型、眼部、头部朝向** → 实时参数（后端 AI 计算）
- **待机动作、表情切换** → 调用 SDK 的 `startMotion()` 播放 .motion3.json
- **呼吸、物理** → 始终启用的 SDK 引擎组件

现有代码 [lappmodel.ts:554-557](CubismSdkForWeb-5-r.4/Samples/TypeScript/Demo/src/lappmodel.ts#L554-L557) 已经正确保留了所有引擎组件：
```typescript
if (this._motionManager != null) this._motionManager.updateMotion(this._model, dt);
if (this._physics != null) this._physics.evaluate(this._model, dt);
if (this._pose != null) this._pose.updateParameters(this._model, dt);
if (this._breath != null) this._breath.updateParameters(this._model, dt);
```

---

## 五、能否复用 SDK 的渲染能力？

**可以，而且非常容易。**

SDK 的渲染依赖链很短：

1. 一个 `<canvas>` 元素
2. 调用 `CubismFramework.startUp()` + `CubismFramework.initialize()`
3. 加载 `.moc3` 模型文件 → `Moc.fromArrayBuffer()` → `Model.fromMoc()`
4. 加载纹理贴图到 WebGL 纹理单元
5. 创建 `CubismRenderer_WebGL`，绑定模型和纹理
6. 每帧调用 `model.update()` + `renderer.drawModel()`

整个渲染管线都在 SDK 框架层，不需要自己写 WebGL。Demo 中的 [lappdelegate.ts:110-129](CubismSdkForWeb-5-r.4/Samples/TypeScript/Demo/src/lappdelegate.ts#L110-L129) 展示了完整的 requestAnimationFrame 循环。

**不需要自己写渲染刷新** — 框架的 `CubismRenderer_WebGL` 已经处理了所有 WebGL 操作。你只需要：
- 把现有的前端 TypeScript demo 集成到 React 组件
- 通过 WebSocket 接收后端 AI 参数
- 在 `LAppModel.update()` 中设置参数值
- 让框架自动完成绘制

---

## 六、当前状态与行动计划

### 6.1 当前已实现（前端）

| 组件 | 文件 | 状态 |
|------|------|------|
| WebSocket 接收器 | [LAppAIWebSocket.ts](CubismSdkForWeb-5-r.4/Samples/TypeScript/Demo/src/LAppAIWebSocket.ts) | ✅ 完整 |
| 音频管理器 | [LAppAudioManager.ts](CubismSdkForWeb-5-r.4/Samples/TypeScript/Demo/src/LAppAudioManager.ts) | ✅ 完整 |
| 模型加载+渲染 | [lappmodel.ts](CubismSdkForWeb-5-r.4/Samples/TypeScript/Demo/src/lappmodel.ts) | ✅ 完整 |
| 嘴型同步 | [lappmodel.ts:566-582](CubismSdkForWeb-5-r.4/Samples/TypeScript/Demo/src/lappmodel.ts#L566-L582) | ✅ 已激活 |
| 头部/身体/手臂控制 | [lappmodel.ts:615-798](CubismSdkForWeb-5-r.4/Samples/TypeScript/Demo/src/lappmodel.ts#L615-L798) | ⚠️ 已实现但被注释 |
| 物理/呼吸/眨眼 | [lappmodel.ts:554-557](CubismSdkForWeb-5-r.4/Samples/TypeScript/Demo/src/lappmodel.ts#L554-L557) | ✅ 已激活 |

### 6.2 当前未实现（后端 Python → 前端）

**文件**: [deprecated/live2d/live2d_manager.py](backend/deprecated/live2d/live2d_manager.py)

完全是空桩。需要：
1. 实现 `send_params()` 通过 WebSocket 发送 AI 参数到前端
2. 实现参数计算逻辑（情绪→头部姿态→身体姿态→手臂动作的映射）

### 6.3 最小可行动方案

**后端改造**:
```python
# 在 agent_driver.py 中，每帧/每次情绪变化时：
params = {
    "type": "PARAMS",
    "data": {
        "ParamAngleX": head_yaw,      # 从情绪引擎获取
        "ParamAngleY": head_pitch,
        "ParamAngleZ": head_roll,
        "ParamBodyAngleX": body_sway,
        "ParamEyeLOpen": eye_left,
        "ParamEyeROpen": eye_right,
    }
}
await ws.send(json.dumps(params))
```

**前端改造**（取消注释已实现代码）:
```typescript
// 在 LAppModel.update() 中取消注释 615-798 行的 AI 参数控制逻辑
// 当前只有嘴型被 AI 控制，需要同时激活头部、身体、手臂
```

---

## 七、关键文件索引

| 文件 | 用途 |
|------|------|
| [Core/live2dcubismcore.d.ts](CubismSdkForWeb-5-r.4/Core/live2dcubismcore.d.ts) | 核心 C++ 类型定义 |
| [Samples/.../src/lappmodel.ts](CubismSdkForWeb-5-r.4/Samples/TypeScript/Demo/src/lappmodel.ts) | 模型加载/更新/渲染 ★核心 |
| [Samples/.../src/lappdelegate.ts](CubismSdkForWeb-5-r.4/Samples/TypeScript/Demo/src/lappdelegate.ts) | 应用主循环 requestAnimationFrame |
| [Samples/.../src/lappsubdelegate.ts](CubismSdkForWeb-5-r.4/Samples/TypeScript/Demo/src/lappsubdelegate.ts) | Canvas/WebGL/渲染协调 |
| [Samples/.../src/LAppAIWebSocket.ts](CubismSdkForWeb-5-r.4/Samples/TypeScript/Demo/src/LAppAIWebSocket.ts) | WebSocket 接收 AI 参数 |
| [Samples/.../src/LAppAudioManager.ts](CubismSdkForWeb-5-r.4/Samples/TypeScript/Demo/src/LAppAudioManager.ts) | TTS 音频播放+口型帧 |
| [backend/deprecated/live2d/live2d_manager.py](backend/deprecated/live2d/live2d_manager.py) | ❌ 后端空桩（待实现） |
