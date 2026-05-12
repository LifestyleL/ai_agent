"""
本能行为处理器

订阅 INSTINCT_TRIGGERED 事件，基于人设和状态生成行为响应。
改造为类实例，消除模块级全局变量。
"""

import queue
import random
import time
from backend.core.event.event_bus import EventType, Event


# 预设文本映射
INSTINCT_RESPONSES = {
    "escape": [
        "唔...有点累了，想休息一下",
        "啧，状态不太好，让我缓一缓",
        "感觉有点烦躁，不想继续了",
        "嗯...需要调整一下状态",
        "注意力有点分散，想发会儿呆",
    ],
    "initiative": [
        "诶，精力不错，想做点什么",
        "状态挺好，找点事情做吧",
        "嗯...感觉可以主动做点事",
        "心情不错，想主动一点",
        "有干劲了，想做点什么",
    ],
}


class InstinctHandler:
    """本能处理器（类实例，无全局状态）"""

    def __init__(self, llm_api, tts_queue, prompt_builder, drive_model):
        self._llm = llm_api
        self._tts_queue = tts_queue
        self._prompt_builder = prompt_builder
        self._drive_model = drive_model
        self._last_text = ""
        self._last_time = 0

    def register(self, event_bus) -> None:
        """注册到事件总线"""
        event_bus.subscribe(EventType.INSTINCT_TRIGGERED, self._handle)
        print("[InstinctHandler] 本能处理器已注册")

    def _handle(self, event: Event) -> None:
        """处理本能冲动事件"""
        urge_type = event.data.get("urge_type")
        comfort_snapshot = event.data.get("comfort_snapshot", "")
        comfort_level = event.data.get("comfort_level", 0)

        print(f"[InstinctHandler] 本能冲动: {urge_type}, 舒适度: {comfort_level:.1f}")

        now = time.time()
        if now - self._last_time < 600:
            print(f"  [冷却] 距上次不足10分钟，跳过")
            return

        if self._llm is None:
            self._use_preset(urge_type)
            return

        try:
            current_snapshot = (
                self._drive_model.snapshot()
                if hasattr(self._drive_model, 'snapshot')
                else comfort_snapshot
            )
            prompt = self._prompt_builder.build_instinct_prompt(urge_type, current_snapshot)
            text = self._llm.ask(prompt, temperature=0.9)
            text = text.strip().strip('"').strip("'")

            if text == self._last_text:
                print(f"  [去重] 与上次相同，跳过")
                return
            if len(text) > 100:
                text = text[:97] + "..."

            self._last_text = text
            self._last_time = now

            tts_item = {"text": text, "emotion": "neutral"}
            self._tts_queue.put(tts_item, timeout=1.0)
            print(f"[InstinctHandler] 本能响应已入队: '{text}'")

        except Exception as e:
            print(f"[InstinctHandler] LLM 生成失败: {e}")
            self._use_preset(urge_type)

    def _use_preset(self, urge_type: str) -> None:
        """使用预设文本作为后备"""
        responses = INSTINCT_RESPONSES.get(urge_type, ["感觉有点不一样"])
        text = random.choice(responses)
        try:
            self._tts_queue.put({"text": text, "emotion": "neutral"}, timeout=1.0)
            print(f"[InstinctHandler] 预设响应已入队: '{text}'")
        except queue.Full:
            print(f"[InstinctHandler] TTS队列已满，丢弃: '{text}'")
        except Exception as e:
            print(f"[InstinctHandler] 入队失败: {e}")


# 向后兼容的模块级初始化函数（过渡期用）
def init_instinct_handler(llm_api, tts_queue=None):
    """向后兼容——新代码应使用 InstinctHandler 类 + DI 容器"""
    print("[InstinctHandler] 已通过模块级函数初始化（旧路径）")
    # 全局存储实例供旧代码使用
    import builtins
    if not hasattr(builtins, '_global_instinct_handler'):
        from backend.core.behavior.persona import Persona
        from backend.core.behavior.prompt_builder import PromptBuilder
        handler = InstinctHandler(
            llm_api=llm_api,
            tts_queue=tts_queue,
            prompt_builder=PromptBuilder(Persona()),
            drive_model=None,
        )
        from backend.core.event.event_bus import event_bus
        handler.register(event_bus)
        setattr(builtins, '_global_instinct_handler', handler)
