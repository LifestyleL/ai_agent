"""
QQ 适配器：OneBot v11 反向 WebSocket

协议：OneBot v11 reverse WebSocket
QQ 框架（NapCat / LLOneBot）作为 WS 客户端连接本服务。
消息通过 pipeline.process() 进入 AI 管线，回复直接通过 WS 发回。

session_id 格式：qq_{message_type}_{chat_id}_{user_id}
"""

import asyncio
import json
import logging
from typing import Any, Dict, Optional, Callable, Awaitable

from aiohttp import web

logger = logging.getLogger(__name__)

MessageHandler = Callable[[str, str], Awaitable[str]]  # (text, session_id) -> response_text


class QQAdapter:
    """OneBot v11 反向 WebSocket 适配器（无框架依赖）"""

    def __init__(self, host: str = "0.0.0.0", port: int = 5800, path: str = "/onebot"):
        self._host = host
        self._port = port
        self._path = path
        self._runner: Optional[web.AppRunner] = None
        self._ws: Optional[web.WebSocketResponse] = None
        self._handler: Optional[MessageHandler] = None

    def set_handler(self, handler: MessageHandler) -> None:
        """设置消息处理回调：async def handler(text, session_id) -> str"""
        self._handler = handler

    async def start(self) -> None:
        """启动 WS 服务"""
        app = web.Application()
        app["adapter"] = self
        app.router.add_get(self._path, self._handle_ws)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        logger.info("[QQAdapter] OneBot WS listening ws://%s:%s%s", self._host, self._port, self._path)

    async def shutdown(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
        self._ws = None

    @property
    def connected(self) -> bool:
        return self._ws is not None and not self._ws.closed

    # ── internal ──

    @staticmethod
    def _make_session_id(data: dict) -> str:
        msg_type = data.get("message_type", "private")
        user_id = str(data.get("user_id", ""))
        if msg_type == "group":
            return f"qq_group_{data.get('group_id', '')}_{user_id}"
        return f"qq_private_{user_id}"

    @staticmethod
    def _build_response(data: dict, text: str) -> dict:
        msg_type = data.get("message_type", "private")
        if msg_type == "group":
            params = {"message_type": "group", "group_id": data["group_id"], "message": text}
        else:
            params = {"message_type": "private", "user_id": data["user_id"], "message": text}
        return {"action": "send_msg", "params": params}

    async def _handle_ws(self, request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._ws = ws
        adapter = request.app["adapter"]
        remote = request.remote
        logger.info("[QQAdapter] QQ client connected (%s)", remote)

        async for msg in ws:
            if msg.type != web.WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except json.JSONDecodeError:
                continue
            if data.get("post_type") != "message":
                continue

            text = data.get("raw_message", "")
            if not text or not text.strip():
                continue

            session_id = self._make_session_id(data)
            msg_type = data.get("message_type", "private")

            if msg_type == "group":
                sender = data.get("sender", {}).get("nickname", "")
                logger.info("[QQAdapter] Group %s @%s: %.50s", data.get("group_id"), sender, text)
            else:
                logger.info("[QQAdapter] Private %s: %.50s", data.get("user_id"), text)

            try:
                response = await self._handler(text.strip(), session_id)
            except Exception as e:
                logger.error("[QQAdapter] Handler error: %s", e)
                response = "呜…刚才出错了…"

            await ws.send_json(self._build_response(data, response))
            logger.info("[QQAdapter] Response sent session=%s len=%d", session_id, len(response))

        logger.info("[QQAdapter] QQ client disconnected (%s)", remote)
        self._ws = None
        return ws
