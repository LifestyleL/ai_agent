"""
run_qq.py — QQ AI 入口（v2: 共享 ReAct ThinkPipeline）

架构：
  init → DI Container → GroupResponseDecider → Channel.pre_process
       → ThinkPipeline.execute() → Channel.post_process → OneBot WS 回复

与 main.py 共享：ThinkPipeline / LLMChatStage / ToolExecStage / SkillManager / ToolRegistry
QQ 消息通过 QQChannel 走统一的 ReAct 管线。
"""

import asyncio
import json
import logging
import os
import re
import signal
import sys
import threading

from aiohttp import web

# ── path ──
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)
_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)


def _init_deps():
    """初始化共享依赖（与 main.py 相同的 ThinkPipeline）"""
    from config import validate_config

    validate_config()

    from core.llm.llm_factory import LLMFactory
    from core.memory.memory_facade import MemoryFacade
    from core.memory.short_term import ShortTermMemory
    from core.emotion.emotion_engine import EmotionEngine

    from backend.plugins.registry import ToolRegistry
    from backend.plugins.builtin.adapters import (
        SearchMemoryAdapter, ReadFileAdapter, WriteDiaryAdapter,
        ListDirectoryAdapter, GrepSearchAdapter, WebSearchAdapter,
        RecognizeImageAdapter,
    )
    from backend.core.skill.skill_manager import SkillManager
    from backend.core.channel.qq_channel import QQChannel
    from backend.core.think_pipeline import (
        ThinkPipeline, MemoryRetrieveStage, PromptBuildStage, FinalizeStage,
    )
    from backend.core.think_pipeline.skill_match_stage import SkillMatchStage
    from backend.core.think_pipeline.llm_chat_stage import LLMChatStage
    from backend.core.think_pipeline.tool_exec_stage import ToolExecStage
    from backend.core.think_pipeline.dispatchers import DefaultResponseDispatcher
    from backend.adapters.qq.group_response_decider import GroupResponseDecider

    llm = LLMFactory.get_default()
    memory = MemoryFacade(llm_api=llm)
    qq_short_term = ShortTermMemory(card_store=memory._card_store)
    emotion = EmotionEngine()

    # 工具注册（QQ 白名单：只读+日记+文件探索+图片识别）
    registry = ToolRegistry(allowlist={
        "search_memory", "read_file", "write_diary",
        "list_directory", "grep_search", "web_search",
        "recognize_image",
    })
    registry.register(SearchMemoryAdapter())
    registry.register(ReadFileAdapter())
    registry.register(WriteDiaryAdapter())
    registry.register(ListDirectoryAdapter())
    registry.register(GrepSearchAdapter())
    registry.register(WebSearchAdapter())
    registry.register(RecognizeImageAdapter())

    # 技能管理器
    skill_manager = SkillManager(llm=llm, tool_registry=registry)
    skill_manager.load_all()

    # QQ Channel
    qq_channel = QQChannel(memory=memory, emotion=emotion)

    # 空 dispatcher（QQ 不需要本地推送）
    noop_dispatcher = DefaultResponseDispatcher()

    # Setup stages
    setup_stages = [
        MemoryRetrieveStage(memory_core=memory, emotion_engine=emotion, dispatcher=noop_dispatcher),
        SkillMatchStage(skill_manager=skill_manager),
        PromptBuildStage(),
    ]

    llm_stage = LLMChatStage(llm=llm, registry=registry)
    tool_stage = ToolExecStage(registry=registry)
    finalize_stage = FinalizeStage(memory_core=memory, dispatcher=noop_dispatcher, channel=qq_channel)

    pipeline = ThinkPipeline(
        setup_stages=setup_stages,
        llm_stage=llm_stage,
        tool_stage=tool_stage,
        finalize_stage=finalize_stage,
    )

    decider = GroupResponseDecider(self_id=_QQ_SELF_ID, llm=llm)

    return pipeline, decider, qq_channel, memory


# ── OneBot WebSocket ──


_QQ_SELF_ID = os.environ.get("QQ_SELF_ID", "1910867718")
_AT_PATTERN = re.compile(r'\[CQ:at,[^\]]*\]')
_STRIP_FORMAT_ECHO = re.compile(
    r'^\[群聊\]\s*\S*:\s*'
    r'|^（来自群聊[^）]*）\s*'
    r'|^\[群聊消息[^\]]*\]\s*'
    r'|^yume[：:]\s*'
)


def _make_session_id(data: dict) -> str:
    msg_type = data.get("message_type", "private")
    user_id = str(data.get("user_id", ""))
    if msg_type == "group":
        return f"qq_group_{data.get('group_id', '')}_{user_id}"
    return f"qq_private_{user_id}"


def _build_onebot_response(data: dict, text: str) -> dict:
    msg_type = data.get("message_type", "private")
    if msg_type == "group":
        params = {"message_type": "group", "group_id": data["group_id"], "message": text}
    else:
        params = {"message_type": "private", "user_id": data["user_id"], "message": text}
    return {"action": "send_msg", "params": params}


def _download_qq_image(url: str, memory) -> str:
    """下载 QQ 图片到 agent_memory/temp/，返回相对路径（相对于 agent_memory）"""
    import hashlib
    import time
    import urllib.request

    temp_dir = memory._memory_root / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    # 用 URL hash + 时间戳生成文件名
    url_hash = hashlib.md5(url.encode()).hexdigest()[:12]
    timestamp = int(time.time() * 1000)
    ext = ".jpg"
    filename = f"qq_img_{url_hash}_{timestamp}{ext}"
    filepath = temp_dir / filename

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://q.qq.com/",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            filepath.write_bytes(resp.read())
        logging.info("[QQ] Image downloaded: %s (%d bytes)", filename, filepath.stat().st_size)
        return f"temp/{filename}"
    except Exception as e:
        logging.warning("[QQ] Image download failed: %s — %s", url[:80], e)
        return ""


async def _ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    pipeline = request.app["pipeline"]
    decider = request.app["decider"]
    qq_channel = request.app["qq_channel"]
    remote = request.remote
    logging.info("[QQ] QQ client connected (%s)", remote)

    from backend.core.think_pipeline.context import ThinkContext

    async for msg in ws:
        if msg.type != web.WSMsgType.TEXT:
            continue
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            continue
        if data.get("post_type") != "message":
            continue

        raw_text = data.get("raw_message", "")

        # ── 图片检测：解析 message 数组中的图片，下载保存 ──
        image_paths = []
        message_array = data.get("message", [])
        if message_array and isinstance(message_array, list):
            for seg in message_array:
                if seg.get("type") == "image":
                    img_data = seg.get("data", {})
                    img_url = img_data.get("url", "")
                    if img_url:
                        saved = _download_qq_image(img_url, memory)
                        if saved:
                            image_paths.append(saved)

        if not raw_text and image_paths:
            raw_text = "[图片]"
        if image_paths:
            img_hints = "\n".join(f"- {p}" for p in image_paths)
            raw_text = (
                f"{raw_text}\n\n"
                f"[系统：用户发送了 {len(image_paths)} 张图片，已保存到以下路径。"
                f"如需查看图片内容，请使用 recognize_image 工具：]\n"
                f"{img_hints}"
            )

        if not raw_text or not raw_text.strip():
            continue

        session_id = _make_session_id(data)
        msg_type = data.get("message_type", "private")

        if msg_type == "group":
            group_id = str(data.get("group_id", ""))
            user_id = str(data.get("user_id", ""))
            sender = data.get("sender", {}).get("card") or data.get("sender", {}).get("nickname", "")
            logging.info("[QQ] Group %s @%s: %.50s", group_id, sender, raw_text)

            decider.observe(group_id, raw_text, sender)

            should, reason = decider.should_respond(group_id, user_id, raw_text)
            if not should:
                if reason not in ("cooldown", "duplicate_at"):
                    logging.info("[QQ] Group %s skip: %s (%.50s)", group_id, reason, raw_text)
                continue

            is_forced = reason in ("at_bot", "wake_word", "command")
            logging.info("[QQ] Group %s DECIDE: %s (forced=%s)", group_id, reason, is_forced)

            clean = _AT_PATTERN.sub("", raw_text).strip()
            text = f"（来自群聊，{sender} 说：）{clean}"
            group_ctx = decider.get_group_context(group_id)
        else:
            text = raw_text.strip()
            is_forced = True
            sender = ""
            group_ctx = ""
            logging.info("[QQ] Private %s: %.50s", data.get("user_id"), text)

        # ── 共享 ReAct 管线 ──
        qq_channel.set_session(
            group_context=group_ctx,
            current_speaker=sender,
            is_forced=is_forced,
        )

        ctx = ThinkContext(
            user_input=text,
            session_id=session_id,
            memory_context={},
        )
        ctx = await qq_channel.pre_process(ctx)

        try:
            ctx = await pipeline.execute(ctx)
        except Exception as e:
            logging.error("[QQ] Pipeline error: %s", e)
            response = "呜…刚才出错了，稍等一下…"
        else:
            ctx = await qq_channel.post_process(ctx)
            response = ctx.response_text

        # LLM 决定不回应 → 静默
        if not response:
            if msg_type == "group":
                logging.info("[QQ] Group %s LLM pass: stay silent", group_id)
            continue

        # 防 LLM echo
        if msg_type == "group":
            response = _STRIP_FORMAT_ECHO.sub("", response).strip()
            decider.on_bot_reply(group_id, response)

        await ws.send_json(_build_onebot_response(data, response))
        logging.info("[QQ] Response sent session=%s len=%d", session_id, len(response))

    logging.info("[QQ] QQ client disconnected (%s)", remote)
    return ws


# ── main ──


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    pipeline, decider, qq_channel, memory = _init_deps()

    host = os.environ.get("QQ_WS_HOST", "0.0.0.0")
    port = int(os.environ.get("QQ_WS_PORT", "5800"))
    path = os.environ.get("QQ_WS_PATH", "/onebot")

    # WS server
    app = web.Application()
    app["pipeline"] = pipeline
    app["decider"] = decider
    app["qq_channel"] = qq_channel
    app.router.add_get(path, _ws_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    print(f"[QQ] OneBot WS listening ws://{host}:{port}{path}")

    # ── 终端输入线程 ──
    loop = asyncio.get_running_loop()
    stdin_stop = threading.Event()

    from backend.core.think_pipeline.context import ThinkContext

    def _stdin_loop():
        print()
        print("=" * 40)
        print("  QQ AI 终端测试模式")
        print("  打字对话 | /diary 整理日记")
        print("  /search <关键词> | /quit 退出")
        print("=" * 40)
        print()
        while not stdin_stop.is_set():
            try:
                text = input("user：")
            except EOFError:
                break
            if text.strip() == "/quit":
                stdin_stop.set()
                loop.call_soon_threadsafe(_shutdown.set)
                break
            if not text.strip():
                continue
            if text.strip().startswith("/diary"):
                try:
                    from datetime import datetime
                    dw = memory._diary_writer
                    dates = dw._catch_up_diary()
                    for ds in dates:
                        memory._diary_processor.process_daily_diary_async(ds)

                    today = datetime.now().strftime("%Y-%m-%d")
                    draft_path = memory._memory_root / "diary" / "drafts" / "daily_draft.txt"
                    if draft_path.exists() and draft_path.stat().st_size > 100:
                        raw_text = draft_path.read_text(encoding="utf-8", errors="replace")
                        today_diary = memory._memory_root / "diary" / "daily" / f"{today}.md"
                        today_diary.parent.mkdir(parents=True, exist_ok=True)

                        if today_diary.exists() and today_diary.stat().st_size >= 200:
                            old_content = today_diary.read_text(encoding="utf-8", errors="replace")
                            from backend.core.memory.diary_processor import _SPLIT_MARKER
                            if _SPLIT_MARKER in old_content:
                                old_raw = old_content.split(_SPLIT_MARKER, 1)[1]
                            else:
                                old_raw = old_content
                            merged = old_raw.strip() + "\n\n" + raw_text.strip()
                            today_diary.write_text(f"# {today} 对话日记\n\n{merged}", encoding="utf-8")
                            print(f"[日记] 追加模式：旧 {len(old_raw)} + 新 {len(raw_text)} 字符 → 重新整理中...")
                        else:
                            today_diary.write_text(f"# {today} 对话日记\n\n{raw_text}", encoding="utf-8")
                            print(f"[日记] 首次归档 ({len(raw_text)} 字符)，LLM 整理中...")

                        memory._diary_processor.process_daily_diary_async(today)
                        draft_path.write_text(f"--- {today} ---\n", encoding="utf-8")
                        dw._last_active_date = today
                    else:
                        print(f"[日记] 当天草稿为空或过短，跳过")

                    print(f"[日记] 完成 — 历史归档: {len(dates)} 天\n")
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    print(f"[日记] 错误: {e}\n")
                continue
            if text.strip().startswith("/search"):
                keyword = text.strip()[8:].strip()
                if keyword:
                    try:
                        cb = memory._context_builder
                        result = cb.search_memory(keyword=keyword, limit=5)
                        print(f"[搜索] {keyword}:")
                        print(result[:800] if result else "（无结果）")
                        print()
                    except Exception as e:
                        print(f"[搜索] 错误: {e}\n")
                else:
                    print("[搜索] 用法: /search <关键词>\n")
                continue
            try:
                qq_channel.set_session(is_forced=True)
                ctx = ThinkContext(
                    user_input=text.strip(),
                    session_id="qq_private_terminal",
                    memory_context={},
                )
                future_pre = asyncio.run_coroutine_threadsafe(
                    qq_channel.pre_process(ctx), loop
                )
                ctx = future_pre.result(timeout=10)
                future_pipe = asyncio.run_coroutine_threadsafe(
                    pipeline.execute(ctx), loop
                )
                ctx = future_pipe.result(timeout=120)
                future_post = asyncio.run_coroutine_threadsafe(
                    qq_channel.post_process(ctx), loop
                )
                ctx = future_post.result(timeout=5)
                response = ctx.response_text
                print(f"yume：{response}\n")
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[ERROR] {e}\n")

    threading.Thread(target=_stdin_loop, daemon=True).start()

    # ── 信号处理 ──
    _shutdown = asyncio.Event()

    def _on_signal(signum, frame):
        print("\n[QQ] Shutting down...")
        stdin_stop.set()
        loop.call_soon_threadsafe(_shutdown.set)

    try:
        signal.signal(signal.SIGINT, _on_signal)
        signal.signal(signal.SIGTERM, _on_signal)
    except ValueError:
        pass

    print("[QQ] Ready. Terminal chat active, waiting for QQ client...\n")
    await _shutdown.wait()

    # ── 优雅关闭 ──
    await runner.cleanup()
    print("[QQ] Stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[QQ] Stopped.")
