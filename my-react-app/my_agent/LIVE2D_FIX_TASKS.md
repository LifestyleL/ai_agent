# Live2D 全链路修复任务清单

> **执行者**: Claude Code  
> **目标**: 修复前后端 Live2D 参数控制链路中的所有已知问题  
> **验证标准**: 每项修复后都能通过对应测试

---

## 任务总览

| # | 优先级 | 文件 | 问题类型 |
|---|--------|------|----------|
| 1 | P0 | `LAppAIWebSocket.ts` | 删除错误的 `updateViseme()` 调用 |
| 2 | P0 | `LAppAIWebSocket.ts` | 修复 `PartArmA` 覆盖 Bug |
| 3 | P0 | `LAppModel.ts` (`update()`) | 删除每帧 console.log 性能杀手 |
| 4 | P1 | `LAppModel.ts` (`update()`) | 平滑算法改为基于 deltaTime |
| 5 | P1 | `animator.py` (`set_body` + `compute_params`) | 放宽身体参数范围 |
| 6 | P1 | `LAppAIWebSocket.ts` (`_onMessage`) | 前端身体 clamp 范围同步放宽 |
| 7 | P1 | `live2d_manager.py` | 修复 `send_custom_params` 一次性覆盖 |
| 8 | P2 | `live2d_behavior.py` | 标注弃用或整合 |
| 9 | P2 | `DEBUG_LIVE2D.md` | 更新参数范围文档 |

---

## 任务 1: 删除 LAppAIWebSocket.ts 中错误的 updateViseme() 调用

### 文件
`src/live2d/framework/LAppAIWebSocket.ts` (或实际路径)

### 问题
`_onMessage` 方法末尾, 在 WebSocket 消息回调中调用了 `updateViseme()`.
该函数依赖 `audioContext.currentTime` 进行时间轴插值, **必须且只能在每帧渲染的 `update()` 循环中调用**.
在 `onmessage` 中调用会导致口型时间轴被网络频率打碎, 口型抽风.

### 修改
找到 `_onMessage` 方法中以下代码块, **整块删除**:

```typescript
// 删除以下全部代码
if (LAppAudioManager.getInstance().getIsPlaying()) {
  LAppAudioManager.getInstance().updateViseme();
  this.aiFaceParams.ParamMouthOpenY = LAppAudioManager.getInstance().currentViseme.aa;
}
```

### 验证
- 搜索整个文件, 确认不再存在 `updateViseme` 字符串
- `updateViseme` 只应在 `LAppModel.ts` 的 `update()` 中被调用

---

## 任务 2: 修复 PartArmA 覆盖 Bug

### 文件
同 `LAppAIWebSocket.ts`

### 问题
当前代码先赋值了 `ParamArmLA` 等新参数, 然后无条件地用 `PartArmA` 覆盖:
```typescript
// 第一段: 赋值了新参数
this.aiFaceParams.ParamArmLA = this._clamp(params.ParamArmLA ?? params.armLA ?? 1, 0, 1);
// ...

// 第二段: 无条件覆盖 (Bug! 后端没发 PartArmA 也会覆盖回 1)
this.aiFaceParams.ParamArmLA = partArmA;  // 覆盖了上面刚赋的值
```

### 修改
将第二段改为**条件赋值**, 只有后端明确传了 `PartArmA` / `PartArmB` 时才映射:

```typescript
// 【新参数优先】先处理 ParamArmLA/RA/LB/RB
this.aiFaceParams.ParamArmLA = this._clamp(params.ParamArmLA ?? params.armLA ?? 1, 0, 1);
this.aiFaceParams.ParamArmRA = this._clamp(params.ParamArmRA ?? params.armRA ?? 1, 0, 1);
this.aiFaceParams.ParamArmLB = this._clamp(params.ParamArmLB ?? params.armLB ?? 1, 0, 1);
this.aiFaceParams.ParamArmRB = this._clamp(params.ParamArmRB ?? params.armRB ?? 1, 0, 1);

// 【旧版兼容】仅在后端明确传了 PartArmA/B 时才覆盖
if (params.PartArmA !== undefined && params.PartArmA !== null) {
  const partArmA = this._clamp(params.PartArmA, 0, 1);
  this.aiFaceParams.PartArmA = partArmA;
  this.aiFaceParams.ParamArmLA = partArmA;
  this.aiFaceParams.ParamArmLB = partArmA;
}
if (params.PartArmB !== undefined && params.PartArmB !== null) {
  const partArmB = this._clamp(params.PartArmB, 0, 1);
  this.aiFaceParams.PartArmB = partArmB;
  this.aiFaceParams.ParamArmRA = partArmB;
  this.aiFaceParams.ParamArmRB = partArmB;
}
```

### 验证
- 确认 `PartArmA` 相关赋值被 `if (params.PartArmA !== undefined)` 包裹
- 确认新参数 (`ParamArmLA` 等) 的赋值在旧版兼容代码之前

---

## 任务 3: 删除 LAppModel update() 中的每帧 console.log

### 文件
`src/live2d/framework/LAppModel.ts` (或实际路径)

### 问题
`update()` 方法中, 在"统一应用参数到模型"区域, 有约 7 行 `console.log`,
每帧 (60fps) 执行一次, 每秒产生 420 条日志, 严重阻塞主线程.

### 修改
找到以下代码块, **整块删除**:

```typescript
// 删除以下全部代码
// 调试日志: 显示将要应用的参数值
console.log("[MODEL] 应用AI参数到模型:");
console.log(`[MODEL] 嘴巴: ${this._smoothedAI.ParamMouthOpenY.toFixed(3)}`);
console.log(`[MODEL] 左眼: ${this._smoothedAI.ParamEyeLOpen.toFixed(3)}, 右眼: ${this._smoothedAI.ParamEyeROpen.toFixed(3)}`);
console.log(`[MODEL] 头部: X=${this._smoothedAI.ParamAngleX.toFixed(3)}, Y=${this._smoothedAI.ParamAngleY.toFixed(3)}, Z=${this._smoothedAI.ParamAngleZ.toFixed(3)}`);
console.log(`[MODEL] 身体: X=${this._smoothedAI.ParamBodyAngleX.toFixed(3)}, Y=${this._smoothedAI.ParamBodyAngleY.toFixed(3)}, Z=${this._smoothedAI.ParamBodyAngleZ.toFixed(3)}`);
console.log(`[MODEL] 头发: ${this._smoothedAI.ParamHairAhoge.toFixed(3)}`);
console.log(`[MODEL] 手臂: LA=${this._smoothedAI.ParamArmLA.toFixed(3)}, RA=${this._smoothedAI.ParamArmRA.toFixed(3)}, LB=${this._smoothedAI.ParamArmLB.toFixed(3)}, RB=${this._smoothedAI.ParamArmRB.toFixed(3)}`);
```

### 验证
- 搜索 `update()` 方法内, 确认不再有 `console.log("[MODEL]"` 的行
- 注释掉的那段"调试: 输出所有参数ID (只执行一次)"的代码可以保留 (它有 `window._paramsLogged` 保护, 只执行一次)

---

## 任务 4: 平滑算法改为基于 deltaTime (帧率无关)

### 文件
同 `LAppModel.ts`

### 问题
当前平滑算法硬编码了系数 (如 `current * 0.5 + targetVal * 0.5`),
在不同帧率 (60fps vs 144fps) 下表现完全不同, 会导致动作速度不一致.

### 修改

**步骤 4a**: 在 `update()` 方法开头, 添加 deltaTime 保护:
```typescript
const deltaTimeSeconds: number = LAppPal.getDeltaTime();
const dt = Math.min(deltaTimeSeconds, 0.1); // 新增: 防止切标签页回来后 dt 暴涨
```
注意: 后续代码中使用 `dt` 替代 `deltaTimeSeconds`.

**步骤 4b**: 替换所有硬编码的平滑算法.

找到头部平滑:
```typescript
// 替换前
["ParamAngleX", "ParamAngleY", "ParamAngleZ", "ParamHairAhoge"].forEach(key => {
  const current = this._smoothedAI[key] || 0;
  const targetVal = target[key] || 0;
  this._smoothedAI[key] = current * 0.5 + targetVal * 0.5;
});
```
替换为:
```typescript
// 替换后
const lerpHead = 1 - Math.exp(-10.0 * dt);
["ParamAngleX", "ParamAngleY", "ParamAngleZ", "ParamHairAhoge"].forEach(key => {
  const current = this._smoothedAI[key] || 0;
  const targetVal = target[key] || 0;
  this._smoothedAI[key] = current + (targetVal - current) * lerpHead;
});
```

找到身体平滑:
```typescript
// 替换前
["ParamBodyAngleX", "ParamBodyAngleY", "ParamBodyAngleZ"].forEach(key => {
  const current = this._smoothedAI[key] || 0;
  const targetVal = target[key] || 0;
  this._smoothedAI[key] = current * 0.7 + targetVal * 0.3;
});
```
替换为:
```typescript
// 替换后
const lerpBody = 1 - Math.exp(-5.0 * dt);
["ParamBodyAngleX", "ParamBodyAngleY", "ParamBodyAngleZ"].forEach(key => {
  const current = this._smoothedAI[key] || 0;
  const targetVal = target[key] || 0;
  this._smoothedAI[key] = current + (targetVal - current) * lerpBody;
});
```

找到嘴巴平滑 (非音频播放时的 AI 参数分支):
```typescript
// 替换前
const current = this._smoothedAI.ParamMouthOpenY || 0;
this._smoothedAI.ParamMouthOpenY = current * 0.5 + target.ParamMouthOpenY * 0.5;
```
替换为:
```typescript
// 替换后
const current = this._smoothedAI.ParamMouthOpenY || 0;
this._smoothedAI.ParamMouthOpenY = current + (target.ParamMouthOpenY - current) * lerpHead;
```

找到嘴巴回归闭嘴 (无音频且无 AI 参数时):
```typescript
// 替换前
this._smoothedAI.ParamMouthOpenY = (this._smoothedAI.ParamMouthOpenY || 0) * 0.85;
```
替换为:
```typescript
// 替换后
this._smoothedAI.ParamMouthOpenY = (this._smoothedAI.ParamMouthOpenY || 0) * Math.exp(-8.0 * dt);
```

### 验证
- 确认 `update()` 方法中不再存在 `* 0.5`, `* 0.7`, `* 0.85` 这类硬编码系数
- 确认所有平滑都使用了 `dt` 变量
- 确认 `const dt = Math.min(deltaTimeSeconds, 0.1)` 在使用 `dt` 之前声明

---

## 任务 5: 放宽后端身体参数范围

### 文件
`my_agent/live2d/animator.py`

### 问题
`set_body()` 和 `compute_params()` 中, 身体参数的 clamp 范围太窄,
严重限制了算法生成的动作幅度. 算法原始输出可达 +/-3+, 但被砍到 +/-1.

### 修改

**步骤 5a**: 修改 `set_body()` 方法:
```python
# 替换前
def set_body(self, x=None, y=None, z=None):
    if x is not None: self._target_body_x = clamp(x, -1, 1)
    if y is not None: self._target_body_y = clamp(y, -0.5, 0.5)
    if z is not None: self._target_body_z = clamp(z, -0.3, 0.3)
```
```python
# 替换后
def set_body(self, x=None, y=None, z=None):
    if x is not None: self._target_body_x = clamp(x, -4, 4)
    if y is not None: self._target_body_y = clamp(y, -2, 2)
    if z is not None: self._target_body_z = clamp(z, -1, 1)
```

**步骤 5b**: 修改 `compute_params()` 末尾的 clamp:
```python
# 替换前
target_body_x = clamp(target_body_x, -1, 1)
target_body_y = clamp(target_body_y, -0.5, 0.5)
target_body_z = clamp(target_body_z, -0.3, 0.3)
```
```python
# 替换后
target_body_x = clamp(target_body_x, -4, 4)
target_body_y = clamp(target_body_y, -2, 2)
target_body_z = clamp(target_body_z, -1, 1)
```

### 验证
- 在 `animator.py` 中搜索, 确认身体相关的 clamp 已全部更新
- 可运行 `test_animator_only.py` 确认 `bodyX` 在算法模式下输出超过 +/-1

---

## 任务 6: 前端身体 clamp 范围同步放宽

### 文件
`LAppAIWebSocket.ts`

### 问题
前端 `_onMessage` 中身体参数的 clamp 范围与后端不一致, 后端发出的较大值会被前端截断.

### 修改
找到以下三行:
```typescript
this.aiFaceParams.ParamBodyAngleX = this._clamp(params.bodyX ?? 0, -1, 1);
this.aiFaceParams.ParamBodyAngleY = this._clamp(params.bodyY ?? 0, -0.5, 0.5);
this.aiFaceParams.ParamBodyAngleZ = this._clamp(params.bodyZ ?? 0, -0.3, 0.3);
```
替换为:
```typescript
this.aiFaceParams.ParamBodyAngleX = this._clamp(params.bodyX ?? 0, -4, 4);
this.aiFaceParams.ParamBodyAngleY = this._clamp(params.bodyY ?? 0, -2, 2);
this.aiFaceParams.ParamBodyAngleZ = this._clamp(params.bodyZ ?? 0, -1, 1);
```

### 验证
- 确认前端身体范围与任务 5 中后端范围完全一致

---

## 任务 7: 修复 send_custom_params 一次性覆盖

### 文件
`my_agent/live2d/live2d_manager.py`

### 问题
当前 `send_custom_params` 把参数塞进 `_tts_queue`, 只存活一帧 (33ms),
下一帧立刻被 `compute_params` 的算法值覆盖. 参数"闪一下就没了".

### 修改
替换 `send_custom_params` 方法:
```python
# 替换前
def send_custom_params(self, params_dict: dict):
    """直接发送自定义参数(下一帧生效)"""
    self._tts_queue.put(params_dict)
```
```python
# 替换后
def send_custom_params(self, params_dict: dict):
    """设置自定义参数(持续生效, 直到 reset_control)"""
    if "headX" in params_dict or "headY" in params_dict or "headZ" in params_dict:
        self.animator.set_head(
            x=params_dict.get("headX"),
            y=params_dict.get("headY"),
            z=params_dict.get("headZ"),
        )
    if "bodyX" in params_dict or "bodyY" in params_dict or "bodyZ" in params_dict:
        self.animator.set_body(
            x=params_dict.get("bodyX"),
            y=params_dict.get("bodyY"),
            z=params_dict.get("bodyZ"),
        )
    if "mouth" in params_dict:
        self.animator.set_mouth(params_dict["mouth"])
    if "hair" in params_dict:
        self.animator.set_hair(params_dict["hair"])
    if "eyeLeft" in params_dict or "eyeRight" in params_dict:
        self.animator.set_eyes(
            left=params_dict.get("eyeLeft"),
            right=params_dict.get("eyeRight"),
        )
    if "PartArmA" in params_dict or "PartArmB" in params_dict:
        self.animator.set_arms(
            arm_a=params_dict.get("PartArmA"),
            arm_b=params_dict.get("PartArmB"),
        )
```

### 验证
- 确认 `send_custom_params` 内部不再有 `_tts_queue.put`
- 确认调用了 `self.animator.set_*` 系列方法
- 测试: 调用 `send_custom_params({"headX": 5})` 后, 连续多帧的输出中 `headX` 应持续为 5

---

## 任务 8: 标注 live2d_behavior.py 弃用

### 文件
`my_agent/live2d/live2d_behavior.py`

### 问题
该文件定义了一套独立的行为状态机 (`Animator` + `BaseBehavior`),
但目前**没有任何代码引用它**. 与正在使用的 `animator.py` (`Live2DAnimator`) 存在概念冲突,
容易让维护者混淆.

### 修改
在文件顶部添加弃用标注:
```python
"""
[DEPRECATED] This file is deprecated.

The current system uses Live2DAnimator from animator.py,
which employs sinusoidal algorithm + None target value override mechanism.

The behavior state machine (Animator + BaseBehavior) in this file is not referenced.
If needed, integrate its concepts into Live2DAnimator
(e.g. set_mode("happy") to switch parameter groups).
Keep this file for reference only. Do not import in new code.
"""
```

### 验证
- 搜索整个项目, 确认没有任何文件 `from live2d_behavior import` 或 `import live2d_behavior`

---

## 任务 9: 更新 DEBUG_LIVE2D.md 参数范围

### 文件
`my_agent/live2d/DEBUG_LIVE2D.md`

### 修改
找到参数范围表格, 更新 `bodyX/bodyY/bodyZ` 的范围:

```markdown
| 参数 | 范围 | 说明 |
|------|------|------|
| eyeLeft/eyeRight | -1.0 ~ 1.0 | -1=前端眨眼, 0=闭眼, 1=睁眼 |
| mouth | 0.0 ~ 1.0 | 0=闭嘴, 1=最大张嘴 |
| headX | -10.0 ~ 10.0 | 头部左右转动(左负右正) |
| headY | -8.0 ~ 8.0 | 头部上下转动(下负上正) |
| headZ | -5.0 ~ 5.0 | 头部倾斜 |
| bodyX | -4.0 ~ 4.0 | 身体左右摇摆(已放宽) |
| bodyY | -2.0 ~ 2.0 | 身体上下俯仰(已放宽) |
| bodyZ | -1.0 ~ 1.0 | 身体倾斜(已放宽) |
| hair | -1.0 ~ 1.0 | 头发飘动 |
| PartArmA/PartArmB | 0.0 ~ 1.0 | 手臂显示度(0隐藏, 1显示) |
```

### 验证
- 确认文档中的范围与 `animator.py` 和 `LAppAIWebSocket.ts` 一致

---

## 执行顺序建议

```
第一轮(后端不动, 只改前端): 任务 1, 2, 3, 4, 6
  -> 部署前端, 验证模型基本能动、不卡顿

第二轮(前后端同步改): 任务 5, 7
  -> 重启后端, 验证身体幅度、参数持续生效

第三轮(清理): 任务 8, 9
  -> 代码整洁, 文档同步
```

---

## 全局验证测试

完成所有任务后, 按以下步骤验证:

### 测试 A: 后端冒烟(不依赖前端)
```python
from live2d.live2d_manager import Live2DManager
manager = Live2DManager()
manager.start()
import time
time.sleep(0.5)

# 测试覆盖
manager.set_head(x=5)
time.sleep(1)
# 期望: 日志中 headX 持续为 5

# 测试重置
manager.reset_control()
time.sleep(1)
# 期望: headX 恢复为正弦波变化的值

# 测试身体范围
manager.set_body(x=3)
time.sleep(1)
# 期望: bodyX 为 3 (如果之前被 clamp 到 1 则说明任务 5 未完成)

manager.stop()
```

### 测试 B: 前端暴力测试(不依赖后端)
在 `LAppModel.update()` 中临时替换为 Math.sin 测试代码(之前已验证通过),
确认模型能响应参数变化.

### 测试 C: 全链路联调
1. 启动后端 `python main.py`
2. 启动前端
3. 运行 `python live2d_control_client.py`, 选择模式 1 (自动测试基本控制)
4. 观察: 模型头部平滑转动、嘴巴张合、身体有明显晃动、参数不会"闪回"
5. 在调试器中执行 `reset`, 观察模型平滑回归算法待机状态
