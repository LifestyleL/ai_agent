# Live2D 参数输入控制改进计划

## 概述

当前Live2D系统实现了基本的动画和语音口型同步，但缺乏细粒度的参数控制接口。本文档分析现有架构，识别问题，并提出改进方案，以支持外部参数输入控制。

## 当前架构分析

### 后端 (Python)
- **live2d_manager.py**: 单例管理器，每33ms通过WebSocket发送Live2D参数
  - 使用`Live2DAnimator`生成参数（或从TTS队列获取）
  - 提供`set_emotion_mode(mode)`和`send_tts(audio_base64, visemes)`接口
- **animator.py**: 动画生成器，根据时间正弦波生成头部、身体、嘴巴等参数
  - 支持两种模式：`idle`（低活动度）和`thinking`（高活动度）
  - 自动切换模式，产生自然的微小动作

### 前端 (TypeScript)
- **LAppAIWebSocket.ts**: 接收WebSocket数据，更新`aiFaceParams`
  - 映射字段：`eyeLeft` → `ParamEyeLOpen`, `eyeRight` → `ParamEyeROpen`, `mouth` → `ParamMouthOpenY`等
  - 处理TTS音频和口型数据
- **lappmodel.ts**: 每帧调用`update()`，平滑应用AI参数到模型
  - 头部平滑系数0.85，身体平滑系数0.92
  - 眨眼完全由前端控制（随机眨眼）
  - 嘴巴在播放音频时使用viseme，否则平滑回归闭嘴

### 数据流
```
animator.compute_params() → live2d_manager WebSocket发送 → 前端LAppAIWebSocket接收 → lappmodel.update()应用
```

## 识别的问题与限制

### 1. 参数映射不一致
- 前后端参数名称需保持一致，当前映射关系在`LAppAIWebSocket._onMessage`中硬编码
- 扩展新参数需同时修改前后端

### 2. 参数范围不匹配
| 参数 | 后端范围 (animator) | 前端范围 (clamp) | 问题 |
|------|-------------------|-----------------|------|
| hair | 无限制 (实际可达±3.5) | -1 ~ 1 | 超出范围被截断 |
| bodyX | -4 ~ 4 | -1 ~ 1 | 动画幅度被限制 |
| bodyY | -3 ~ 3 | -0.5 ~ 0.5 | 动画幅度被限制 |
| bodyZ | -2 ~ 2 | -0.3 ~ 0.3 | 动画幅度被限制 |

### 3. 控制粒度不足
- 仅有`set_emotion_mode(mode)`切换活动度
- 无法直接控制头部旋转、身体姿势、嘴巴开合等独立参数
- 缺乏实时参数覆盖机制

### 4. 眨眼控制冲突
- 前端完全接管眨眼，忽略后端传来的`eyeLeft`/`eyeRight`值
- 后端无法实现情绪化眨眼（如惊讶时睁大眼睛）

### 5. 嘴巴控制协调问题
- 静默时animator生成嘴巴正弦波动作（0~0.3）
- 前端在未播放音频时平滑回归闭嘴，可能抵消animator效果

### 6. 活动度概念未暴露
- animator内部活动度（0.3~0.75）影响动作幅度
- 外部无法调节活动度强度

### 7. 手臂控制固定
- `PartArmA=1`, `PartArmB=0`固定，无控制接口

### 8. 平滑处理可能造成延迟
- 前端平滑系数导致动作响应有延迟
- 不适合需要快速响应的场景（如跟随鼠标）

## 改进方案

### 目标
1. 提供细粒度参数控制API
2. 保持向后兼容性
3. 统一参数范围和映射
4. 支持混合控制（算法生成 + 外部覆盖）

### 方案一：扩展Animator控制接口（推荐）

在`Live2DAnimator`类中添加直接参数控制方法：

```python
class Live2DAnimator:
    def set_head(self, x=None, y=None, z=None):
        """设置头部目标值（None表示使用算法生成）"""
    
    def set_body(self, x=None, y=None, z=None):
        """设置身体目标值"""
    
    def set_mouth(self, value=None):
        """设置嘴巴开合（0~1）"""
    
    def set_hair(self, value=None):
        """设置头发飘动（-1~1）"""
    
    def set_eyes(self, left=None, right=None):
        """设置眼睛开合（0~1，-1表示使用前端眨眼）"""
    
    def set_arms(self, arm_a=None, arm_b=None):
        """设置手臂状态（0~1）"""
    
    def set_activity(self, value=None):
        """设置活动度（0~1）"""
    
    def set_mode(self, mode):
        """设置模式（idle/thinking）"""
    
    def reset_control(self):
        """重置所有控制，恢复完全算法生成"""
```

**实现逻辑**：
- 添加目标值变量（`_target_head_x`等），初始为`None`
- `compute_params()`中检查目标值，若非`None`则使用目标值，否则使用算法生成
- 支持部分覆盖（如只设置head_x，其他仍由算法生成）

### 方案二：扩展Live2DManager控制接口

在`Live2DManager`中暴露控制方法，转发给animator：

```python
class Live2DManager:
    def set_head(self, x=None, y=None, z=None):
        self.animator.set_head(x, y, z)
    
    def set_body(self, x=None, y=None, z=None):
        self.animator.set_body(x, y, z)
    
    # ... 其他类似方法
    
    def send_custom_params(self, params_dict):
        """直接发送自定义参数（覆盖当前帧）"""
        # 将params_dict放入队列，_sync_loop优先使用
```

### 方案三：统一参数范围

调整animator中参数生成范围，匹配前端限制：

```python
# animator.py修改
def compute_params(self, t: float):
    # ...
    return {
        "eyeLeft": blink,
        "eyeRight": blink,
        "mouth": clamp(mouth, 0, 1),
        "headX": clamp(target_head_x, -10, 10),
        "headY": clamp(target_head_y, -8, 8),
        "headZ": clamp(target_head_z, -5, 5),
        "hair": clamp(hair, -1, 1),  # 增加限制
        "bodyX": clamp(target_body_x, -1, 1),      # 调整范围
        "bodyY": clamp(target_body_y, -0.5, 0.5),  # 调整范围
        "bodyZ": clamp(target_body_z, -0.3, 0.3),  # 调整范围
        "PartArmA": 1,
        "PartArmB": 0
    }
```

**注意**：调整范围会改变现有动画幅度，需测试确认效果。

### 方案四：眨眼控制协商

扩展眨眼控制协议：
- 后端发送`eyeLeft`/`eyeRight`为`-1`时，前端使用自主眨眼
- 其他值（0~1）时，前端使用该值覆盖眨眼
- 前端保留随机眨眼触发逻辑，但当后端提供有效值时暂时禁用

### 方案五：嘴巴控制协调

明确嘴巴控制优先级：
1. TTS音频播放时：使用viseme口型
2. 外部设置嘴巴值时：使用设置值
3. 静默且无设置时：使用animator生成的轻微嘴巴动作（可选）

### 方案六：扩展WebSocket协议（可选）

定义更丰富的消息类型：

```json
{
  "type": "PARAMS",
  "data": {"eyeLeft": 1.0, "headX": 0.5, ...}
}
```
```json
{
  "type": "CONTROL",
  "command": "set_head",
  "args": {"x": 0.5, "y": 0.2}
}
```

## 实施步骤

### 第一阶段：基础控制接口（预计2-3天）
1. 修改`animator.py`，添加目标值变量和控制方法
2. 修改`live2d_manager.py`，暴露控制接口
3. 统一参数范围（调整animator限制）
4. 测试基本功能，确保向后兼容

### 第二阶段：眨眼和嘴巴协调（预计1-2天）
1. 实现眨眼控制协商协议
2. 明确嘴巴控制优先级
3. 更新前端`LAppAIWebSocket`和`lappmodel.ts`支持新协议
4. 测试协调效果

### 第三阶段：高级功能（可选）
1. 实现WebSocket控制协议扩展
2. 添加REST API控制接口
3. 开发UI控制面板
4. 录制/回放动作序列

## 代码修改示例

### animator.py 修改片段

```python
class Live2DAnimator:
    def __init__(self):
        # 现有初始化...
        self._target_head_x = None
        self._target_head_y = None
        self._target_head_z = None
        # ... 其他目标值
        
    def set_head(self, x=None, y=None, z=None):
        if x is not None:
            self._target_head_x = clamp(x, -10, 10)
        if y is not None:
            self._target_head_y = clamp(y, -8, 8)
        if z is not None:
            self._target_head_z = clamp(z, -5, 5)
            
    def compute_params(self, t: float):
        # 头部计算
        if self._target_head_x is not None:
            target_head_x = self._target_head_x
        else:
            # 原有算法生成
            main = math.sin(t * 0.6)
            noise_x = math.sin(t * 0.25 + 10) * 0.4
            target_head_x = (main * 7 + noise_x) * activity
            target_head_x = clamp(target_head_x, -10, 10)
        # ... 其他参数类似
```

### live2d_manager.py 修改片段

```python
class Live2DManager:
    # ... 现有方法
    
    def set_head(self, x=None, y=None, z=None):
        self.animator.set_head(x, y, z)
        
    def set_emotion_mode(self, mode: str):
        """保持现有接口，兼容旧代码"""
        self.animator.mode = mode
        
    def send_custom_params(self, params_dict: dict):
        """直接发送自定义参数（下一帧生效）"""
        self._tts_queue.put(params_dict)
```

## 测试计划

1. **单元测试**：测试animator控制接口
2. **集成测试**：通过agent_driver调用控制接口，观察Live2D响应
3. **兼容性测试**：确保现有TTS和情绪模式功能正常
4. **性能测试**：控制接口不应影响33ms发送周期

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 破坏现有功能 | 高 | 保持向后兼容，分阶段实施，充分测试 |
| 参数范围调整改变动画表现 | 中 | 保留配置项，可调整范围系数 |
| 前端性能影响 | 低 | 控制消息频率，避免每帧大量计算 |
| 多控制源冲突 | 中 | 定义明确优先级：TTS > 外部设置 > 算法生成 |

## 后续扩展方向

1. **表情系统**：定义高兴、悲伤、惊讶等表情预设
2. **动作序列**：支持录制和回放复杂动作序列
3. **物理模拟**：更自然的头发、服装物理效果
4. **交互响应**：根据用户输入实时调整表情和动作
5. **多模型支持**：适配不同Live2D模型，自动映射参数

## 结论

当前Live2D系统具有良好的基础动画和TTS口型同步，但缺乏细粒度控制接口。通过扩展Animator控制接口、统一参数范围、协调眨眼和嘴巴控制，可以显著提升系统灵活性和表现力。建议按三个阶段实施，优先实现基础控制接口，保持向后兼容性。

---
*文档版本：1.0*
*创建日期：2026-04-15*
*更新日期：2026-04-15*