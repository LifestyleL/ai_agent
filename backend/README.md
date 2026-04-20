# AI Agent 后端项目

## 项目结构

```
backend/
├── core/                    # 核心模块
│   ├── emotion_engine.py   # 情绪缓动算法 (0.7旧+0.3新, 类型切换阈值≥2, 自然衰减*0.9)
│   ├── memory_core.py      # 记忆系统核心 (短期RAM驻留, 长期自动打标, 情绪联动)
│   ├── vector_memory.py    # 向量记忆管理 (FAISS索引, 条件触发检索门控)
│   ├── agent/              # Agent 核心组件
│   ├── event/              # 事件处理系统
│   ├── llm/                # LLM 交互层
│   └── memory/             # 记忆存储目录
├── services/               # 服务模块
├── utils/                  # 工具函数
├── tests/                  # 测试套件
│   └── unit/               # 单元测试
│       └── test_memory_closed_loop.py  # 记忆系统闭环冒烟测试
├── deprecated/             # 技术债归档 (2026-04)
├── agent_memory/           # 记忆存储根目录 (JSON三层架构)
│   ├── short_term.json     # 短期记忆 (RAM驻留+异步持久化)
│   ├── long_term/          # 长期记忆 (按日归档)
│   └── vector_db/          # 向量记忆 (FAISS索引+映射文件)
├── config.py               # 配置入口 (YAML分层配置)
└── config/                 # YAML配置目录
```

## 记忆系统架构 (2026-04重构)

### 三层JSON存储架构

1. **短期记忆** (`short_term.json`)
   - RAM驻留缓冲区 (最大15轮对话)
   - 异步持久化 (`asyncio.to_thread`)
   - 主链路零阻塞设计

2. **长期记忆** (`long_term/YYYY-MM-DD.json`)
   - 按日归档，自动打标入库
   - 入库条件: `长度>25` OR `情绪强度≥5` OR `场景类型==B`
   - LLM自动打标 (summary, emotion_type, scene_type, importance)

3. **向量记忆** (`vector_db/`)
   - FAISS索引 + `vector_memory.json` 映射
   - 条件触发检索门控: `情绪强度≥5` AND `场景类型==B`
   - 重要性过滤: `importance ≥ 5` 才存入向量库

### 情绪缓动算法 (`EmotionEngine`)

- **强度平滑**: `新强度 = (0.7 * 旧强度 + 0.3 * 新强度) * 0.9`
- **类型切换阈值**: 情绪类型差值 `≥2` 才切换
- **自然衰减**: 每次更新强度乘以 `0.9`

### 关键文件索引

| 文件 | 说明 | 最近更新 |
|------|------|----------|
| `core/emotion_engine.py` | 情绪引擎核心算法 | 2026-04 |
| `core/memory_core.py` | 记忆系统主类 | 2026-04 |
| `core/vector_memory.py` | 向量记忆管理 | 2026-04 |
| `core/agent/agent_driver.py` | Agent主链路 | 2026-04 |
| `tests/unit/test_memory_closed_loop.py` | 闭环冒烟测试 | 2026-04 |
| `deprecated/` | 旧版Markdown记忆系统归档 | 2026-04 |

## 配置系统

采用YAML分层配置 (`config/default.yaml`, `config/development.yaml`, `config/production.yaml`):

```yaml
websocket:
  port: 8765
  enable_jsonrpc: true

ai:
  deepseek:
    api_key: ${DEEPSEEK_API_KEY}
    model: deepseek-chat
  qwen:
    api_key: ${QWEN_API_KEY}
    model: qwen-max

memory:
  short_term_max_tokens: 4096
```

环境变量优先级: `production.yaml` > `development.yaml` > `default.yaml`

## 测试验证

```bash
# 运行记忆系统闭环测试
cd backend
python tests/unit/test_memory_closed_loop.py

# 预期输出: 5/5 通过
```

## 技术债归档 (2026-04)

- `deprecated/memory_core_legacy.py` - 旧版记忆核心 (Markdown文件存储)
- `deprecated/memories.md` - 旧版长期记忆
- `deprecated/short_memories.md` - 旧版短期记忆  
- `deprecated/surfing_memories.md` - 旧版冲浪记忆

**注意**: 所有旧版Markdown记忆文件已于2026-04被JSON三层架构替代，仅作数据冷备份保留。

## 下一步重构

- [ ] 清理兼容性静态方法 (`MemoryCore.append_to_file`, `MemoryCore.load_files`)
- [ ] 迁移旧版调用到新记忆实例
- [ ] 实现深度记忆情感联想触发
- [ ] 优化向量检索性能

---

*最后更新: 2026-04-18*