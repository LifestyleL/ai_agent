"""
视觉观察器：协调截图采集、变化检测、VLM 描述、事件推送
"""
from __future__ import annotations

import asyncio
import time
import threading
from typing import Optional, TYPE_CHECKING

from .frame_differ import FrameDiffer
from .vlm_client import VLMClient
import config

if TYPE_CHECKING:
    from core.spontaneous.engine import SpontaneousEngine


class VisualObserver:
    """自适应节奏调度：5s 起步，连续 3 帧不变 +5s 退避，变化则重置"""

    def __init__(self, engine: "SpontaneousEngine", ws_server=None):
        self._engine = engine
        self._ws = ws_server
        self._differ = FrameDiffer(
            threshold=getattr(config, 'VISION_FRAME_DIFF_THRESHOLD', 0.08)
        )

        # 自适应截图频率：5s 起步，连续 3 帧不变则 +5s，变化则重置
        self._base_interval = 5                      # 起始间隔
        self._current_interval = self._base_interval  # 当前间隔（动态调整）
        self._interval_step = 5                       # 每次增加的秒数
        self._max_interval = 300                      # 最大间隔上限（5分钟）
        self._unchanged_streak = 0                    # 连续不变帧计数
        self._streak_threshold = 3                    # 触发退避的阈值

        self._last_capture_time: float = 0
        self._cooldown_until: float = 0    # VLM 调用后冷却
        self._cooldown_seconds = getattr(config, 'VISION_COOLDOWN_SECONDS', 30)

        # 等待前端返回的截图（自动模式）
        self._pending = False
        self._pending_frame: Optional[str] = None
        self._lock = threading.Lock()

        # 用户主动 look 的 Future（同步等待模式）
        self._look_future: Optional[asyncio.Future] = None

        # 最新描述
        self._last_description: str = ""

        # 回调注册：由 message_router 调用
        self.on_frame_received = self._on_frame_received

        print("[VisualObserver] 初始化完成")

    # ── 公共 API ──

    async def tick(self, silence_duration: float):
        """
        由 engine._main_loop 每轮调用。
        根据沉默时长决定是否请求截图。
        """
        now = time.time()

        # 冷却中不请求
        if now < self._cooldown_until:
            return

        # 正在等待前端返回，不重复请求
        if self._pending:
            # 超时 10s 重置
            if now - self._last_capture_time > 10:
                self._pending = False
            return

        # 计算间隔：自适应退避
        interval = self._current_interval

        if now - self._last_capture_time < interval:
            return

        # 请求截图
        self._last_capture_time = now
        self._pending = True

        if self._ws and hasattr(self._ws, 'send_screenshot_request'):
            await self._ws.send_screenshot_request()
        else:
            self._pending = False

    async def request_look(self) -> str:
        """用户主动要求看屏幕：同步等待截图 → 返回 raw base64（主 LLM 是 VLM，直接看图）"""
        if not self._ws or not hasattr(self._ws, 'send_screenshot_request'):
            print("[VisualObserver] request_look: WebSocket 不可用")
            return ""

        loop = asyncio.get_running_loop()
        self._look_future = loop.create_future()

        print("[VisualObserver] 用户请求 look，发送截图请求...")
        await self._ws.send_screenshot_request()

        try:
            base64_image = await asyncio.wait_for(self._look_future, timeout=15.0)
        except asyncio.TimeoutError:
            print("[VisualObserver] request_look: 截图超时")
            self._look_future = None
            return ""

        self._look_future = None

        if not base64_image:
            return ""

        print(f"[VisualObserver] request_look 返回 raw 截图 ({len(base64_image)} chars)")
        return base64_image

    def _describe_sync(self, base64_image: str) -> str:
        """同步 VLM 调用（在线程池中运行）"""
        try:
            client = VLMClient()
            return client.describe(base64_image)
        except Exception as e:
            print(f"[VisualObserver] VLM 调用异常: {e}")
            return ""

    def _on_frame_received(self, base64_image: str):
        """收到前端截图回调（由 message_router 线程调用）"""
        # 如果用户主动 look 正在等待，直接返回截图
        if self._look_future and not self._look_future.done():
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.call_soon_threadsafe(self._look_future.set_result, base64_image)
                else:
                    self._look_future.set_result(base64_image)
            except Exception:
                self._look_future.set_result(base64_image)
            return

        # 自动模式：变化检测 → VLM → 事件推送
        with self._lock:
            if not base64_image:
                self._pending = False
                return

            self._pending = False

            # 变化检测
            changed = self._differ.is_changed(base64_image)
            if changed:
                # 画面有变化 → 重置频率
                self._current_interval = self._base_interval
                self._unchanged_streak = 0
                print(f"[VisualObserver] 画面有变化，重置间隔={self._base_interval}s，调用 VLM 描述...")
            else:
                # 无变化 → 累积 streak，超过阈值则退避
                self._unchanged_streak += 1
                if self._unchanged_streak >= self._streak_threshold:
                    self._current_interval = min(
                        self._current_interval + self._interval_step,
                        self._max_interval
                    )
                    self._unchanged_streak = 0
                    print(f"[VisualObserver] {self._streak_threshold}帧不变，退避至间隔={self._current_interval}s")
                print("[VisualObserver] 画面无变化，跳过")
                return

            # 启动冷却
            self._cooldown_until = time.time() + self._cooldown_seconds

        # VLM 调用在锁外进行（可能耗时）
        description = self._describe_sync(base64_image)

        if description:
            self._last_description = description
            print(f"[VisualObserver] VLM 描述: {description}")

            # 推入内部事件
            try:
                self._engine._push_internal_event(
                    event_type="visual_observation",
                    strength=0.7,
                    summary=description,
                )
                print(f"[VisualObserver] 事件已推入: visual_observation")
            except Exception as e:
                print(f"[VisualObserver] 推送事件失败: {e}")

    # ── 属性 ──

    @property
    def last_description(self) -> str:
        return self._last_description

    @property
    def is_cooling_down(self) -> bool:
        return time.time() < self._cooldown_until
