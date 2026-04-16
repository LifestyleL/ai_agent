自驱动的完整生命周期
用一个用户真实的使用场景走一遍，假设用户打开页面后和 Qwen 聊了几句，然后去上厕所了。

Phase 1：人在的时候（Drive 被压制）
用户发消息
  ↓
[EventBus] USER_INPUT_RECEIVED
  ↓
[DriveModel] drive = max(0, drive - 0.5)   ← 一棍子打回原形
           engagement = min(1.0, engagement + 0.2)  ← 抬高投入度
  ↓
[Qwen] 正常聊天
这时候 Drive 被压制，Qwen 全心全意跟用户对话。

Phase 2：人走了（Drive 开始涨）
用户沉默...
  ↓
[DriveModel.tick()] 每秒执行一次：
  
  第10秒  drive=0.01, engagement=0.82    (还精神着)
  第30秒  drive=0.01, engagement=0.78    (engagement在自然衰减，drive还没开始涨)
  第60秒  drive=0.00, engagement=0.72    (idle超过60秒)
  第61秒  drive=0.005, engagement=0.71   ← 开始涨了！
  第70秒  drive=0.050, engagement=0.69
  第80秒  drive=0.100, engagement=0.67
  ...
  第180秒 drive=0.600, engagement=0.47   ← 觉得有点无聊了
  ...
  第240秒 drive=0.850, engagement=0.32   ← 临界点
  
  random.random() < 0.05  →  (95%的概率这次还不触发)
  
  第241秒 drive=0.855, engagement=0.31
  random.random() = 0.03  →  ✅ 触发！
  ↓
  drive = 0.0  ← 清空，防止连击
  ↓
[EventBus] SPONTANEOUS_ACTION_TRIGGERED
Phase 3：后台偷懒（Autonomous Worker 启动）
[Autonomous Worker] 收到事件
  ↓
从 personality.md 的 likes 列表里随机挑一个
  → 假设挑到了 "深海生物"
  ↓
构造搜索任务："关于深海生物的最新有趣知识，50字以内"
  ↓
调用 DeepSeek 去搜索（静默执行，不触发嘟囔）
  ↓
DeepSeek 搜索完毕，返回：
  "灯笼鱼不是靠眼睛发光，是靠皮肤里的共生细菌发光，
   而且它可以根据需要开关这个灯。"
  ↓
[EventBus] DISCOVERY_MADE
  data: {
    "topic": "深海生物",
    "content": "灯笼鱼不是靠眼睛发光..."
  }
Phase 4：分享欲（Qwen 把发现念出来）
这里有两种情况：

情况 A：用户还没回来 → Qwen 主动说话

[agent_driver] 收到 DISCOVERY_MADE
  ↓
构造 Prompt：
  "你刚才自己偷偷查了下深海生物。
   查到了：灯笼鱼不是靠眼睛发光...
   用你自己的话感叹或分享一句。"
  ↓
[Qwen] 回复："诶你知道吗，我刚才随便翻了翻，
  灯笼鱼发光居然是细菌干的...这也太离谱了吧"
  ↓
[EventBus] TTS_REQUESTED
  ↓
扬声器："诶你知道吗，我刚才随便翻了翻..."
用户从厕所回来，听到 Qwen 在自言自语。

情况 B：用户刚好发消息 → 顺便带一句

用户："我回来了"
  ↓
[agent_driver] handle_user_input
  内存里存着刚收到的 DISCOVERY_MADE 数据
  ↓
在 Prompt 里悄悄塞一句：
  "[你刚才查到了关于深海生物的有趣事情，
    如果合适可以顺便分享]"
  ↓
[Qwen] 回复："欢迎回来！对了，我刚才闲着没事翻了翻，
  你猜灯笼鱼发光是什么原理？不是它自己发的！是细菌！"
感觉就像你走开的时候它偷偷在玩手机，你回来它假装自然地跟你分享。

Phase 5：闭环（Drive 又被压制）
用户："哈哈真的假的"
  ↓
[EventBus] USER_INPUT_RECEIVED
  ↓
[DriveModel] drive = 0.0   ← 又被打回去了
  ↓
回到 Phase 1，正常聊天
如果用户又走了，整个循环重新开始。但下一次挑的喜好可能变成了"奇怪的哲学"或者"音乐"，不会重复。

一句话总结整条链路
没人理 → tick涨drive → 溢出触发事件 → 
Worker从likes挑话题 → DeepSeek静默搜索 → 
结果丢给Qwen → Qwen用人设语气念出来
全程 Qwen 不知道自己在"执行任务"，它只觉得"我突然想到一个有趣的事想说说"。这就是自驱动的灵魂——动机是内部的，不是外部指令驱动的。

####

Phase 3：后台偷懒（Autonomous Worker 启动）
这个触发机制是什么:

这个触发机制的核心，是一个名为 SPONTANEOUS_ACTION_TRIGGERED 的事件。

Autonomous Worker 本身没有任何主动权，它只是个纯粹的监听器，死死盯着事件总线，只有当它看到上面这个事件被丢出来时，它才会醒过来去干活。

那么这个事件是怎么被丢出来的呢？触发条件是“双重门槛”（时间 + 概率）：

门槛 1：时间积累（必须满足）
由 DriveModel.tick() 每秒执行一次来积攒。
用户只要不说话，超过 60 秒后，drive（自驱力/无聊度）的值就会以每次 +0.005 的速度慢慢往上涨。
它必须涨到超过 0.85。按数学算，这大概需要用户连续沉默 2.5 到 3 分钟左右。

门槛 2：随机概率（防止机械感）
就算 drive 涨到了 0.86（满足了门槛 1），tick() 里面还有一道锁：


if self.drive > 0.85 and random.random() < 0.05:
这意味着，在无聊度爆表的前提下，每一秒仍然只有 5% 的概率真正扣下扳机。

为什么搞得这么复杂（不直接设个3分钟定时器）？
如果直接设个“静默180秒就触发”，AI 的行为就会像机器：
*第一天：180秒，说话。第二天：180秒，说话。*

加入了 0.05 的随机概率后，触发时间变成了一个呈正态分布的模糊区间（大概在 3 分钟到 4 分钟之间随机发生）。这完美模拟了人类“走神”的非线性特征——有时候发呆半分钟就开始乱想，有时候能安静待五分钟。

触发瞬间的绝对安全机制（防连击）
一旦那 5% 的概率命中，事件被发布出去，代码会立刻执行：


self.drive = 0.0  # 清空内驱力
这就相当于把扳机弹簧拆了。保证了一次无聊只会触发一次“后台偷懒”，绝对不可能出现因为随机运气好，连续两秒触发两次，导致 AI 像机关枪一样连着查东西的情况。如果它想再查，必须再老老实实等 3 分钟重新积攒 drive。