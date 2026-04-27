import queue
import threading
import time
import random
from typing import Dict, Any
from core.event.event_bus import EventType


class TTSManager:
    """TTS 播报管理：队列、后台消费线程、流式断句、情绪管理"""

    _BUFFER_SENTENCES = [
        "让我想想……",
        "嗯……我想想啊……",
        "稍等一下，我回忆回忆……",
        "等等，让我想想这件事……",
        "这个嘛……我想想……",
    ]

    def __init__(self, voice, event_bus, max_queue_size=10):
        self.voice = voice
        self._event_bus = event_bus

        self._tts_queue = queue.Queue(maxsize=max_queue_size)
        self._current_emotion = "neutral"
        self._tts_buffer = ""

        self._tts_worker_thread = threading.Thread(target=self._tts_worker_loop, daemon=True)
        self._tts_worker_thread.start()
        print("[TTSManager] TTS 后台消费线程已启动")

    @property
    def current_emotion(self):
        return self._current_emotion

    @current_emotion.setter
    def current_emotion(self, value):
        self._current_emotion = value

    @property
    def tts_queue(self):
        return self._tts_queue

    def _get_buffer_sentence(self) -> str:
        return random.choice(self._BUFFER_SENTENCES)

    def speak_final_text(self, text: str):
        """极简外部播报入口：专供状态机微观流程使用"""
        if not text:
            return
        try:
            tts_item = {"text": text, "emotion": self._current_emotion}
            self._tts_queue.put(tts_item, timeout=2.0)
            print(f"[TTS] [状态机入口] 文本已入队: '{text[:30]}...' (情感: {self._current_emotion})")
        except queue.Full:
            print(f"[WARN] [TTS_Queue] 队列已满，丢弃状态机文本: '{text[:20]}...'")
        except Exception as e:
            print(f"[TTS Error] 状态机播报失败: {e}")

    def on_spontaneous_speech(self, text: str, context: Dict[str, Any]):
        """自驱动引擎回调：将主动发言送入TTS队列"""
        if not text.strip():
            return

        emotion = context.get("emotion", "neutral")
        priority = context.get("priority", 1)
        trigger_reason = context.get("trigger_reason", "")

        print(f"[SpontaneousEngine] 主动发言: '{text}'")
        print(f"  情感: {emotion}, 优先级: {priority}, 触发原因: {trigger_reason}")

        self._current_emotion = emotion

        tts_item = {"text": text, "emotion": emotion}
        try:
            self._tts_queue.put(tts_item, timeout=2.0)
            print(f"[Queue] [TTS] 主动发言已入队: '{text[:30]}...' (情感: {emotion})")
        except queue.Full:
            print(f"[WARN] [TTS_Queue] 队列已满，丢弃主动发言: '{text[:20]}...'")
        except Exception as e:
            print(f"[ERROR] 主动发言入队失败: {e}")

    def enqueue_text(self, text: str, emotion: str = None):
        """通用文本入队入口"""
        if not text.strip():
            return
        emotion = emotion or self._current_emotion
        tts_item = {"text": text, "emotion": emotion}
        try:
            self._tts_queue.put(tts_item, timeout=2.0)
            print(f"[Queue] [TTS] 文本已入队: '{text[:30]}...' (情感: {emotion})")
        except queue.Full:
            print(f"[WARN] [TTS_Queue] 队列已满，丢弃: '{text[:20]}...'")

    def process_stream_chunk(self, chunk_data: dict, full_text_received: str, user_input: str, frontend_bridge):
        """处理流式chunk：文字推前端，句子入队列"""
        chunk_type = chunk_data.get("type")

        if chunk_type == "thinking":
            thinking_text = chunk_data.get("text", "")
            print(f"[Stream] [思考提示] {thinking_text}")
            frontend_bridge.send_text_to_frontend(thinking_text, "thinking")

        elif chunk_type == "tool":
            buffer = self._get_buffer_sentence()
            print(f"[TTS掩护] 推送缓冲语：{buffer}")

            tool_name = chunk_data.get("tool", "")
            tool_params = chunk_data.get("params", {})
            print(f"[Tool] 工具调用: {tool_name}, 参数: {tool_params}")

        elif chunk_type == "chunk":
            chunk_text = chunk_data.get("text", "")
            print(chunk_text, end="", flush=True)
            frontend_bridge.send_text_to_frontend(chunk_text, "chunk")

            full_text_received += chunk_text

            chunk_text = chunk_text.replace("\n", "").replace("\r", "")
            self._tts_buffer += chunk_text

            first_end_pos = -1
            for punc in ["。", "！", "？"]:
                pos = self._tts_buffer.find(punc)
                if pos != -1:
                    if first_end_pos == -1 or pos < first_end_pos:
                        first_end_pos = pos

            if first_end_pos != -1:
                sentence = self._tts_buffer[:first_end_pos + 1]
                self._tts_buffer = self._tts_buffer[first_end_pos + 1:]
                try:
                    tts_item = {"text": sentence, "emotion": self._current_emotion}
                    self._tts_queue.put(tts_item, timeout=2.0)
                    queue_time = time.time() * 1000
                    print(f"[延迟诊断] 第一句句子已入队时间戳: {queue_time:.2f} ms (文本: '{sentence[:30]}...')")
                    print(f"[Queue] [TTS] 句子已入队: '{sentence[:30]}...' (情感: {self._current_emotion})")
                except queue.Full:
                    print(f"[WARN] [TTS_Queue] 队列已满，丢弃句子: '{sentence[:20]}...'")

        elif chunk_type == "done":
            final_emotion = chunk_data.get("emotion", "neutral")

            if self._tts_buffer.strip():
                tail_text = self._tts_buffer
                self._tts_buffer = ""
                try:
                    tts_item = {"text": tail_text, "emotion": final_emotion}
                    self._tts_queue.put(tts_item, timeout=2.0)
                    tail_queue_time = time.time() * 1000
                    print(f"[延迟诊断] 尾巴句子已入队时间戳: {tail_queue_time:.2f} ms (文本: '{tail_text[:30]}...')")
                    print(f"[Queue] [TTS] 尾巴句子已入队: '{tail_text[:30]}...' (情感: {final_emotion})")
                except queue.Full:
                    print(f"[WARN] [TTS_Queue] 队列已满，丢弃尾巴句子: {tail_text[:20]}...'")

            self._current_emotion = final_emotion

            final_action = chunk_data.get("action", "")
            if final_action:
                print(f"[Action] [动作] {final_action}")

            return True, full_text_received

        return False, full_text_received

    def _tts_worker_loop(self):
        """后台线程：从队列取句子，同步调用 TTS，确保一句播完才播下一句"""
        while True:
            item = self._tts_queue.get()

            if item is None:
                self._tts_queue.task_done()
                break

            if isinstance(item, dict):
                text = item.get("text", "")
                emotion = item.get("emotion", self._current_emotion)
            else:
                text = item
                emotion = self._current_emotion

            if not text.strip():
                self._tts_queue.task_done()
                continue

            try:
                self.voice._tts_done_event.clear()

                self._event_bus.publish(
                    EventType.TTS_REQUESTED,
                    source="_tts_worker_loop",
                    text=text,
                    emotion=emotion,
                    timestamp=time.time()
                )

                if not self.voice._tts_done_event.wait(timeout=60):
                    print(f"[ERROR] [TTS_Queue] 句子合成超时(60s): '{text[:30]}...' (情感: {emotion})")
                else:
                    print(f"[OK] [TTS_Queue] 句子合成完成: '{text[:30]}...' (情感: {emotion})")

            except Exception as e:
                print(f"[ERROR] [TTS_Queue] 合成出错: {e}")
            finally:
                self._tts_queue.task_done()

    def shutdown(self):
        """关闭 TTS 后台线程"""
        print("[TTSManager] 正在关闭 TTS 后台线程...")
        try:
            self._tts_queue.put(None, timeout=2.0)
        except queue.Full:
            print("[WARN] TTS 队列已满，强制关闭")
        try:
            self._tts_worker_thread.join(timeout=2)
        except Exception:
            pass
        if self._tts_worker_thread.is_alive():
            print("[WARN] TTS 后台线程未能正常结束（非致命）")
        else:
            print("[OK] TTS 后台线程已关闭")
