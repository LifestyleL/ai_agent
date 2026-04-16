# Live2D 参数调试指南

## 概述

本文档介绍如何使用Live2D参数调试工具来观察和调整Live2D动画系统的参数计算、响应和动作效果。

**重要更新**: 已修复循环导入问题，现在可以独立运行调试工具！

## 文件说明

1. **`live2d_debug.py`** - 交互式调试器 (完整功能)
2. **`live2d_monitor.py`** - 实时监控器 (观察参数变化)
3. **`simple_live2d_debug.py`** - 简化调试器 (仅测试Animator)
4. **`test_debug_simple.py`** - 自动测试脚本
5. **`test_animator_only.py`** - Animator单元测试
6. **`DEBUG_LIVE2D.md`** - 本文档

## 可用工具

### 1. Live2D 交互式调试器 (`live2d_debug.py`)
- **功能**: 手动控制Live2D参数，测试预设动画，保存/加载配置
- **特点**: 交互式命令行界面，适合精细调整和测试
- **使用**: `python live2d_debug.py`

### 2. Live2D 实时监控器 (`live2d_monitor.py`)
- **功能**: 实时显示参数变化，统计信息，趋势分析
- **特点**: 自动刷新界面，适合观察系统行为
- **使用**: `python live2d_monitor.py`

## 快速开始

### 方案A: 单独运行调试器（推荐）
```bash
# 在 my_agent 目录下
python live2d_debug.py
```

这会自动启动Live2D管理器并开始监控。如果主系统已运行（WebSocket服务器在监听），调试器会自动连接并支持`direct`命令直接控制前端。您可以使用以下命令：

```
debug> status     # 显示当前参数
debug> ranges     # 显示参数范围
debug> set headX 0.5  # 设置头部X位置
debug> test nod   # 测试点头动画
debug> reset      # 重置控制
debug> help       # 显示所有命令
```

### 方案B: 与主系统同时运行

**重要**: 由于Live2DManager是单例模式，调试器会与主系统共享同一个实例。

1. **首先启动主系统**:
```bash
python main.py
```

2. **在另一个终端启动监控器**:
```bash
python live2d_monitor.py
```

这样您可以观察主系统运行时的参数变化。

### 方案C: 使用监控器观察主系统
```bash
# 终端1: 启动主系统
python main.py

# 终端2: 启动监控器（配置为慢速更新）
python live2d_monitor.py
# 输入监控间隔: 0.5
# 输入历史记录大小: 100
```

## 调试命令参考

### 基本命令
- `status` - 显示当前所有参数值
- `ranges` - 显示参数允许范围
- `reset` - 重置所有控制（恢复算法生成）
- `auto` - 切换到自动模式
- `manual` - 切换到手动模式

### 参数控制
- `set <参数名> <值>` - 设置单个参数（通过Live2DManager）
  ```
  set headX 0.5      # 头部向右转
  set mouth 0.8      # 嘴巴张开80%
  set eyeLeft 0.3    # 左眼半闭（值：-1~1，-1表示使用前端眨眼）
  ```
- `direct <参数名> <值>` - 直接发送参数到前端（通过WebSocket）
  ```
  direct headX 0.5   # 直接控制头部向右转
  direct mouth 0.8   # 直接控制嘴巴张开
  ```
  注意：`direct`命令需要WebSocket连接已建立（主系统已运行），且参数会立即发送到前端，绕过算法生成。

### 动画测试
- `test nod` - 点头动画
- `test shake` - 摇头动画  
- `test blink` - 眨眼测试
- `test speak` - 说话口型测试
- `test idle` - 切换到空闲模式
- `test thinking` - 切换到思考模式

### 批量操作
- `batch` - 进入批量设置模式
  ```
  batch> headX 0.5
  batch> headY -0.2
  batch> mouth 0.3
  batch> done
  ```

### 配置管理
- `save` - 保存当前配置到文件
- `load` - 从文件加载配置
- `mode <idle/thinking>` - 设置活动模式
- `activity <0~1>` - 设置活动度

## 参数说明

### 参数范围
| 参数 | 范围 | 说明 |
|------|------|------|
| eyeLeft/eyeRight | -1.0 ~ 1.0 | -1=前端眨眼, 0=闭眼, 1=睁眼 |
| mouth | 0.0 ~ 1.0 | 0=闭嘴, 1=最大张嘴 |
| headX | -10.0 ~ 10.0 | 头部左右转动（左负右正） |
| headY | -8.0 ~ 8.0 | 头部上下转动（下负上正） |
| headZ | -10.0 ~ 10.0 | 头部倾斜（已放宽） |
| bodyX | -4.0 ~ 4.0 | 身体左右摇摆（已放宽） |
| bodyY | -2.0 ~ 2.0 | 身体上下俯仰（已放宽） |
| bodyZ | -1.0 ~ 1.0 | 身体倾斜（已放宽） |
| hair | -3.0 ~ 3.0 | 头发飘动（已放宽） |
| PartArmA/PartArmB | 0.0 ~ 1.0 | 手臂显示度（0隐藏，1显示） |

### 模式说明
- **idle模式**: 低活动度（0.3），动作幅度小
- **thinking模式**: 高活动度（0.75），动作幅度大
- **活动度**: 直接影响算法生成的动作幅度，0~1可调

## 观察要点

### 1. 参数响应
- 设置参数后观察Live2D模型的实时响应
- 注意平滑过渡效果（前端有平滑处理）

### 2. 冲突检测
- TTS播放时嘴巴由viseme控制
- 外部设置与算法生成的优先级
- 眨眼控制协议（-1表示使用前端眨眼）

### 3. 性能观察
- 监控更新频率是否稳定（目标30fps）
- 参数计算是否有延迟
- 内存使用情况

## 常见问题

### Q1: 为什么设置参数后模型没反应？
- 检查参数范围是否正确
- 确认Live2D前端已连接（ws://localhost:8765）
- 检查是否有其他控制源覆盖（如TTS）

### Q2: 如何测试嘴巴与TTS的协调？
1. 使用 `set mouth 0.5` 设置嘴巴
2. 在主系统输入文本，触发TTS
3. 观察嘴巴是否切换为viseme控制
4. TTS结束后嘴巴是否恢复设置值

### Q3: 如何观察前端平滑效果？
1. 设置一个极端值 `set headX 8`
2. 立即重置 `reset`
3. 观察参数平滑回归的过程

### Q4: 调试器影响主系统怎么办？
- 使用 `reset` 命令恢复算法控制
- 或重启主系统

## 高级调试技巧

### 1. 参数趋势分析
使用监控器观察参数变化趋势，识别：
- 周期性模式（如呼吸、微小动作）
- 异常波动
- 响应延迟

### 2. 边界测试
测试参数边界情况：
```bash
set headX 10    # 最大右转
set headX -10   # 最大左转  
set mouth 1.0   # 最大张嘴
set mouth 0.0   # 完全闭嘴
```

### 3. 组合测试
测试多个参数的组合效果：
```bash
# 惊讶表情
set eyeLeft 1.0
set eyeRight 1.0
set mouth 0.7
set headY 5.0

# 沮丧表情  
set eyeLeft 0.5
set eyeRight 0.5
set mouth 0.2
set headY -3.0
set headZ 2.0
```

### 4. 与前端联动测试
1. 启动主系统 `python main.py`
2. 启动调试器 `python live2d_debug.py`
3. 在主系统输入文本对话
4. 在调试器观察参数如何响应TTS和情绪

## 故障排除

### 错误: "ModuleNotFoundError: No module named 'live2d'"
```bash
# 确保在 my_agent 目录下运行
cd my-react-app/my_agent
python live2d_debug.py
```

### 错误: "Live2D管理器初始化失败"
- 检查 `live2d_manager.py` 是否存在
- 检查Python路径设置

### 监控器显示异常字符
- 确保终端支持ANSI颜色代码
- 或修改监控器代码去掉颜色

### 参数设置无效
- 检查前端是否正常运行
- 检查WebSocket连接状态
- 尝试重启整个系统

## 代码修改建议

调试过程中如果发现参数范围、响应速度等问题，可以修改：

1. **参数范围**: `animator.py` 中的 `clamp()` 调用
2. **平滑系数**: 前端 `lappmodel.ts` 中的平滑系数
3. **活动度算法**: `animator.py` 中的 `get_activity_target()`
4. **控制优先级**: `animator.py` 中的 `compute_params()` 逻辑

## 联系支持

如遇到无法解决的问题，请提供：
1. 错误信息
2. 操作步骤
3. 相关配置文件
4. 期望效果与实际效果对比