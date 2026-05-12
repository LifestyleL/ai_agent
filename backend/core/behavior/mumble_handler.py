"""
潜意识流播报处理器：解决DeepSeek思考时的空缺

0 LLM调用，纯字典匹配，嘴比脑子快的"嘟囔"。
当DeepSeek处理任务时，通过SUBCONSCIOUS_ACTION事件触发简短语气词。

改造为类实例，消除模块级全局变量。
"""

import time
import random
from core.event.event_bus import event_bus, EventType, Event

# 嘟囔模板库
MUMBLE_TEMPLATES = {
    "analyzing": [
        "让我看看……",
        "嗯……稍微有点复杂。",
        "等下，我先理一下。",
        "这个我得仔细看看……",
        "唔，有点意思……"
    ],
    "searching": [
        "我找找资料……",
        "好像得去查一下。",
        "我翻翻看啊。",
        "等我去查查看……",
        "找找有没有相关信息……"
    ],
    "coding": [
        "我写一下试试……",
        "这里逻辑有点绕。",
        "马上好。",
        "调试一下看看……",
        "代码写得差不多了……"
    ],
    "frustrated": [
        "啊？报错了……",
        "奇怪，明明对的啊。",
        "等下，这不对劲。",
        "咦？怎么不对……",
        "这有点奇怪……"
    ],
    "insight": [
        "哦！我知道了。",
        "等等，好像有点眉目了。",
        "原来是这样。",
        "啊哈，明白了！",
        "这下清楚了。"
    ],
    "done": [
        "搞定了。",
        "弄完了，你看下。",
        "完成了。",
        "可以了。",
        "好了。"
    ],
    "thinking": [
        "让我想想……",
        "思考中……",
        "嗯……",
        "在想呢……",
        "琢磨一下……"
    ]
}


class MumbleHandler:
    """嘟囔处理器（类实例，无全局状态）"""

    def __init__(self, tts_queue):
        self._tts_queue = tts_queue
        self._last_mumble_time = 0

    def register(self, event_bus) -> None:
        """注册到事件总线"""
        event_bus.subscribe(EventType.SUBCONSCIOUS_ACTION, self._handle)
        print("[MumbleHandler] 嘟囔处理器已注册")

    def _handle(self, event: Event) -> None:
        """处理潜意识动作事件"""
        # 频率限制：最多每7秒才嘟囔一次
        now = time.time()
        if now - self._last_mumble_time < 7.0:
            return

        action = event.data.get("action")
        if not action:
            return

        templates = MUMBLE_TEMPLATES.get(action)
        if not templates:
            templates = MUMBLE_TEMPLATES.get("thinking", ["让我想想……"])

        self._last_mumble_time = now
        mumble = random.choice(templates)

        print(f"[MumbleHandler] 嘟囔: '{mumble}' (触发动作: {action})")

        # 封死后门：强制所有声音走统一队列
        try:
            import queue
            if self._tts_queue is not None:
                tts_item = {"text": mumble, "emotion": "neutral"}
                self._tts_queue.put(tts_item, timeout=1.0)
                print(f"[MumbleHandler] 嘟囔已入队: '{mumble}'")
            else:
                print(f"[MumbleHandler] TTS队列尚未注入，跳过嘟囔")
        except queue.Full:
            print(f"[MumbleHandler] TTS队列已满，丢弃嘟囔: '{mumble}'")
        except Exception as e:
            print(f"[MumbleHandler] 嘟囔入队失败: {e}")

    @staticmethod
    def trigger_mumble(action: str, source: str = "manual"):
        """手动触发嘟囔（供外部调用）"""
        if action not in MUMBLE_TEMPLATES:
            print(f"[MumbleHandler] 警告: 未知的动作类型 '{action}'")
            return

        event_bus.publish(
            EventType.SUBCONSCIOUS_ACTION,
            source=source,
            action=action,
            timestamp=time.time()
        )


# 向后兼容的模块级初始化函数（过渡期用）
def init_mumble_handler(tts_queue):
    """向后兼容——新代码应使用 MumbleHandler 类 + DI 容器"""
    print("[MumbleHandler] 已通过模块级函数初始化（旧路径）")
    import builtins
    if not hasattr(builtins, '_global_mumble_handler'):
        handler = MumbleHandler(tts_queue=tts_queue)
        from core.event.event_bus import event_bus
        handler.register(event_bus)
        setattr(builtins, '_global_mumble_handler', handler)
