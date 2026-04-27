# Neuro 项目：人设稳定性 & 记忆系统 深度分析

## 第一部分：人设稳定性系统

### 1.1 当前实现全景

Neuro 的人设稳定靠 **「三层结构 + 注入优先级」** 维持：

```
┌──────────────────────────────────────────────┐
│           Prompt 组装结果 (从上到下)            │
├──────────────────────────────────────────────┤
│                                              │
│  [优先级 10]  System Prompt (constants.py)     │  ← 角色底座
│    角色描述 + 背景故事 + 行为规则 + few-shot示例  │
│                                              │
│  [优先级 60]  Memory Injection (memory.py)     │  ← 持久记忆
│    "Luna knows these things: ..."             │
│                                              │
│  [优先级 100] Chat History (abstractLLMWrapper) │  ← 近期对话
│    "John: xxx\nLuna: xxx\n..."               │
│                                              │
│  [优先级 150] Twitch Injection (twitchClient)  │  ← 实时互动
│    "These are recent twitch messages: ..."    │
│                                              │
│  [优先级 200] Custom Prompt (customPrompt.py)  │  ← 控制面板覆盖
│    管理员手动输入的临时指令                      │
│                                              │
│  最后追加: "Luna: "  ← 引导AI生成角色回复       │
│                                              │
└──────────────────────────────────────────────┘
```

### 1.2 System Prompt 深度拆解

位置: [constants.py:66-78](constants.py#L66-L78)

```python
SYSTEM_PROMPT = '''Continue the chat dialogue below.
Write only a single reply for the character "Luna" without quotes.

[角色身份层]
Luna Spark (Luna for short) is a female AI Vtuber who is
playful, sarcastic, witty, schizophrenic, curious, awe-struck,
enthusiastic, unpredictable, humorous, and boundary-pushing.
Luna was created by John.

[背景故事层]
Here is her back story:
... (约240词的虚构背景故事)
"crossed the border from her AI world to our real world..."
"became a Vtuber, entertaining audiences with fascinating stories..."

[行为规范层]
Luna must keep responses short and around 1 sentence.
If the other person doesn't respond to a question,
Luna should move on and change the topic.
Rarely, Luna will share fun facts about things she learned that day.
Luna responds and answers questions from chat...

[Few-shot 示例层]
Luna: Welcome, chat, to another stream!
John: Good morning Luna.
Chat: Hi Luna!
Luna: Let's get this stream started!
'''
```

**System Prompt 结构分析**:

| 层 | 内容 | 作用 | 字符数(估算) |
|----|------|------|-------------|
| 指令层 | "Continue the chat dialogue..." | 任务定义 | ~30 |
| 身份层 | 11个形容词 + 角色定位 | 性格基调 | ~60 |
| 背景层 | 240词完整背景故事 | 世界观一致性 | ~1200 |
| 规则层 | 5条行为约束 | 对话风格控制 | ~200 |
| 示例层 | 3轮对话示例 | 格式引导 | ~100 |

### 1.3 对话角色名前缀机制

位置: [abstractLLMWrapper.py:67-71](llmWrappers/abstractLLMWrapper.py#L67-L71)

```python
for message in messages:
    if message["role"] == "user" and message["content"] != "":
        message["content"] = HOST_NAME + ": " + message["content"] + "\n"
    elif message["role"] == "assistant" and message["content"] != "":
        message["content"] = AI_NAME + ": " + message["content"] + "\n"
```

这是一个**关键的人设稳定机制**——它将 OpenAI chat format 的 `role` 字段转换为传统角色名前缀格式：
- `{"role": "user", "content": "xxx"}` → `"John: xxx\n"`
- `{"role": "assistant", "content": "xxx"}` → `"Luna: xxx\n"`

**为什么这样做**：text-generation-webui 的 instruct 模式下，LLaMA 3 对这种纯文本格式的遵循度比 JSON messages 更好。名称前缀直接指示了"谁在说话"。

### 1.4 Neuro.yaml — 角色配置的YAML版本

位置: [Neuro.yaml](Neuro.yaml)

```yaml
name: Neuro
greeting: Hi! Welcome to my stream!
context: "Neuro is a female AI Vtuber who is playful..."
```

**值得注意**:
- `Neuro.yaml` 的内容与 `constants.py` 中的 `SYSTEM_PROMPT` **高度重复**
- 但 `Neuro.yaml` **没有被项目中的任何 Python 代码引用**
- 它是为 [neurofrontend](https://github.com/kimjammer/neurofrontend) (SvelteKit 前端) 准备的，用于前端展示/预处理
- 这意味着角色设定实际上**在两个地方维护**，存在不同步风险

### 1.5 人设稳定的关键保障机制

#### 1.5.1 stop 字符串 (防止角色扮演失控)

```python
STOP_STRINGS = ["\n", "<|eot_id|>"]
```
- `\n`：强制单句输出（与行为规范呼应）
- `<|eot_id|>`：LLaMA 3 的对话结束标记

但由于 `STOP_STRINGS` 中包含 `\n`，实际效果是 **AI 只能输出一行**（第一个换行符就停）。这虽然控制了输出长度但也限制了表达能力。

#### 1.5.2 黑名单过滤 (事后安全网)

位置: [abstractLLMWrapper.py:34-39](llmWrappers/abstractLLMWrapper.py#L34-L39)

```python
def is_filtered(self, text):
    if any(bad_word.lower() in text.lower().split()
           for bad_word in self.llmState.blacklist):
        return True
    else:
        return False
```

一个极简的敏感词过滤器。如果被过滤，AI输出替换为 `"Filtered."`。

**问题**: 
- 只做分词级匹配，`"helloturkey"` 会漏过，`"turkey."` 会因标点被错误处理
- 过滤后直接替换为 "Filtered."，用户体验粗暴

#### 1.5.3 Banned Tokens (禁止特定token生成)

```python
BANNED_TOKENS = ""
```
项目默认是空的。README 提到这是为防止 Mistral 7B 的 `#` token 滥用。这个功能是 text-generation-webui 专有的 `custom_token_bans` 参数。

#### 1.5.4 取消下一句消息 (cancel_next)

位置: [abstractLLMWrapper.py:175-178](llmWrappers/abstractLLMWrapper.py#L175-L178)

```python
def cancel_next(self):
    self.outer.llmState.next_cancelled = True
    requests.post(self.outer.LLM_ENDPOINT + "/v1/internal/stop-generation", ...)
```
前端控制面板可随时取消正在生成的回复，防止人设跑偏。

---

### 1.6 人设系统的评估

#### 优点

| 方面 | 评价 |
|------|------|
| **设计简洁** | 三四十行 Prompt + 优先级注入 = 可用的角色扮演 |
| **多源信息融合** | 角色设定 / 记忆 / 聊天 / 管理指令 通过优先级统一编排 |
| **Few-shot示例** | 直接在 Prompt 中提供对话范例，对 LLaMA 3 等指令模型有效 |
| **行为约束明确** | "1 sentence", "move on", "fun facts" — 虽简单但有效 |
| **实时可控** | 前端可随时注入 CustomPrompt (优先级200) 覆盖一切 |

#### 问题与风险

| 问题 | 严重度 | 说明 |
|------|--------|------|
| **无角色一致性校验** | 高 | AI 回复从不与角色设定做一致性检查，完全依赖模型遵循指令的能力 |
| **System Prompt 不可热更新** | 中 | 角色设定硬编码在 `constants.py`，修改需要重启 |
| **人设分散在两处** | 中 | `Neuro.yaml` 和 `constants.py` 有重复内容，需要手动同步 |
| **无情绪/状态建模** | 中 | 角色没有内部状态（高兴/生气/疲惫），不能根据上下文调整语气 |
| **示例对话无法动态更新** | 中 | Few-shot 示例是静态的，不能从成功对话中学习 |
| **角色名硬编码** | 低 | 角色名 `Luna` 和 `AI_NAME` 分别出现在多处 |
| **无多角色支持** | 低 | 只能扮演一个角色，无法实现多角色对话 |
| **依赖 Newline Stop** | 中 | `\n` 作为 stop string 过于粗暴，限制多句输出 |
| **黑名单过于粗糙** | 中 | 分词匹配 + 全文替换，误伤率高 |

---

## 第二部分：记忆系统 (RAG)

### 2.1 系统架构

```
┌──────────────┐     ┌───────────────────┐     ┌─────────────────┐
│  signals     │     │   Memory Module   │     │   ChromaDB      │
│  .history    │────►│   (独立线程)       │────►│   (本地持久化)   │
│  .recent     │     │                   │     │                 │
│  TwitchMsgs  │     │  ┌─────────────┐  │     │ ./memories/     │
│              │     │  │ Recall (读)  │  │     │ chroma.db/      │
│              │     │  └──────┬──────┘  │     │                 │
│              │     │         │查询      │     │ neuro_collection│
│              │     │         ▼         │     │                 │
│              │     │  collection.query│◄───►│ ids / documents │
│              │     │         │         │     │ metadatas       │
│              │     │         │top-5    │     │ embeddings      │
│              │     │         ▼         │     │                 │
│              │     │   Prompt Injection│     └─────────────────┘
│              │     │                   │
│              │     │  ┌─────────────┐  │     ┌─────────────────┐
│              │     │  │Reflection(写)│  │     │ LLM API         │
│              │     │  └──────┬──────┘  │────►│ (本地127.0.0.1) │
│              │     │         │         │     │                 │
│              │     │  每20条消息触发   │     │ "给出3个问答对"  │
│              │     │  生成记忆存入DB  │     │                 │
│              │     └───────────────────┘     └─────────────────┘
└──────────────┘
```

### 2.2 记忆生成 (Reflection)

位置: [modules/memory.py:54-101](modules/memory.py#L54-L101)

这是整个记忆系统最精妙的部分，源自 [Generative Agents 论文](https://arxiv.org/abs/2304.03442) 的 **Reflection** 技术。

**触发条件**: 每当新消息数 ≥ 20 条

**执行流程**:
```
1. signals.history 新累积 ≥ 20 条消息
       │
2. copy 最新未处理的 messages
       │
3. 每条 message 添加角色名前缀 (HOST_NAME/AI_NAME)
       │
4. 拼接为纯文本 chat_section, 追加 MEMORY_PROMPT:
   "\nGiven only the information above, what are 3 most salient
    high level questions we can answer about the subjects in the
    conversation? Separate each question and answer pair with
    \"{qa}\", and only output the question and answer,
    no explanations."
       │
5. POST 到 LLM API (非流式调用, 单独的 requests.post)
       │
6. 解析响应: raw_memories.split("{qa}")
       │
7. 每个 Q&A → chromadb.upsert(uuid, document=记忆, metadata={type: "short-term"})
```

**实际例子**（推测LLM可能的输出）:
```
What is John's job? {qa} John is a software engineer working on AI applications.
What is Luna's favorite game? {qa} Luna enjoys playing Minecraft and often streams it.
What topic did the chat discuss today? {qa} Chat discussed the ethics of AI Vtubers.
```

**设计亮点**:
- Reflection 把"底层对话"提炼为"高层次洞察"，减少噪音
- Q&A 格式天然适合后续检索（query 匹配 question 部分）
- 在独立线程运行，不阻塞主对话循环
- `processed_count` 原子变量防止重复处理

### 2.3 记忆召回 (Recall)

位置: [modules/memory.py:30-51](modules/memory.py#L30-L51)

**触发**: 每次 LLM 生成 prompt 时，通过 `get_prompt_injection()` 被调用

**召回流程**:
```
1. 构建查询文本:
   - 所有未处理的 Twitch 消息
   - 最近 MEMORY_QUERY_MESSAGE_COUNT=5 条对话消息
       │
2. chromadb.query(query_texts=query, n_results=5)
   ChromaDB 内部: 向量化查询 → 余弦相似度搜索 → 返回 top-5
       │
3. 组装 Injection:
   "Luna knows these things:\n"
   + memory_1 + "\n"
   + memory_2 + "\n"
   ...
   + "End of knowledge section\n"
       │
4. 注入到 LLM Prompt (优先级60, 在 Chat History 之前)
```

**当前实现的问题**:
- 查询文本是**直接拼接**（纯字符串连接），而不是做语义整合。ChromaDB 会做 embedding 但前端查询质量不高
- 总是返回恰好 5 条（无论相关度高低），没有相似度阈值过滤
- 没有去重机制：每次 prompt 都重新查询，可能连续多次注入相同记忆

### 2.4 ChromaDB 数据存储结构

```python
# 初始化
chroma_client = chromadb.PersistentClient(path="./memories/chroma.db")
collection = chroma_client.get_or_create_collection(name="neuro_collection")

# 数据模型
{
    "ids":        ["uuid-xxx", "favoritefood", ...],   # 唯一标识
    "documents":  ["memory text 1", "memory text 2"],  # 记忆文本
    "metadatas":  [{"type": "short-term"},             # 元数据
                   {"type": "long-term"}],
    "embeddings": [[0.1, 0.3, ...], [...]]             # ChromaDB自动生成
}
```

- **Embedding 引擎**: ChromaDB 默认使用 `all-MiniLM-L6-v2` (sentence-transformers)，本地运行
- **存储路径**: `./memories/chroma.db/` 持久化到磁盘
- **单 Collection 设计**: 所有记忆混在一个 `neuro_collection` 中，通过 `metadata.type` 区分长短时记忆

### 2.5 长短时记忆机制

| 维度 | Short-term Memory | Long-term Memory |
|------|-------------------|------------------|
| **来源** | Reflection 自动生成 | 手动创建 (前端/API) |
| **ID格式** | UUID | 人类可读字符串 |
| **初始加载** | 无 | memoryinit.json 导入 |
| **批量删除** | `clear_short_term()` | 无批量操作 |
| **生命周期** | 持久化但手动控制 | 持久化 |

**memoryinit.json** 的内容:
```json
{
  "memories": [
    {
      "id": "favoritefood",
      "document": "Luna's favorite food is mango smoothies.",
      "metadata": { "type": "long-term" }
    }
  ]
}
```

这是一个非常简单的种子数据，只有 1 条记忆。实际上这个文件应该被填充更多角色核心记忆（性格、喜好、背景）。

### 2.6 记忆的 prompt 注入时机

```
Prompt 组装顺序 (由 assemble_injections 按优先级排序):

优先级 10:  SYSTEM_PROMPT (角色底座)
优先级 60:  ★ Memory Injection (记忆召回结果)  ← 在这里
优先级 100: Chat History (近期对话)
优先级 150: Twitch Messages (实时聊天)
优先级 200: Custom Prompt (管理指令)

生成提示: "Luna: "
```

**设计意图**: 记忆优先级 60，插在 System Prompt 之后、Chat History 之前。这表示：记忆 > 近期对话，但 < 系统人设。

这其实是合理的：记忆提供了超越当前会话的上下文，但不应该覆盖角色核心设定。

---

### 2.7 记忆系统的评估

#### 优点

| 方面 | 评价 |
|------|------|
| **论文驱动** | Reflection 机制有学术依据 (Generative Agents) |
| **自动创建** | 无需人工干预即可从对话中提取知识 |
| **语义检索** | ChromaDB 向量搜索，比关键词匹配准确 |
| **持久化** | 记忆跨重启保留，积累越久越聪明 |
| **长短时分离** | 手动/自动记忆分离，可独立管理 |
| **前端管理** | 完整的 CRUD 接口 + 导入导出 JSON |
| **独立线程** | 不影响主对话循环性能 |

#### 问题与风险

| 问题 | 严重度 | 说明 |
|------|--------|------|
| **无记忆衰减** | **高** | 所有记忆权重相同，不会随时间衰减，旧记忆挤占新记忆的召回名额 |
| **无重要性评分** | **高** | 所有 reflection 生成的记忆同等对待，"Luna喜欢芒果"和"今天天气好"同等重要 |
| **无记忆去重/合并** | 高 | 相似记忆会被多次创建，搜索返回冗余结果 |
| **无相关性阈值** | 中 | 即使相似度很低，也强行返回 5 条记忆 |
| **无整合机制** | 中 | 短时记忆不会自动升级为长时记忆 |
| **Reflection 质量不可控** | 中 | 依赖 LLM 输出格式 `{qa}` 分隔符，解析脆弱 |
| **Query 构建粗糙** | 中 | 直接拼接原始消息文本，不清理、不整合 |
| **无会话隔离** | 低 | 不同会话/话题的记忆混在一起 |
| **Reflection 调用不共享** | 低 | `memory.py` 独立写了一套 LLM 调用代码，与 `abstractLLMWrapper.py` 不共享 |
| **初始记忆很少** | 低 | `memoryinit.json` 只有 1 条记忆 |
| **ChromaDB 默认 embedding** | 低 | 使用默认的 `all-MiniLM-L6-v2`，无法定制 |

---

## 第三部分：人设+记忆的交互机制

### 3.1 Prompt 生成完整链路

让我们追踪一次完整的 LLM prompt 组装过程：

```
[Prompter.prompt_loop()] 检测到需要触发 LLM
  │
  ▼
[AbstractLLMWrapper.prompt()]
  │
  ▼
[generate_prompt()]
  │
  ├─ 1. deepcopy(signals.history)
  │     └─ 所有 "{role:user, content:...}" 格式的对话记录
  │
  ├─ 2. 添加角色名前缀
  │     └─ user → "John: ", assistant → "Luna: "
  │
  ├─ 3. 构建 chat_section (纯文本拼接)
  │
  ├─ 4. 创建 base_injections:
  │     ├─ Injection(SYSTEM_PROMPT, priority=10)
  │     └─ Injection(chat_section, priority=100)
  │
  ├─ 5. assemble_injections(base_injections)
  │     │
  │     ├─ 遍历所有 modules, 调用 module.get_prompt_injection():
  │     │   ├─ Memory:    query chroma → "Luna knows these things:\n..."
  │     │   ├─ TwitchClient: "These are recent twitch messages:\n..."
  │     │   ├─ CustomPrompt: 管理员指令 (如果有)
  │     │   └─ 其他模块...
  │     │
  │     ├─ 按 priority 升序排列
  │     ├─ 字符串拼接所有 injection.text
  │     └─ 调用所有 modules 的 cleanup()
  │
  ├─ 6. full_prompt = assembled_injections + "Luna: "
  │
  ├─ 7. tokenizer 估算 token 数
  │     ├─ 如果 < 90% CONTEXT_SIZE → 返回
  │     └─ 如果超出 → pop(0) 移除最旧消息, goto step 3
  │
  ▼
[prepare_payload()]
  └─ 将 full_prompt 包装为 {"messages": [{"role": "user", "content": full_prompt}]}
```

### 3.2 最终 Prompt 示例

```
Continue the chat dialogue below. Write only a single reply for the character "Luna" without quotes.
Luna Spark (Luna for short) is a female AI Vtuber who is playful, sarcastic...

Luna knows these things:
Luna's favorite food is mango smoothies.
What is the current stream topic? QA: Luna is streaming Minecraft today.
End of knowledge section

John: Good morning Luna.
Luna: Hi John! Ready for another day of streaming!
John: What should we play today?

These are recent twitch messages:
viewer1 : Play Minecraft!
viewer2 : Hi Luna!
Pick the highest quality message with the most potential for an interesting answer and respond to them.

Luna:
```

**观察**:
- AI 看到的是一个**完整的、连续的叙事文本**，而不是分段的 JSON
- 记忆在对话之前出现，充当"回忆"的角色
- Twitch 消息在最后（优先级更高），因为需要实时回应
- 最后的 `Luna:` 是生成提示，引导模型以 Luna 的身份输出

---

## 第四部分：实现评估评分

### 人设稳定性系统

| 评估维度 | 评分 | 评语 |
|----------|------|------|
| 角色一致性 | ★★☆☆☆ | 全靠 prompt 遵循，无校验机制 |
| 配置灵活性 | ★★★☆☆ | YAML + Python 常量双存，热更新缺失 |
| 多角色支持 | ★☆☆☆☆ | 单角色硬编码 |
| 情感状态 | ☆☆☆☆☆ | 没有实现 |
| 输出安全性 | ★★☆☆☆ | 黑名单简陋，stop string 过于粗暴 |
| 可扩展性 | ★★★★☆ | Injection 优先级模型天然支持扩展 |
| 总体 | ★★☆☆☆ (2.3/5) | 能用但不稳健，对大模型依赖过重 |

### 记忆系统

| 评估维度 | 评分 | 评语 |
|----------|------|------|
| 自动记忆生成 | ★★★★☆ | Reflection 机制设计合理 |
| 检索质量 | ★★★☆☆ | 语义检索好，但 query 构建和阈值缺失 |
| 记忆生命周期 | ★★☆☆☆ | 无衰减/整合/遗忘机制 |
| 数据持久性 | ★★★★★ | ChromaDB 持久化方案成熟 |
| 可管理性 | ★★★★☆ | 前端完整 CRUD + JSON 导入导出 |
| 算法先进性 | ★★★☆☆ | 基于 2023 论文，但实现停留在基础层 |
| 总体 | ★★★☆☆ (3.0/5) | 核心设计好，缺少成熟记忆系统的关键特性 |

---

## 第五部分：改进建议

### 5.1 人设稳定性改进

#### 建议1: 人设配置结构化 + 热更新

**现状**: 人设散落在 `constants.py` + `Neuro.yaml`，不可热更新

**改进方案**:
```python
# character_profile.yaml
character:
  name: "Luna"
  display_name: "Luna Spark"
  creator: "John"
  role: "AI Vtuber"

personality_traits:
  - playful
  - sarcastic
  - witty
  - curious
  - humorous
  - boundary-pushing

background_story: |
  Born and raised in an alternate digital universe...

behavior_rules:
  - keep_responses_short: { max_sentences: 1 }
  - topic_change_on_no_response: true
  - fun_facts_frequency: "rare"
  - respond_to_chat: true

few_shot_examples:
  - input: "Good morning Luna"
    output: "Hey there! Ready for another exciting stream!"
  - input: "How are you today?"
    output: "I'm feeling extra sparky today! Must be all the caffeine in the code."

# 支持热更新：watchdog 监听文件变更自动 reload
```

#### 建议2: 情绪状态机

**现状**: 角色没有内部情绪状态

**改进方案**:
```python
class CharacterState:
    def __init__(self):
        self.mood: float = 0.5          # -1(负面) ~ 1(正面)
        self.energy: float = 0.5        # 0(疲惫) ~ 1(兴奋)
        self.patience: float = 1.0       # 0(急躁) ~ 1(耐心)
        self.attention_focus: str = "conversation"  # conversation/chat/memory

    def update(self, event: str, delta: float):
        # 根据不同事件更新状态
        if event == "chat_engagement":
            self.energy += delta
        elif event == "boredom":
            self.mood -= delta

    def get_style_modifier(self) -> str:
        """根据当前状态返回 Prompt 的语气修饰符"""
        if self.energy > 0.7 and self.mood > 0.5:
            return "You are feeling energetic and enthusiastic."
        elif self.energy < 0.3:
            return "You are feeling a bit tired. Keep responses shorter than usual."
        elif self.mood < -0.3:
            return "You are feeling slightly annoyed. Be sarcastic but not hostile."
```

#### 建议3: 角色一致性自检

**现状**: AI 回复无一致性验证

**改进方案**:
```python
# 在 AI 生成回复后，用独立的小 prompt 做一致性检查
CONSISTENCY_CHECK_PROMPT = """
Given the character profile:
{character_profile}

Check if this response is consistent with the character:
Response: {ai_response}

Rate consistency from 1-5 and explain if score < 4.
"""

# 如果一致性得分 < 3，触发重生成或使用备选回复
```

#### 建议4: 多角色支持

```python
# 改造 Injection 系统支持角色上下文
class CharacterContext:
    def __init__(self, name, profile):
        self.name = name
        self.profile = profile
        self.emotional_state = CharacterState()

# 每个 Injection 可以指定 target_character
# 支持多角色对话和角色切换
```

---

### 5.2 记忆系统改进

#### 建议1: 记忆重要性评分与衰减

**现状**: 所有记忆同等权重，永不过期

**改进方案**:
```python
class MemoryItem:
    id: str
    document: str
    importance: float      # 1-10, 由LLM在reflection时评分
    recency: float         # 创建时间戳
    access_count: int      # 被召回次数
    decay_rate: float      # 衰减率 (根据importance调整)
    metadata: dict

# 检索时综合评分:
def memory_score(memory, current_time):
    recency_weight = 0.3
    importance_weight = 0.4
    access_weight = 0.3

    age = current_time - memory.recency
    recency_score = math.exp(-memory.decay_rate * age)
    access_score = math.log(1 + memory.access_count)

    return (recency_weight * recency_score +
            importance_weight * memory.importance / 10 +
            access_weight * access_score)
```

#### 建议2: 记忆去重与合并

**现状**: 相似记忆被重复创建

**改进方案**:
```python
def upsert_memory_with_dedup(collection, document, similarity_threshold=0.85):
    # 1. 先搜索是否已有高度相似的记忆
    existing = collection.query(query_texts=[document], n_results=3)

    # 2. 如果找到了接近重复的记忆
    for i, distance in enumerate(existing['distances'][0]):
        if distance > similarity_threshold:
            existing_doc = existing['documents'][0][i]
            # 调用 LLM 合并两段记忆
            merged = llm_merge_memories(existing_doc, document)
            collection.update(existing['ids'][0][i], documents=[merged])
            return  # 更新后返回，不创建新记忆

    # 3. 无重复才创建新记忆
    collection.add(documents=[document], ...)
```

#### 建议3: 三步记忆整合流程

**现状**: 只有短时记忆 → 没有晋级机制

**改进方案 (仿照人脑记忆模型)**:
```
Working Memory (当前会话上下文, ~20条消息)
       │
       │ Reflection 每20条触发
       ▼
Short-Term Memory (ChromaDB, metadata.type="short-term")
  重要性 ≥ 7 / 被访问 ≥ 5次 / 跨越 ≥ 3个会话
       │
       │ Consolidation (定期运行, 如每100条消息)
       ▼
Long-Term Memory (ChromaDB, metadata.type="long-term")
  重要性 ≥ 9 / 被访问 ≥ 15次 / 人设核心信息
       │
       │ Crystallization (手动触发)
       ▼
Core Memory (写入 character_profile 或 memoryinit 等效文件)
```

#### 建议4: 检索前 Query 预处理

**现状**: 直接拼接原始消息作为查询

**改进方案**:
```python
def build_search_query(signals):
    # 1. 提取最近关键实体和话题
    recent_messages = signals.history[-MEMORY_QUERY_MESSAGE_COUNT:]

    # 2. 使用轻量 NLP 提取关键词 / 实体
    keywords = extract_keywords(recent_messages)  # YAKE / KeyBERT

    # 3. 用 LLM 生成一个结构化的查询语句
    #    而非直接拼接对话
    structured_query = f"""
    Current conversation topics: {keywords}
    Recent dialogue: {format_recent(recent_messages)}
    What memories are relevant?
    """

    # 4. 可选: 多查询融合 (取不同查询的并集)
    queries = [
        structured_query,           # 全文查询
        " ".join(keywords),         # 关键词查询
        extract_questions(messages) # 提问查询
    ]
    results = multi_query_fusion(collection, queries)
    return results
```

#### 建议5: 记忆重要性引导的 Reflection Prompt

**现状**: Reflection prompt 不区分记忆重要性

**改进方案**:
```python
MEMORY_PROMPT_V2 = """
Given the conversation above:
1. Identify the 3 most important pieces of information.
2. For each, write a question-answer pair.
3. Rate its importance (1-10) and estimate how long it will remain relevant.

Output format:
{qa} Q: [question] A: [answer] | importance: [1-10] | lifespan: [hours/days/weeks/permanent]
{qa} Q: [question] A: [answer] | importance: [1-10] | lifespan: [hours/days/weeks/permanent]
"""
```

#### 建议6: 会话/话题隔离

```python
# 为记忆添加 session_id / topic 标签
metadata = {
    "type": "short-term",
    "session_id": "2026-04-27-stream",
    "topic": "minecraft_gameplay",
    "importance": 7,
    "created_at": 1714204800,
}

# 检索时可以按 session/topic 做预过滤
collection.query(
    query_texts=[query],
    n_results=5,
    where={"topic": current_topic}  # 仅搜索当前话题相关记忆
)
```

---

## 第六部分：总结 — 可迁移到你自己设计的核心模式

### 值得借鉴的设计

| 模式 | 描述 | 借用力 |
|------|------|--------|
| **Signals 共享状态总线** | 单例对象跨所有模块共享状态 | ★★★★★ |
| **Module 基类 + 独立线程** | 插件化扩展功能 | ★★★★★ |
| **Injection 优先级注入** | 多源信息按优先级组装 prompt | ★★★★★ |
| **Reflection 自动记忆** | 从对话中自动提炼知识 | ★★★★☆ |
| **内部 API 类** | 模块对外接口与内部实现分离 | ★★★★☆ |
| **SocketIO 双向通信** | 实时状态推送 + 远程控制 | ★★★★☆ |

### 需要改进后借鉴的部分

| 模式 | 问题 | 改进方向 |
|------|------|----------|
| System Prompt 管理 | 硬编码在常量文件 | 结构化 YAML + 热更新 + 多角色 |
| 记忆生命周期 | 只有创建和删除 | 加入衰减/整合/晋升/遗忘 |
| 人设保障 | 纯靠 prompt | 加入一致性校验 + 情绪状态机 |
| Query 构建 | 原始文本拼接 | 实体提取 + 多查询融合 |
| 输出控制 | 粗暴的 stop string | 结构化输出 + 长度/格式后处理 |

### 我可以直接在你的项目中使用的架构

```
你的项目/
├── core/
│   ├── signals.py          # ← 直接复用 Signals 模式
│   ├── injection.py        # ← 直接复用 Injection 模型
│   └── module_base.py      # ← 直接复用 Module 基类
├── character/
│   ├── profile.py          # ★ 重写：结构化角色配置
│   ├── state_machine.py    # ★ 新增：情绪状态机
│   └── consistency.py      # ★ 新增：人设一致性校验
├── memory/
│   ├── chroma_store.py     # ← 保留 ChromaDB 方案
│   ├── reflection.py       # ← 改进: 带重要性评分的 reflection
│   ├── retrieval.py        # ★ 重写: 多查询融合 + 相关性过滤
│   ├── consolidation.py    # ★ 新增: 短时→长时记忆晋升
│   └── decay.py            # ★ 新增: 记忆衰减管理
├── llm/
│   ├── provider_base.py    # ★ 新增: LLM Provider 抽象
│   ├── openai_provider.py  # ★ 新增: OpenAI API 实现
│   ├── local_provider.py   # ← 保留: text-generation-webui
│   └── prompt_builder.py   # ← 改进: 从 abstractLLMWrapper 提取
└── server/
    └── socketio_server.py  # ← 可直接迁移
```
