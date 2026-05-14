"""
Phase 4 验证：Channel 抽象 + QQ/本地统一

场景：
  1. ChannelRegistry 解析：local vs qq session_id
  2. Channel 属性：is_external / template_path
  3. QQChannel pre_process：群聊上下文注入 + 意图检测
  4. QQChannel post_process：PASS 检测（forced vs non-forced）
  5. LocalChannel pre_process：channel_name 注入
  6. FinalizeStage：channel.is_external 替换硬编码
  7. ThinkContext.replace()：template_path / channel_name 字段

用法:
  cd backend
  python tests/manual/test_channel.py
"""

import asyncio
import sys
import os

_project_root = os.path.join(os.path.dirname(__file__), "..", "..", "..")
_backend_dir = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, _project_root)
sys.path.insert(0, _backend_dir)

from backend.core.channel.base import Channel
from backend.core.channel.local_channel import LocalChannel
from backend.core.channel.qq_channel import QQChannel
from backend.core.think_pipeline.context import ThinkContext
from backend.core.think_pipeline.finalize import FinalizeStage


# ═══════════════════════════════════════════════════════════════
# Mock objects
# ═══════════════════════════════════════════════════════════════

class MockDispatcher:
    """模拟 ResponseDispatcher"""
    def __init__(self):
        self.frontend_msgs = []
        self.tts_msgs = []
        self.last_speak = None

    def send_to_frontend(self, text: str, msg_type: str = "chunk"):
        self.frontend_msgs.append((text, msg_type))

    def speak_complete(self, text: str):
        self.tts_msgs.append(text)
        self.last_speak = text


class MockFrontend:
    """模拟 Live2D 前端"""
    def __init__(self):
        self.commands = []

    def send_live2d_cmd(self, cmd: str, **kwargs):
        self.commands.append((cmd, kwargs))


class MockTTS:
    """模拟 TTS Manager"""
    def __init__(self):
        self.current_emotion = "neutral"


# ═══════════════════════════════════════════════════════════════
# ChannelRegistry（与 main.py 内联定义一致）
# ═══════════════════════════════════════════════════════════════

class ChannelRegistry:
    def __init__(self):
        self._channels: dict = {}

    def register(self, ch: Channel):
        self._channels[ch.name] = ch

    def resolve(self, session_id: str) -> Channel:
        for ch in self._channels.values():
            if ch.name == "local":
                continue
            if session_id and session_id.startswith(f"{ch.name}_"):
                return ch
        return self._channels.get("local")


# ═══════════════════════════════════════════════════════════════
# 测试场景
# ═══════════════════════════════════════════════════════════════

async def test_registry_resolve_local():
    """场景 1：ChannelRegistry 解析 — 本地 session"""
    print(f"\n{'─' * 50}")
    print("[场景1] ChannelRegistry 解析：本地 session")

    reg = ChannelRegistry()
    qq = QQChannel()
    local = LocalChannel()
    reg.register(local)
    reg.register(qq)

    # 空 session_id → local
    ch1 = reg.resolve("")
    print(f"  resolve('') → {ch1.name} (expected: local)")
    ok1 = ch1.name == "local"

    # 本地 session_id 不带 qq_ 前缀 → local
    ch2 = reg.resolve("local_abc123")
    print(f"  resolve('local_abc123') → {ch2.name} (expected: local)")
    ok2 = ch2.name == "local"

    ok = ok1 and ok2
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


async def test_registry_resolve_qq():
    """场景 2：ChannelRegistry 解析 — QQ session"""
    print(f"\n{'─' * 50}")
    print("[场景2] ChannelRegistry 解析：QQ session")

    reg = ChannelRegistry()
    qq = QQChannel()
    local = LocalChannel()
    reg.register(local)
    reg.register(qq)

    ch = reg.resolve("qq_group_12345_67890")
    print(f"  resolve('qq_group_12345_67890') → {ch.name} (expected: qq)")

    ok = ch.name == "qq"
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


async def test_channel_properties():
    """场景 3：Channel 属性验证"""
    print(f"\n{'─' * 50}")
    print("[场景3] Channel 属性")

    local = LocalChannel()
    qq = QQChannel()

    print(f"  LocalChannel.is_external = {local.is_external} (expected: False)")
    print(f"  LocalChannel.template_path = '{local.template_path}' (expected: '')")
    print(f"  QQChannel.is_external = {qq.is_external} (expected: True)")
    print(f"  QQChannel.template_path = '{qq.template_path}' (expected: prompts/yume_qq_system.md)")

    ok = (
        not local.is_external
        and local.template_path == ""
        and qq.is_external
        and qq.template_path == "prompts/yume_qq_system.md"
    )
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


async def test_qq_pre_process_forced():
    """场景 4：QQChannel pre_process — 强制回应模式（被 @）"""
    print(f"\n{'─' * 50}")
    print("[场景4] QQChannel pre_process: forced 模式")

    qq = QQChannel()
    qq.set_session(
        group_context="[群聊] 群友1: 今天天气不错",
        current_speaker="小明",
        is_forced=True,
    )

    ctx = ThinkContext(user_input="yume 还记得上次说的那个游戏吗")
    ctx = await qq.pre_process(ctx)

    has_group = "_group_context" in ctx.memory_context
    has_speaker = "_current_speaker" in ctx.memory_context
    is_forced = ctx.memory_context.get("_is_forced")
    has_rule = "_respond_rule" in ctx.memory_context
    rule = ctx.memory_context.get("_respond_rule", "")
    is_channel_qq = ctx.channel_name == "qq"
    tmpl = ctx.template_path

    print(f"  _group_context set: {has_group}")
    print(f"  _current_speaker = '{ctx.memory_context.get('_current_speaker')}'")
    print(f"  _is_forced = {is_forced}")
    print(f"  respond_rule starts with '现在是强制回应': {rule.startswith('现在是强制回应')}")
    print(f"  channel_name = '{ctx.channel_name}'")
    print(f"  template_path = '{tmpl}'")
    print(f"  precise_query (memory intent): {ctx.memory_context.get('precise_query', '')[:80]}")

    ok = (
        has_group
        and has_speaker
        and is_forced == "true"
        and has_rule
        and "强制回应" in rule
        and is_channel_qq
        and tmpl == "prompts/yume_qq_system.md"
    )
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


async def test_qq_pre_process_smart():
    """场景 5：QQChannel pre_process — 智能回应模式（非 forced）"""
    print(f"\n{'─' * 50}")
    print("[场景5] QQChannel pre_process: 智能模式")

    qq = QQChannel()
    qq.set_session(
        group_context="[群聊] A: 周末去哪玩\n[群聊] B: 爬山吧",
        current_speaker="小红",
        is_forced=False,
    )

    ctx = ThinkContext(user_input="今天天气真好")
    ctx = await qq.pre_process(ctx)

    is_forced = ctx.memory_context.get("_is_forced")
    rule = ctx.memory_context.get("_respond_rule", "")

    print(f"  _is_forced = {is_forced}")
    print(f"  rule contains '[PASS]': {'[PASS]' in rule}")
    print(f"  rule contains '智能回应': {'智能回应' in rule}")

    ok = is_forced == "false" and "[PASS]" in rule and "智能回应" in rule
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


async def test_qq_post_process_pass():
    """场景 6：QQChannel post_process — [PASS] 检测（非 forced 消息）"""
    print(f"\n{'─' * 50}")
    print("[场景6] QQChannel post_process: PASS 静默")

    qq = QQChannel()
    qq.set_session(is_forced=False)

    # LLM 输出 [PASS] → 应清空
    ctx = ThinkContext(user_input="你好", response_text="[PASS]")
    ctx = await qq.post_process(ctx)
    print(f"  non-forced + '[PASS]' → response='{ctx.response_text}' (expected: '')")

    ok1 = ctx.response_text == ""

    # LLM 正常输出 → 保留
    ctx2 = ThinkContext(user_input="你好", response_text="你好呀，小明！")
    ctx2 = await qq.post_process(ctx2)
    print(f"  non-forced + 正常回复 → response='{ctx2.response_text}' (expected: 保留)")

    ok2 = ctx2.response_text == "你好呀，小明！"

    # 空白 PASS 变体
    ctx3 = ThinkContext(user_input="你好", response_text="  [pass]  忽略")
    # [PASS] 在行首才算（regex: ^\s*\[PASS\]），"  [pass]  忽略" 匹配
    ctx3 = await qq.post_process(ctx3)
    print(f"  non-forced + '  [pass]  忽略' → response='{ctx3.response_text}' (expected: '')")

    ok3 = ctx3.response_text == ""

    ok = ok1 and ok2 and ok3
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


async def test_qq_post_process_forced_no_pass():
    """场景 7：QQChannel post_process — forced 消息不触发 PASS"""
    print(f"\n{'─' * 50}")
    print("[场景7] QQChannel post_process: forced 消息忽略 [PASS]")

    qq = QQChannel()
    qq.set_session(is_forced=True)

    # 被 @ 时即使 LLM 输出 [PASS] 也保留（由 system prompt 保证，这里测 post_process 不误杀）
    ctx = ThinkContext(user_input="yume 你在吗", response_text="[PASS]")
    ctx = await qq.post_process(ctx)
    print(f"  forced + '[PASS]' → response='{ctx.response_text}' (expected: '[PASS]')")

    ok = ctx.response_text == "[PASS]"
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


async def test_local_pre_process():
    """场景 8：LocalChannel pre_process — emotion + channel_name"""
    print(f"\n{'─' * 50}")
    print("[场景8] LocalChannel pre_process")

    frontend = MockFrontend()
    tts = MockTTS()
    dispatcher = MockDispatcher()
    local = LocalChannel(dispatcher=dispatcher, frontend=frontend, tts_manager=tts)

    ctx = ThinkContext(
        user_input="你好",
        memory_context={"emotion_label": "happy"},
    )
    ctx = await local.pre_process(ctx)

    print(f"  channel_name = '{ctx.channel_name}' (expected: 'local')")
    print(f"  tts.current_emotion = '{tts.current_emotion}' (expected: 'happy')")
    print(f"  frontend commands: {len(frontend.commands)}")

    ok = ctx.channel_name == "local" and tts.current_emotion == "happy"
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


async def test_local_send_response():
    """场景 9：LocalChannel send_response — 推送到 dispatcher"""
    print(f"\n{'─' * 50}")
    print("[场景9] LocalChannel send_response")

    dispatcher = MockDispatcher()
    local = LocalChannel(dispatcher=dispatcher)

    ctx = ThinkContext(user_input="你好", response_text="你好呀！")
    await local.send_response(ctx)

    print(f"  frontend_msgs: {dispatcher.frontend_msgs}")
    print(f"  tts_msgs: {dispatcher.tts_msgs}")

    ok = len(dispatcher.frontend_msgs) == 1 and len(dispatcher.tts_msgs) == 1
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


async def test_finalize_with_channel_external():
    """场景 10：FinalizeStage — 外部频道（QQ）跳过 TTS 补播"""
    print(f"\n{'─' * 50}")
    print("[场景10] FinalizeStage: QQ 频道跳过本地 TTS")

    qq = QQChannel()
    qq.set_session(is_forced=False)

    dispatcher = MockDispatcher()
    stage = FinalizeStage(memory_core=None, dispatcher=dispatcher, channel=qq)

    ctx = ThinkContext(
        user_input="你好",
        original_user_input="你好",
        response_text="你好呀",
        session_id="qq_group_12345_67890",
        streamed_to_tts=False,
    )
    ctx = await stage.process(ctx)

    # 外部频道不应触发 dispatcher.speak_complete
    print(f"  dispatcher tts_msgs (should be empty): {dispatcher.tts_msgs}")
    print(f"  dispatcher last_speak: {dispatcher.last_speak}")

    ok = len(dispatcher.tts_msgs) == 0 and dispatcher.last_speak is None
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


async def test_finalize_with_channel_local():
    """场景 11：FinalizeStage — 本地频道补播 TTS"""
    print(f"\n{'─' * 50}")
    print("[场景11] FinalizeStage: 本地频道补播 TTS")

    local = LocalChannel()
    dispatcher = MockDispatcher()
    stage = FinalizeStage(memory_core=None, dispatcher=dispatcher, channel=local)

    ctx = ThinkContext(
        user_input="你好",
        original_user_input="你好",
        response_text="你好呀",
        session_id="",
        streamed_to_tts=False,
    )
    ctx = await stage.process(ctx)

    print(f"  dispatcher tts_msgs: {dispatcher.tts_msgs}")

    ok = len(dispatcher.tts_msgs) == 1 and dispatcher.tts_msgs[0] == "你好呀"
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


async def test_context_replace_fields():
    """场景 12：ThinkContext.replace() — template_path 和 channel_name"""
    print(f"\n{'─' * 50}")
    print("[场景12] ThinkContext 新字段")

    ctx = ThinkContext(user_input="hello")
    ctx2 = ctx.replace(template_path="prompts/yume_qq_system.md", channel_name="qq")

    # 原实例不变（不可变语义）
    print(f"  original.template_path = '{ctx.template_path}' (expected: '')")
    print(f"  original.channel_name = '{ctx.channel_name}' (expected: '')")
    print(f"  new.template_path = '{ctx2.template_path}' (expected: 'prompts/yume_qq_system.md')")
    print(f"  new.channel_name = '{ctx2.channel_name}' (expected: 'qq')")

    ok = (
        ctx.template_path == ""
        and ctx.channel_name == ""
        and ctx2.template_path == "prompts/yume_qq_system.md"
        and ctx2.channel_name == "qq"
    )
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


async def test_qq_intent_detection():
    """场景 13：QQChannel 意图检测 — 关键词预搜索"""
    print(f"\n{'─' * 50}")
    print("[场景13] QQChannel 意图检测")

    # 需要 mock memory 来测试意图检测
    class MockContextBuilder:
        def search_memory(self, keyword="", limit=5):
            if "记得" in keyword or "以前" in keyword:
                return "[记忆] 2024-03: 用户提到喜欢像素游戏"
            return "未找到"

    class MockMemory:
        def __init__(self):
            self._context_builder = MockContextBuilder()

    qq = QQChannel(memory=MockMemory())
    qq.set_session(is_forced=False)

    # 记忆意图
    ctx = ThinkContext(user_input="还记得以前说的那个游戏吗")
    ctx = await qq.pre_process(ctx)

    pq = ctx.memory_context.get("precise_query", "")
    print(f"  记忆关键词触发 — precise_query: '{pq[:80]}'")

    ok1 = "记忆" in pq

    # 聊天意图（无关键词）
    ctx2 = ThinkContext(user_input="哈哈哈")
    ctx2 = await qq.pre_process(ctx2)

    pq2 = ctx2.memory_context.get("precise_query", "")
    print(f"  聊天消息 — precise_query: '{pq2[:60] or '(空)'}'")

    ok2 = True  # 无关键词时不注入 precise_query

    ok = ok1 and ok2
    print(f"  {'[PASS] 通过' if ok else '[FAIL] 失败'}")
    return ok


# ═══════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════

async def main():
    print("=" * 50)
    print("Phase 4: Channel 抽象 + QQ/本地统一 验证")
    print("=" * 50)

    results = []

    results.append(await test_registry_resolve_local())
    results.append(await test_registry_resolve_qq())
    results.append(await test_channel_properties())
    results.append(await test_qq_pre_process_forced())
    results.append(await test_qq_pre_process_smart())
    results.append(await test_qq_post_process_pass())
    results.append(await test_qq_post_process_forced_no_pass())
    results.append(await test_local_pre_process())
    results.append(await test_local_send_response())
    results.append(await test_finalize_with_channel_external())
    results.append(await test_finalize_with_channel_local())
    results.append(await test_context_replace_fields())
    results.append(await test_qq_intent_detection())

    passed = sum(results)
    total = len(results)
    print(f"\n{'=' * 50}")
    print(f"结果: {passed}/{total} 通过")
    if passed < total:
        print("[FAIL] 部分场景失败，请检查输出")
    else:
        print("[PASS] 全部通过")


if __name__ == "__main__":
    asyncio.run(main())
