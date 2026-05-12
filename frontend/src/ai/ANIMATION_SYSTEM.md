# Live2D 前端动画控制系统 — 实现总结

## 架构概览

```
SDK 层 (motion → physics → pose → breath)     ← 原生，不动
        ↓
Layer 0: 微表情噪声 (AiMicroNoise.ts)          ← 面部"活气"
        ↓
Layer 2: 角度组合伪位移 (AiIdleAnimator.ts)     ← 身体摇摆
        ↓
Layer B: Burst 偶发大动作 (AiIdleAnimator.ts)   ← 随机大动作
        ↓
后端指令覆盖 (AiWebSocket.ts backendTouched)    ← 最高优先级
        ↓
lappmodel.ts: 指数衰减 lerp + setParameterValueById
```

## 文件清单

| 文件 | 职责 |
|------|------|
| `src/ai/AiIdleAnimator.ts` | 身体动画：正弦摇摆 + Burst 偶发动作 |
| `src/ai/AiMicroNoise.ts` | 面部微表情：随机游走噪声 |
| `src/ai/AiWebSocket.ts` | 参数存储 + 后端桥接 + 优先级管理 |
| `src/ai/AiAudioManager.ts` | TTS 音频播放 + 口型同步 |
| `src/lappmodel.ts` | 模型 update() 主循环，lerp 平滑注入所有参数 |

---

## 一、身体摇摆：角度组合伪位移（方法二）

### 问题

Live2D 模型（Natori）没有 X 轴平移参数。`ParamAllX` 虽在 cdi3.json 中定义，但无部件引用，设值无效。

### 方案

用 **单信号源 + 多角度组合** 制造"重心偏移"的视觉错觉。

真实的人左右摇摆时：重心压到一侧腿上 → 骨盆侧倾 → 上身微斜 → 头微倾。这些角度变化叠在一起，大脑会解读为"他在左右晃"，即使网格实际没有平移。

### 信号源

```
sway = sin(t × 1.5) × 8
```

一个正弦波驱动全部部位，只乘不同系数。一帧内同方向、同速度、同加速度——天生绝对同步，不存在部位之间"脱节"。

### 参数映射

| 参数 | 公式 | 振幅 | 作用 |
|------|------|------|------|
| `ParamBodyAngleZ` | `sway × 0.9` | ±7.2 | **身体侧倾（主力）** |
| `ParamWaistAngleZ` | `sway × 0.8` | ±6.4 | 腰部骨盆旋转 |
| `ParamAngleZ` | `sway × 0.4` | ±3.2 | 头微侧倾 |
| `ParamBodyAngleX` | `sway × 0.3` | ±2.4 | 身体轻微旋转 |
| `ParamLeftShoulderUp` | `max(0, sway × 0.3)` | 0~2.4 | 重心侧耸肩 |
| `ParamRightShoulderUp` | `max(0, -sway × 0.3)` | 0~2.4 | 重心侧耸肩 |

### 关键设计决策

- **BodyAngleZ 是主力**：侧倾（身体绕 Z 轴旋转）比 X 轴旋转更能传递"重心偏移"感
- **肩膀用 max(0, x)** ：只在重心侧耸肩，对侧归零，避免"双肩齐耸"的僵硬感
- **频率 1.5Hz**：比呼吸快、比心跳慢，接近真实摇摆节奏
- **摇摆幅度 ±8**：视觉明显但不夸张

---

## 二、面部微表情："活气系统"

### 问题

面部参数（眉毛、眼球、嘴角、脸颊）默认为 0，完全静止。角色像"面具"。

### 方案

用 **极慢随机游走** 给每个面部参数持续注入微小噪声（±0.01~0.03）。

### MicroNoise 算法

```
每帧:
  if random() < speed × dt:
    target = (random - 0.5) × 2    // 重选目标 [-1, 1]
  value += (target - value) × 0.015  // 极慢 lerp 滑过去
  return value
```

- `speed`: 约每秒 0.1~0.4 次重选目标（每个部位独立频率）
- lerp 因子 0.015：变化极慢，肉眼感觉"有在动但看不出在动什么"

### 参数映射

| 参数 | 噪声幅度 | 条件 |
|------|---------|------|
| `ParamBrowLY/RY` | ±0.025 | 后端未控制眉毛 |
| `ParamEyeBallX` | ±0.03 | 后端未控制眼球 |
| `ParamEyeBallY` | ±0.025 | 后端未控制眼球 |
| `ParamMouthForm` | ±0.015 | 不在讲话（mouth 未被后端控制） |
| `ParamCheek` | ±0.01 | 后端未控制脸颊 |
| `ParamEyeLSmile/RSmile` | ±0.012 | 后端未控制 |

### 关键设计决策

- **每个部位独立噪声实例**：眉毛、眼球、嘴各动各的，不会出现"整张脸同步抽搐"
- **幅度极小**：超过 0.03 就从"活气"变成"抽搐"
- **嘴角只在静默时**：`backendTouched.has("ParamMouthOpenY")` 检测是否在说话
- **位置**：在 AiIdleAnimator 正弦之前执行，可以被后端覆盖

---

## 三、Burst 偶发大动作

### 机制

随机间隔 3~8 秒触发一次预定义的动作模板，经过 attack → hold → decay 三阶段。

### 动作模板 (BURST_POOL)

| 标签 | 目标参数 | 攻击/保持/衰减(s) |
|------|---------|-------------------|
| quickLeft | AngleX:-20, AngleZ:6 | 0.25/0.3/0.7 |
| quickRight | AngleX:20, AngleZ:-4 | 0.25/0.3/0.7 |
| tiltLeft | AngleZ:-16, AngleY:5 | 0.35/0.6/0.8 |
| tiltRight | AngleZ:16, AngleY:4 | 0.35/0.6/0.8 |
| lookUp | AngleY:14, BodyAngleY:5 | 0.30/0.5/0.9 |
| lookDown | AngleY:-12, BodyAngleY:4 | 0.30/0.5/0.9 |
| leanIn | BodyAngleX:-6, AngleX:10 | 0.40/0.8/1.2 |
| swayBody | BodyAngleX:7, AngleZ:6, AngleX:-10 | 0.50/1.0/1.2 |

- attack: easeOutCubic
- decay: easeInOutCubic
- 基底值从当前参数值快照（`_burstBase`），decay 回归基底

### 触发条件

- 随机间隔 3~8 秒
- 目标参数不被后端占用（`touched` 检查）
- 当前无 Burst 在执行

---

## 四、平滑机制（lappmodel.ts）

### 为什么不依赖 SDK physics

Live2D physics3.json 只处理**挂件物理**（头发、裙子、胸），头部旋转参数是物理的 **INPUT** 而非 OUTPUT。SDK physics 不会帮我们平滑头部/身体旋转。

### 手动指数衰减 lerp

```typescript
lerpFactor = 1 - exp(-3.0 × dt)  // gentle, ~1s 收敛到目标
smoothed = current + (target - current) × lerpFactor
```

- Mouth: `lerpFactor = 1 - exp(-20 × dt)` — 快速响应（口型需实时）
- Eye blink: 原生正弦 blink 计时器，后端显式下发时覆盖
- Arms: 与 body 相同的 gentle lerp

### 平滑参数在 `_smoothedAI` 中维护

每帧 lerp 到 `aiFaceParams` 中的目标值，避免正弦波直接写入导致的视觉跳跃。

---

## 五、优先级系统（AiWebSocket.ts）

### backendTouched 机制

`Set<string>` 记录后端 WebSocket 显式下发的参数名。

- **AiIdleAnimator**：写参数前检查 `!touched.has(paramName)`，被后端占用的参数跳过
- **AiMicroNoise**：同上
- **lappmodel**：眼睛参数检测 `touched.has("ParamEyeLOpen")` 决定覆盖还是用 blink 计时器

### 重置

- 后端每发一次消息，调用 `AI_IDLE.markBackendActive()` 重置 `_fadeFrame = 0`
- 180 帧无后端消息后，`touched.clear()` 清空，空闲动画全面接管

### 表情映射

```
后端 emotion → EMOTION_EXPRESSION_MAP → expression3.json 文件 ID
happy→F01, sad→F04, angry→F03, fear→F02, gentle→F01, serious→F05, neutral→F01
```

体态联动：sad→身体前倾, angry→身体后仰, happy→身体微前倾

---

## 六、已探索但未采用的方案

### 方法一：ParamAllX 位移（无效）

Natori 模型的 `ParamAllX` 无 mesh 部件引用，设值不产生任何视觉变化。

### sin³ 平滑 + 旋转轴解耦（已写暂屏蔽）

在 AiIdleAnimator 中实现了但当前被零值覆盖：
- sin³ 消除正弦波峰停顿感
- X/Y 共享主相位，Y 振幅与 |sinX| 反相关（转头时不仰头）

当前头部旋转暂时归零（配合摇摆测试），需要时取消注释即可恢复。

### ParamBodyAngleX 大幅旋转（已替换）

原始的 `±9.0 bodySwing` 方法二已被"角度组合伪位移"替代，后者效果更好。

---

## 七、调参指南

| 想调的效果 | 改哪个 | 在哪里 |
|-----------|--------|--------|
| 摇摆幅度更大/更小 | `sway = sin(t * 1.5) * 8` 的 `8` | AiIdleAnimator.ts:71 |
| 摇摆更快/更慢 | `t * 1.5` 的 `1.5` | 同上 |
| 身体侧倾比例 | `sway * 0.9` 的 `0.9` | AiIdleAnimator.ts:79 |
| 腰部旋转比例 | `sway * 0.8` 的 `0.8` | AiIdleAnimator.ts:83 |
| 微表情明显度 | `* 0.025` 等幅度系数 | AiMicroNoise.ts:46-71 |
| 微表情变化速度 | `new MicroNoise(0.002)` 的 speed | AiMicroNoise.ts:28-34 |
| Burst 触发频率 | `3 + Math.random() * 5` | AiIdleAnimator.ts:147 |
| lerp 收敛速度 | `-3.0 * dt` 的 `3.0` | lappmodel.ts:589 |
