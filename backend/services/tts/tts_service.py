import base64
import time
import os
import threading
import signal
import atexit
import numpy as np
import dashscope
from dashscope.audio.qwen_tts_realtime import QwenTtsRealtime, QwenTtsRealtimeCallback, AudioFormat
from .tts_config import TTSConfig

# API密钥将在TTSService.__init__中设置，确保TTSConfig已完全初始化

class TTSService:
    """阿里云 CosyVoice TTS（长连接复用版）"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 防止重复初始化
        if hasattr(self, '_initialized') and self._initialized:
            return

        TTSConfig.validate()
        print(f"[TTS] CosyVoice 就绪 (模型: {TTSConfig.MODEL}, 音色: {TTSConfig.voice})")

        # API密钥从统一配置读取
        current_key = TTSConfig.API_KEY
        print(f"[KEY] [TTS] 当前API密钥: {current_key[:8]}...")

        # 🌟 设置API密钥
        dashscope.api_key = current_key

        # 初始化连接状态
        self._is_connected = False

        # 🌟 初始化时就建好长连接，全局复用
        self._init_realtime_tts()

        # 初始化清理标志
        self._cleaned_up = False

        # 心跳保活机制
        self._stop_heartbeat = False
        self._heartbeat_thread = None
        self._start_heartbeat()

        self._initialized = True

        # 注册退出清理函数（atexit 兜底）
        atexit.register(self._cleanup)

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
        print("[HEARTBEAT] [TTS] 心跳保活线程已启动（间隔30秒）")

    def _stop_heartbeat_thread(self):
        """停止心跳线程"""
        if not self._heartbeat_thread:
            return

        self._stop_heartbeat = True
        if self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=5.0)
            if self._heartbeat_thread.is_alive():
                print("[WARN] [TTS] 心跳线程未能正常停止")
            else:
                print("[HEARTBEAT] [TTS] 心跳线程已停止")
        self._heartbeat_thread = None

    def _heartbeat_loop(self):
        """心跳循环，每30秒检查一次连接状态"""
        import time
        heartbeat_interval = 30  # 秒

        while not self._stop_heartbeat:
            time.sleep(heartbeat_interval)

            if self._stop_heartbeat:
                break

            try:
                # 检查连接状态
                if hasattr(self, '_is_connected') and self._is_connected:
                    # 连接正常，记录日志（减少日志噪音，只在调试时开启）
                    # print("[HEARTBEAT] [TTS] 连接状态正常")
                    pass
                else:
                    print("[HEARTBEAT] [TTS] 检测到连接断开，尝试重新连接...")
                    # 尝试重新连接
                    self._ensure_connected()
            except Exception as e:
                print(f"[ERROR] [TTS] 心跳检查异常: {e}")
                # 继续循环，下次再试

    def _cleanup(self):
        """清理WebSocket连接（安全，可多次调用）"""
        # 防止重复清理
        if hasattr(self, '_cleaned_up') and self._cleaned_up:
            return

        try:
            if hasattr(self, '_tts') and self._tts:
                try:
                    print("[CONN] [TTS] 正在关闭WebSocket连接...")
                    self._tts.close()
                    print("[OK] [TTS] WebSocket连接已关闭")
                except Exception as e:
                    print(f"[WARN]  [TTS] 关闭连接时出错: {e}")
                finally:
                    self._is_connected = False
                    self._tts = None
        finally:
            # 停止心跳线程
            if hasattr(self, '_stop_heartbeat'):
                self._stop_heartbeat_thread()
            self._cleaned_up = True

    def __del__(self):
        """析构函数，确保连接被清理"""
        self._cleanup()

    def close(self):
        """公共方法：手动关闭连接"""
        self._cleanup()

    def _init_realtime_tts(self):
        """初始化底层连接实例（不包含会话配置）"""
        # 音频数据和错误信息现在由回调类管理

        class ReusableCallback(QwenTtsRealtimeCallback):
            def __init__(self, outer_self):
                super().__init__()
                self.outer_self = outer_self
                self.complete_event = threading.Event()
                self._audio_chunks = []
                self._error_msg = None

            def on_open(self) -> None:
                print("[TTS] WebSocket连接已建立")
                # 更新外部实例的连接状态
                self.outer_self._is_connected = True

            def on_close(self, close_status_code, close_msg) -> None:
                print(f"[TTS] 连接关闭 code={close_status_code}, msg={close_msg}")
                # 更新外部实例的连接状态
                self.outer_self._is_connected = False
                # 无论正常关闭还是异常关闭都释放等待
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
                """等待合成完成"""
                self.complete_event.wait(timeout)

            def get_audio_data(self):
                """获取合成的音频数据"""
                return b''.join(self._audio_chunks)

            def reset(self):
                """重置状态用于下一次合成"""
                self._audio_chunks.clear()
                self._error_msg = None
                self.complete_event.clear()

        self._callback = ReusableCallback(self)

        # 在创建实例前确保API密钥已设置（与成功测试程序一致）
        dashscope.api_key = TTSConfig.API_KEY
        print(f"[KEY] [TTS] 使用API密钥: {TTSConfig.API_KEY[:8]}...")

        # 使用配置中的模型和音色
        self._tts = QwenTtsRealtime(
            model=TTSConfig.MODEL,  # 从配置读取
            callback=self._callback,
            url=TTSConfig.BASE_URL
        )

        try:
            # 尝试连接，使用指数退避重试
            max_retries = 5
            base_delay = 2  # 初始延迟2秒

            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        # 指数退避：2, 4, 8, 16, 32秒
                        delay = base_delay * (2 ** (attempt - 1))
                        print(f"[RETRY] [TTS] 第 {attempt + 1}/{max_retries} 次尝试连接，等待 {delay} 秒后重试...")
                        time.sleep(delay)

                    self._tts.connect()
                    self._is_connected = True
                    self._is_speaking = False  # 🌟 加个锁，防止并发
                    print("[CONN] [TTS] WebSocket 底层长连接已建立！")
                    break  # 连接成功，退出重试循环

                except Exception as e:
                    error_msg = str(e)
                    print(f"[ERROR] [TTS] 连接尝试 {attempt + 1}/{max_retries} 失败: {error_msg}")

                    # 检查是否是已知的连接问题
                    if "401" in error_msg or "Unauthorized" in error_msg:
                        print("[ERROR] [TTS] 认证失败，无需重试")
                        self._is_connected = False
                        raise RuntimeError(f"TTS认证失败: {error_msg}")

                    # 检查是否是端口/连接相关问题
                    port_errors = ["address already in use", "port", "socket", "connection refused", "timeout"]
                    if any(err in error_msg.lower() for err in port_errors):
                        print(f"[WARN]  [TTS] 检测到端口/连接问题，可能是之前的连接未完全关闭")
                        if attempt < max_retries - 1:
                            print(f"[TIP] 建议：等待 {base_delay * (2 ** attempt)} 秒让系统释放资源")

                    # 如果是最后一次尝试，抛出异常
                    if attempt == max_retries - 1:
                        self._is_connected = False
                        # 清理连接对象
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
        """确保TTS连接处于活动状态，如果断开则尝试重新连接"""
        if not hasattr(self, '_is_connected') or not self._is_connected:
            print("[CONN] [TTS] 连接已断开，尝试重新连接...")
            try:
                # 清理旧的连接
                if hasattr(self, '_tts') and self._tts:
                    try:
                        self._tts.close()
                    except:
                        pass

                # 重新初始化连接
                self._init_realtime_tts()
                # 重置清理标志，因为现在有了新的连接
                self._cleaned_up = False
                print("[OK] [TTS] 重新连接成功")
            except Exception as e:
                print(f"[ERROR] [TTS] 重新连接失败: {e}")
                raise RuntimeError(f"TTS重新连接失败: {str(e)}")

    def _synthesize_with_retry(self, text: str, emotion: str = "neutral") -> tuple:
        """单次合成（每次都会重置会话状态）"""
        import re
        import time

        # 0. 确保连接正常
        self._ensure_connected()

        # 1. 洗文本
        text = re.sub(r'[（(][^）)]*[）)]', '', text)
        text = text.replace('...', '。').replace('…', '。')
        text = re.sub(r'\s+', '', text)
        text = text.strip('，。！？、,!?')
        if not text:
            raise ValueError("清洗后文本为空")

        # 🌟 2. 防并发锁：如果上一句还没播完，直接拒绝
        print(f"[DEBUG] [TTS] 检查并发锁: _is_speaking={self._is_speaking}")
        if self._is_speaking:
            raise RuntimeError("上一句话还没合成完，请稍后再试")

        self._is_speaking = True
        print(f"[DEBUG] [TTS] 获取锁，开始合成: '{text[:30]}...'")

        # 🌟 3. 每次合成前，重置回调状态
        self._callback.reset()

        try:
            print(f"[DEBUG] [TTS] 使用voice: {TTSConfig.voice}")
            self._tts.update_session(
                voice=TTSConfig.voice,  # 从配置读取
                response_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
                mode='server_commit'
            )

            self._tts.append_text(text)
            time.sleep(0.1)  # 给服务器一点处理时间
            self._tts.finish()

            # 4. 等待完成
            self._callback.wait_for_finished(timeout=15)

            # 5. 检查错误
            if self._callback._error_msg:
                raise RuntimeError(f"TTS合成错误: {self._callback._error_msg}")

            all_audio = self._callback.get_audio_data()
            if len(all_audio) < 100:
                self._is_connected = False
                raise RuntimeError(f"TTS 返回空音频，可能连接已断开")

            # 5. 算口型
            sample_rate = 24000
            mouth_frames = []
            frame_bytes = int(sample_rate * 0.01) * 2
            for i in range(0, len(all_audio), frame_bytes):
                chunk = all_audio[i:i + frame_bytes]
                if len(chunk) < 4: break
                samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                rms = float(np.sqrt(np.mean(samples ** 2)))
                mouth = min(1.0, rms * 5.0)
                if mouth_frames:
                    mouth = 0.3 * mouth_frames[-1]['v'] + 0.7 * mouth
                mouth_frames.append({'t': round(i / 2 / sample_rate, 3), 'v': round(mouth, 3)})

            # 延迟诊断：第一句合成完成时间戳
            synthesis_complete_time = time.time() * 1000  # 毫秒
            print(f"[延迟诊断] 第一句合成完成时间戳: {synthesis_complete_time:.2f} ms (文本: '{text[:30]}...')")

            return all_audio, mouth_frames
            
        finally:
            # 无论成功失败，都要释放锁
            self._is_speaking = False
            print(f"[DEBUG] [TTS] 释放锁，合成完成")
