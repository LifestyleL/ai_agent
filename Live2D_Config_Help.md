# Live2D 模型配置文件详解 (HELP文档)

## 概述

Live2D模型配置文件(`.model3.json`)是Live2D动画系统的核心配置文件，定义了模型的所有资源、动画和交互行为。本文档详细讲解主要字段的原理、使用方法和自定义配置。

## 核心字段详解

### 1. FileReferences 字段

**作用**：定义模型所需的所有资源文件路径。

**结构**：
```json
"FileReferences": {
    "Moc": "Haru.moc3",                    // 模型核心数据文件
    "Textures": ["texture_00.png", ...],   // 纹理贴图文件
    "Physics": "Haru.physics3.json",       // 物理模拟配置
    "Pose": "Haru.pose3.json",            // 姿势配置
    "DisplayInfo": "Haru.cdi3.json",      // 显示信息
    "Expressions": [...],                 // 预定义表情
    "Motions": {...},                     // 动作序列
    "UserData": "Haru.userdata3.json"     // 用户数据
}
```

### 2. Expressions 字段

**作用**：定义模型的预定义表情配置，提供快速的表情切换功能。

**原理**：
- 每个表情包含多个参数的预设值
- 支持通过API快速调用，无需手动设置每个参数
- 适合标准化的表情表达

**结构**：
```json
"Expressions": [
    {
        "Name": "F01",
        "File": "expressions/F01.exp3.json"
    }
]
```

**表情文件结构** (F01.exp3.json)：
```json
{
    "Type": "Live2D Expression",
    "Parameters": [
        {
            "Id": "ParamMouthForm",
            "Value": 0.27,
            "Blend": "Add"
        }
    ]
}
```

**使用调用**：
```typescript
// 使用预定义表情
model.setExpression("F01");

// 尝试设置表情，如果不存在则使用随机表情
try {
    model.setExpression("F01");
} catch (error) {
    model.setRandomExpression();
}
```

### 3. Motions 字段

**作用**：定义模型的所有动作序列，是Live2D动画的核心。

**原理**：
- 动作按组分类，每个组可包含多个动作文件
- 支持淡入淡出效果和音效同步
- 通过组名+索引的方式调用

**结构**：
```json
"Motions": {
    "Idle": [
        {
            "File": "motions/idle.motion3.json",
            "FadeInTime": 0.5,
            "FadeOutTime": 0.5
        }
    ],
    "TapBody": [
        {
            "File": "motions/tap_body.motion3.json",
            "FadeInTime": 0.5,
            "FadeOutTime": 0.5,
            "Sound": "sounds/tap.wav"
        }
    ]
}
```

**动作文件结构** (motion3.json)：
```json
{
    "Version": 3,
    "Meta": {
        "Duration": 2.0,        // 动作总时长(秒)
        "Fps": 30.0,           // 帧率
        "Loop": true,          // 是否循环播放
        "CurveCount": 10,      // 参数曲线数量
        "TotalPointCount": 100 // 关键点总数
    },
    "Curves": [
        {
            "Target": "Parameter",    // 目标类型: Parameter/Model
            "Id": "ParamAngleX",      // 参数ID或模型属性
            "Segments": [0, 0, 1, 1.0, 0]  // 时间-值曲线数据
        }
    ]
}
```

**使用调用**：
```typescript
// 播放Idle组的第0个动作
model.startMotion("Idle", 0);

// 播放TapBody组的第1个动作
model.startMotion("TapBody", 1);

// 使用优先级控制
const priority = LAppDefine.PriorityNormal;  // 1-3的优先级
model.startMotion("TapBody", 0, priority);
```

### 4. Groups 字段

**作用**：定义参数的分组，用于Live2D的自动化功能。

**原理**：
- 参数分组后可以批量控制
- 特定分组有特殊自动化功能
- EyeBlink组自动参与眨眼动画
- LipSync组响应音频进行口型同步

**结构**：
```json
"Groups": [
    {
        "Target": "Parameter",
        "Name": "EyeBlink",
        "Ids": [
            "ParamEyeLOpen",
            "ParamEyeROpen"
        ]
    },
    {
        "Target": "Parameter",
        "Name": "LipSync",
        "Ids": [
            "ParamMouthOpenY"
        ]
    }
]
```

**使用调用**：
```typescript
// 自动眨眼 - SDK自动处理，无需手动调用
// 口型同步 - SDK根据音频自动调整参数

// 手动控制分组参数
const eyeBlinkGroup = model.getParameterGroup("EyeBlink");
eyeBlinkGroup.setValue(0.5);  // 批量设置组内所有参数
```

### 5. HitAreas 字段

**作用**：定义模型的可点击区域，用于交互检测。

**结构**：
```json
"HitAreas": [
    {
        "Id": "HitArea",
        "Name": "Head"
    },
    {
        "Id": "HitArea2",
        "Name": "Body"
    }
]
```

**使用调用**：
```typescript
// 检查点击位置是否在头部区域
const hitArea = model.getHitArea("Head");
if (hitArea.contains(clickX, clickY)) {
    // 触发头部点击动作
    model.startMotion("TapHead", 0);
}
```

## 自定义配置指南

### 1. 添加新的动作组

```json
"Motions": {
    "Idle": [...],
    "TapBody": [...],
    "CustomAction": [
        {
            "File": "motions/custom_action.motion3.json",
            "FadeInTime": 0.3,
            "FadeOutTime": 0.3,
            "Sound": "sounds/custom.wav"
        }
    ]
}
```

### 2. 添加新的表情

```json
"Expressions": [
    {
        "Name": "CustomHappy",
        "File": "expressions/custom_happy.exp3.json"
    }
]
```

### 3. 添加新的参数分组

```json
"Groups": [
    {
        "Target": "Parameter",
        "Name": "CustomGroup",
        "Ids": [
            "ParamCustom1",
            "ParamCustom2"
        ]
    }
]
```

## 实际应用示例

### 前端控制器调用

```typescript
class Live2DController {
    // 播放动作
    playMotion(group: string, index: number = 0) {
        const model = this.getModel();
        if (model) {
            model.startMotion(group, index, LAppDefine.PriorityNormal);
        }
    }

    // 设置表情
    setExpression(name: string) {
        const model = this.getModel();
        if (model) {
            try {
                model.setExpression(name);
            } catch (error) {
                console.warn(`表情 ${name} 不存在`);
            }
        }
    }

    // 设置自定义参数
    setCustomParameters(params: { [key: string]: number }) {
        const model = this.getModel();
        if (model) {
            for (const [paramId, value] of Object.entries(params)) {
                const id = CubismFramework.getIdManager().getId(paramId);
                model.getModel().setParameterValueById(id, value);
            }
            model.update();
        }
    }
}
```

### 后端消息处理

```python
def send_motion(self, group: str, index: int = 0):
    """发送动作指令到前端"""
    motion_data = {
        "type": "motion",
        "group": group,
        "index": index,
        "timestamp": time.time()
    }
    self.websocket_server.send_to_clients(motion_data)

def send_expression(self, emotion: str, custom_params: dict = None):
    """发送表情指令到前端"""
    expr_data = {
        "type": "expression",
        "emotion": emotion,
        "custom_params": custom_params or {},
        "timestamp": time.time()
    }
    self.websocket_server.send_to_clients(expr_data)
```

## 最佳实践

1. **动作命名**：使用有意义的组名，如`Idle`、`TapBody`、`Talk`等
2. **参数分组**：合理分组参数，便于批量控制和自动化
3. **淡入淡出**：合理设置`FadeInTime`和`FadeOutTime`避免动作切换生硬
4. **优先级管理**：使用不同的优先级确保重要动作不会被打断
5. **错误处理**：调用动作和表情时添加异常处理

## 常见问题

**Q: 动作播放失败怎么办？**
A: 检查动作文件是否存在，组名和索引是否正确，模型是否已加载。

**Q: 表情设置无效怎么办？**
A: 检查表情名称是否正确，或改用自定义参数方式。

**Q: 如何实现动作循环播放？**
A: 在motion3.json中设置`"Loop": true`，或在代码中监听动作结束事件重新播放。

这个配置文件系统让Live2D模型具有丰富的表现力和灵活的控制能力，是实现高质量虚拟角色交互的核心。

## 调试与测试策略（已实施）解决了模型自动播放随机待机动作

- 原因：在示例代码中，`LAppModel.update()` 会在 `motionManager.isFinished()` 时自动触发 `startRandomMotion(Idle)`，导致你在自动测试或手动控制时出现 "无请求、持续动了"的现象。
- 策略：
  1. `LAppModel` 引入 `_autoIdleEnabled` 标志，默认设为 `false`，避免未初始化前自动播放。
  2. `update()` 执行逻辑改为：`if (motionFinished && _autoIdleEnabled) startRandomMotion(...)`，强制先决条件。
  3. `Live2DController` 暴露 `setAutoIdleEnabled(false)`，主程序初始化时调用，确保测试阶段禁用自动Idle。
  4. 同时增加日志：`startRandomMotion`/`startMotion`/`setExpression` 触发打印，便于观察当前动作源、组、索引、文件路径（定位是否为自动流程）。

- 结果：
  - 自动idle触发已关闭，且可以通过手动指令/外部后端下发命令精准控制。
  - 控制台日志可直接用于定位"是模型自身idle还是触发命令"。

## 测试工具详解 (test_motion.py)

### 工具概述

`test_motion.py` 是专为 Live2D 模型开发的表情动作测试和参数调优工具，集成了完整的表情参数管理系统，为 AI agent 的自动化表情控制提供数据基础。

### 核心功能

#### 1. 自定义参数优先发送
- **优先机制**：`send_expression()` 默认使用 `custom_params` 而非预定义表情文件
- **实时生效**：确保参数修改能立即在模型上看到效果
- **兼容性**：支持预定义表情和自定义参数两种模式

#### 2. 表情参数记录系统
- **自动记录**：每次发送表情时自动记录参数到 `expression_records` 元组
- **数据结构**：`{emotion: {param_id: value, ...}}` 格式
- **AI 学习基础**：为未来 AI 自动调整表情提供参数数据集

#### 3. 标准化文件输出
- **exp3.json 生成**：`write_expression_to_file()` 创建标准 Live2D 表情配置文件
- **批量处理**：`write_expressions_to_files()` 支持选择性或全部写入
- **格式规范**：
```json
{
  "Type": "Live2D Expression",
  "Parameters": [
    {
      "Id": "ParamEyeLOpen",
      "Value": 0.8,
      "Blend": "Add"
    }
  ]
}
```

### 使用流程

#### 交互式测试
```bash
# 启动测试工具
python test_motion.py

# 表情测试命令
sa  # sad (悲伤)
an  # angry (愤怒)
ha  # happy (开心)
su  # surprised (惊讶)
th  # thinking (思考)
ne  # neutral (中性)

# 动作测试命令
m1-m9  # Idle动作组
m0     # TapBody动作

# 管理命令
records  # 显示表情参数记录
write    # 写入表情文件
```

#### 编程接口
```python
tester = Live2DMotionTester()

# 发送自定义参数表情
tester.send_expression("sad", text="悲伤表情", use_custom=True)

# 查看记录
tester.show_expression_records()

# 写入文件
tester.write_expression_to_file("sad", "expressions")
```

### 关键特性

#### 1. WebSocket 实时通信
- **双向通信**：与前端 Live2D 控制器建立 WebSocket 连接
- **消息格式**：
```json
// 表情消息
{
  "type": "expression",
  "emotion": "sad",
  "custom_params": {"ParamEyeLOpen": 0.8, ...},
  "timestamp": 1234567890
}

// 动作消息
{
  "type": "motion",
  "group": "Idle",
  "index": 0,
  "timestamp": 1234567890
}
```

#### 2. 参数映射系统
- **表情映射**：`expressions = {'sa': 'sad', 'an': 'angry', ...}`
- **参数定义**：`custom_params` 包含完整的参数调优数据
- **实时同步**：参数修改立即生效，无需重启

#### 3. AI 自动化支持
- **数据积累**：每次测试自动积累表情参数数据
- **标准化输出**：exp3.json 可直接用于生产环境
- **参数调优**：为 AI 学习算法提供训练数据
- **版本管理**：支持表情参数的版本控制和迭代优化

### 最佳实践

1. **参数调优流程**：
   - 先通过交互测试调整参数
   - 使用 `records` 查看当前参数配置
   - 通过 `write` 导出为配置文件
   - 在实际项目中加载使用

2. **AI 训练数据准备**：
   - 运行完整表情测试套件
   - 导出所有表情的 exp3.json 文件
   - 使用参数数据训练表情识别模型
   - 实现自动化表情生成

3. **生产环境部署**：
   - 将调优后的参数集成到 AI agent 表情系统
   - 支持动态参数调整和实时表情切换
   - 提供表情参数的持久化存储和管理

这个测试工具不仅是开发调试的利器，更是 AI 驱动的 Live2D 表情系统的核心基础设施，为未来的智能化虚拟角色交互奠定了技术基础。