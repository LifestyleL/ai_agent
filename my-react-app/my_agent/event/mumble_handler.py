"""
潜意识流播报处理器：解决DeepSeek思考时的空缺

0 LLM调用，纯字典匹配，嘴比脑子快的"嘟囔"。
当DeepSeek处理任务时，通过SUBCONSCIOUS_ACTION事件触发简短语气词。
"""

import time
import random
from .event_bus import event_bus, EventType, Event, event_handler

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

# 上次嘟囔时间
_last_mumble_time = 0


@event_handler(EventType.SUBCONSCIOUS_ACTION)
def handle_subconscious(event: Event):
    """处理潜意识动作事件"""
    global _last_mumble_time

    # 铁律：无论DeepSeek内部多急，Qwen最多每7秒才嘟囔一次。保持从容。
    now = time.time()
    if now - _last_mumble_time < 7.0:
        return

    action = event.data.get("action")
    if not action:
        return

    templates = MUMBLE_TEMPLATES.get(action)
    if not templates:
        # 如果没有匹配的动作，使用默认的"thinking"
        templates = MUMBLE_TEMPLATES.get("thinking", ["让我想想……"])

    _last_mumble_time = now
    mumble = random.choice(templates)

    print(f"[MumbleHandler] 嘟囔: '{mumble}' (触发动作: {action})")

    # 直接发TTS，不需要经过Qwen大脑，这就是嘴比脑子快的"嘟囔"
    event_bus.publish(
        EventType.TTS_REQUESTED,
        source="mumble_handler",
        text=mumble,
        emotion="neutral",
        priority=5,  # 较高优先级，可以打断其他低优先级TTS
        timestamp=now
    )


def trigger_mumble(action: str, source: str = "manual"):
    """
    手动触发嘟囔（供外部调用）

    Args:
        action: 动作类型，必须是MUMBLE_TEMPLATES中的键
        source: 触发源
    """
    if action not in MUMBLE_TEMPLATES:
        print(f"[MumbleHandler] 警告: 未知的动作类型 '{action}'")
        return

    event_bus.publish(
        EventType.SUBCONSCIOUS_ACTION,
        source=source,
        action=action,
        timestamp=time.time()
    )


def register_mumble_handler():
    """注册嘟囔处理器（已通过装饰器自动注册，此函数用于显式初始化）"""
    print("[MumbleHandler] 潜意识嘟囔处理器已注册")
    # 装饰器已自动注册，这里只是打印日志
    return True