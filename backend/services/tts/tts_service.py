"""
阿里云 CosyVoice TTS（长连接复用版）

改造为 Capability 实现，去掉类级单例 __new__。
"""
import base64
import time
import os
import threading
import atexit
import numpy as np
import dashscope
from dashscope.audio.qwen_tts_realtime import QwenTtsRealtime, QwenTtsRealtimeCallback, AudioFormat
from .tts_config import TTSConfig


class TTSService:
    """阿里云 CosyVoice TTS（长连接复用版）"""

    name = "tts"
    version = "1.0"

    def __init__(self):
        # 实例级初始化守卫（替代旧的类级 __new__ 单例）
        if hasattr(self, '_init_done') and self._init_done:
            return

        TTSConfig.validate()
        print(f"[TTS] CosyVoice 就绪 (模型: {TTSConfig.MODEL}, 音色: {TTSConfig.voice})")

        current_key = TTSConfig.API_KEY
        print(f"[KEY] [TTS] 当前API密钥: {current_key[:8]}...")

        dashscope.api_key = current_key

        self._is_connected = False
        self._abort_flag = threading.Event()
        self._reconnect_lock = threading.Lock()

        self._init_realtime_tts()

        self._cleaned_up = False

        self._stop_heartbeat = False
        self._heartbeat_thread = None
        self._start_heartbeat()

        self._init_done = True

        atexit.register(self._cleanup)

    # ── Capability 生命周期 ──

    @property
    def enabled(self) -> bool:
        return True

    async def initialize(self, deps) -> None:
        pass

    async def shutdown(self) -> None:
        self._cleanup()

    def get_status(self) -> dict:
        return {
            "connected": self._is_connected,
            "speaking": getattr(self, '_is_speaking', False),
        }

    # ── 窄接口: 只产出 (pcm_bytes, visemes) ──

    def synthesize_with_visemes(self, text: str, emotion: str = "neutral") -> tuple:
        """合成并返回 (pcm_bytes, viseme_frames)"""
        return self._synthesize_with_retry(text, emotion)

    def synthesize(self, text: str, emotion: str = "neutral") -> bytes:
        """同步合成，返回 PCM 音频字节"""
        pcm_bytes, _ = self._synthesize_with_retry(text, emotion)
        return pcm_bytes

    # ── 心跳 ──

    def _start_heartbeat(self):
        """启动心跳保活线程"""
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            print("[HEARTBEAT] [TTS] 心跳线程已在运行")
            return

        self._stop_heartbeat = False
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="TTS-Heartbeat",
            daemon=True
        )
        self._heartbeat_thread.start()
        print("[HEARTBEAT] [TTS] 心跳保活线程已启动（间隔20秒，主动保活）")

    def _stop_heartbeat_thread(self):
        """停止心跳线程"""
        if not self._heartbeat_thread:
            return

        self._stop_heartbeat = True
        if self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=1.0)
            if self._heartbeat_thread.is_alive():
                print("[WARN] [TTS] 心跳线程还在sleep中，daemon线程将随进程退出")
        self._heartbeat_thread = None

    def _heartbeat_loop(self):
        """心跳循环：每20秒检查连接状态，断则重连"""
        import time
        heartbeat_interval = 20

        while not self._stop_heartbeat:
            time.sleep(heartbeat_interval)

            if self._stop_heartbeat:
                break

            try:
                if hasattr(self, '_is_connected') and self._is_connected:
                    pass
                else:
                    print("[HEARTBEAT] [TTS] 检测到连接断开，尝试重新连接...")
                    self._ensure_connected()
            except Exception as e:
                print(f"[ERROR] [TTS] 心跳检查异常: {e}")
                self._is_connected = False

    def _cleanup(self):
        """清理所有WebSocket连接（安全，可多次调用）"""
        if hasattr(self, '_cleaned_up') and self._cleaned_up:
            return

        try:
            all_conns = getattr(self, '_all_connections', [])
            if all_conns:
                print(f"[CONN] [TTS] 正在关闭 {len(all_conns)} 个WebSocket连接...")
                for conn in list(all_conns):
                    try:
                        conn.close()
                    except Exception as e:
                        print(f"[WARN]  [TTS] 关闭连接时出错: {e}")
                self._all_connections = []
                print("[OK] [TTS] 所有WebSocket连接已关闭")
            elif hasattr(self, '_tts') and self._tts:
                try:
                    print("[CONN] [TTS] 正在关闭WebSocket连接...")
                    self._tts.close()
                    print("[OK] [TTS] WebSocket连接已关闭")
                except Exception as e:
                    print(f"[WARN]  [TTS] 关闭连接时出错: {e}")
                finally:
                    self._tts = None
        finally:
            self._is_connected = False
            self._tts = None
            if hasattr(self, '_stop_heartbeat'):
                self._stop_heartbeat_thread()
            self._cleaned_up = True

    def __del__(self):
        self._cleanup()

    def close(self):
        self._cleanup()

    def _init_realtime_tts(self):
        """初始化底层连接实例"""

        class ReusableCallback(QwenTtsRealtimeCallback):
            def __init__(self, outer_self):
                super().__init__()
                self.outer_self = outer_self
                self.complete_event = threading.Event()
                self._audio_chunks = []
                self._error_msg = None

            def on_open(self) -> None:
                print("[TTS] WebSocket连接已建立")
                self.outer_self._is_connected = True

            def on_close(self, close_status_code, close_msg) -> None:
                print(f"[TTS] 连接关闭 code={close_status_code}, msg={close_msg}")
                self.outer_self._is_connected = False
                self.complete_event.set()

            def on_event(self, response: dict) -> None:
                try:
                    type = response.get("type")
                    if type == "session.created":
                        print(f"[TTS] 会话创建: {response['session']['id']}")
                    elif type == "response.audio.delta":
                        recv_audio_b64 = response.get("delta")
                        if recv_audio_b64:
                            audio_data = base64.b64decode(recv_audio_b64)
                            self._audio_chunks.append(audio_data)
                    elif type == "response.done":
                        print("[TTS] 响应完成")
                    elif type == "session.finished":
                        print("[TTS] 会话结束")
                        self.complete_event.set()
                    elif 'error' in str(response).lower():
                        self._error_msg = str(response)
                        print(f"[TTS] 收到错误: {self._error_msg}")
                        self.complete_event.set()
                except Exception as e:
                    self._error_msg = str(e)
                    print(f"[TTS] 事件处理错误: {e}")
                    self.complete_event.set()

            def wait_for_finished(self, timeout=15):
                self.complete_event.wait(timeout)

            def get_audio_data(self):
                return b''.join(self._audio_chunks)

            def reset(self):
                self._audio_chunks.clear()
                self._error_msg = None
                self.complete_event.clear()

        self._callback = ReusableCallback(self)

        if hasattr(self, '_tts') and self._tts:
            try:
                self._tts.close()
            except Exception:
                pass

        dashscope.api_key = TTSConfig.API_KEY
        print(f"[KEY] [TTS] 使用API密钥: {TTSConfig.API_KEY[:8]}...")

        new_tts = QwenTtsRealtime(
            model=TTSConfig.MODEL,
            callback=self._callback,
            url=TTSConfig.BASE_URL
        )
        if not hasattr(self, '_all_connections'):
            self._all_connections = []
        self._all_connections.append(new_tts)
        self._tts = new_tts

        try:
            max_retries = 3
            base_delay = 2

            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        delay = base_delay * (2 ** (attempt - 1))
                        print(f"[RETRY] [TTS] 第 {attempt + 1}/{max_retries} 次尝试连接，等待 {delay} 秒后重试...")
                        time.sleep(delay)

                    self._tts.connect()
                    self._is_connected = True
                    self._is_speaking = False
                    print("[CONN] [TTS] WebSocket 底层长连接已建立！")
                    break

                except Exception as e:
                    error_msg = str(e)
                    print(f"[ERROR] [TTS] 连接尝试 {attempt + 1}/{max_retries} 失败: {error_msg}")

                    if "401" in error_msg or "Unauthorized" in error_msg:
                        print("[ERROR] [TTS] 认证失败，无需重试")
                        self._is_connected = False
                        raise RuntimeError(f"TTS认证失败: {error_msg}")

                    port_errors = ["address already in use", "port", "socket", "connection refused", "timeout"]
                    if any(err in error_msg.lower() for err in port_errors):
                        print(f"[WARN]  [TTS] 检测到端口/连接问题，可能是之前的连接未完全关闭")
                        if attempt < max_retries - 1:
                            print(f"[TIP] 建议：等待 {base_delay * (2 ** attempt)} 秒让系统释放资源")

                    if attempt == max_retries - 1:
                        self._is_connected = False
                        try:
                            self._tts.close()
                        except:
                            pass
                        self._tts = None
                        raise RuntimeError(f"TTS连接失败，已重试{max_retries}次: {error_msg}")

        except Exception as e:
            self._is_connected = False
            print(f"[ERROR] [TTS] WebSocket连接失败: {e}")
            if hasattr(e, 'response'):
                print(f"[ERROR] [TTS] 响应详情: {e.response}")
            raise RuntimeError(f"TTS连接失败: {str(e)}")

    def _build_instructions(self, emotion: str) -> str:
        """根据情绪构建语音指导指令"""
        if emotion in ["happy", "excited"]:
            return "用非常可爱、元气满满的少女声音说话，语速稍微轻快一点，带有笑意。"
        elif emotion in ["sad", "gentle"]:
            return "用温柔、轻柔的少女声音说话，语速放缓，声音甜美有磁性。"
        elif emotion in ["angry", "annoyed"]:
            return "用有点小傲娇的少女声音说话，带一点点嘟嘴抱怨的感觉。"
        else:
            return "用自然、可爱的年轻女声日常说话，语气轻松亲切。"

    def _ensure_connected(self):
        """确保TTS连接处于活动状态"""
        if hasattr(self, '_is_connected') and self._is_connected:
            return

        acquired = self._reconnect_lock.acquire(timeout=15)
        if not acquired:
            print("[CONN] [TTS] 重连锁获取超时（15s），其他线程正在重连中，本次跳过")
            return

        try:
            if hasattr(self, '_is_connected') and self._is_connected:
                return

            print("[CONN] [TTS] 连接已断开，尝试重新连接...")
            try:
                if hasattr(self, '_tts') and self._tts:
                    try:
                        self._tts.close()
                    except:
                        pass

                self._init_realtime_tts()
                self._cleaned_up = False
                print("[OK] [TTS] 重新连接成功")
            except Exception as e:
                print(f"[ERROR] [TTS] 重新连接失败: {e}")
                self._is_connected = False
                raise RuntimeError(f"TTS重新连接失败: {str(e)}")
        finally:
            self._reconnect_lock.release()

    def _synthesize_with_retry(self, text: str, emotion: str = "neutral") -> tuple:
        """单次合成（每次都会重置会话状态）"""
        import re

        if self._abort_flag.is_set():
            self._abort_flag.clear()
            return b'', []

        self._ensure_connected()

        text = re.sub(r'[（(][^）)]*[）)]', '', text)
        text = text.replace('...', '。').replace('…', '。')
        text = re.sub(r'\s+', '', text)
        text = text.strip('，。！？、,!?')
        if not text:
            print("[DEBUG] [TTS] 清洗后文本为空，跳过合成")
            return b'', []

        print(f"[DEBUG] [TTS] 检查并发锁: _is_speaking={self._is_speaking}")
        if self._is_speaking:
            raise RuntimeError("上一句话还没合成完，请稍后再试")

        self._is_speaking = True
        print(f"[DEBUG] [TTS] 获取锁，开始合成: '{text[:30]}...'")

        self._callback.reset()

        try:
            print(f"[DEBUG] [TTS] 使用voice: {TTSConfig.voice}")
            self._tts.update_session(
                voice=TTSConfig.voice,
                response_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
                mode='server_commit'
            )

            self._tts.append_text(text)
            self._tts.finish()

            self._callback.wait_for_finished(timeout=15)

            if self._callback._error_msg:
                raise RuntimeError(f"TTS合成错误: {self._callback._error_msg}")

            all_audio = self._callback.get_audio_data()
            if len(all_audio) < 100:
                self._is_connected = False
                raise RuntimeError(f"TTS 返回空音频，可能连接已断开")

            sample_rate = 24000
            mouth_frames = []
            frame_bytes = int(sample_rate * 0.01) * 2
            for i in range(0, len(all_audio), frame_bytes):
                chunk = all_audio[i:i + frame_bytes]
                if len(chunk) < 4:
                    break
                samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                rms = float(np.sqrt(np.mean(samples ** 2)))
                mouth = min(1.0, rms * 5.0)
                if mouth_frames:
                    mouth = 0.3 * mouth_frames[-1]['v'] + 0.7 * mouth
                mouth_frames.append({'t': round(i / 2 / sample_rate, 3), 'v': round(mouth, 3)})

            synthesis_complete_time = time.time() * 1000
            print(f"[延迟诊断] 第一句合成完成时间戳: {synthesis_complete_time:.2f} ms (文本: '{text[:30]}...')")

            return all_audio, mouth_frames

        finally:
            self._is_speaking = False
            print(f"[DEBUG] [TTS] 释放锁，合成完成")
