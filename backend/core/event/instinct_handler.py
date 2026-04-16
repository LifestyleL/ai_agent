"""
本能行为处理器：处理舒适度模型触发的本能冲动

订阅 INSTINCT_TRIGGERED 事件，基于人设和状态生成行为响应。
"""

import asyncio
import time
from .event_bus import event_bus, EventType, event_handler, Event
from core.memory_core import MemoryCore
from .persona import get_persona
from .comfort_model import get_comfort_model


# 全局LLM实例（用于生成本能话语）
_llm_instance = None

# 缓存上一次说的本能话，避免重复
_last_instinct_text = ""
_last_instinct_time = 0


def init_instinct_handler(llm_qwen):
    """
    初始化本能处理器，设置LLM实例

    Args:
        llm_qwen: LLMAPI实例，用于生成本能话语
    """
    global _llm_instance
    _llm_instance = llm_qwen
    print(f"[InstinctHandler] 本能处理器已初始化，LLM实例: {type(llm_qwen).__name__}")


@event_handler(EventType.INSTINCT_TRIGGERED)
async def handle_instinct(event: Event):
    """收到本能冲动事件，基于人设生成自然语言响应"""
    global _last_instinct_text, _last_instinct_time

    urge_type = event.data.get("urge_type")
    comfort_snapshot = event.data.get("comfort_snapshot", "")
    comfort_level = event.data.get("comfort_level", 0)

    print(f"[InstinctHandler] 处理本能冲动: {urge_type}, 舒适度: {comfort_level:.1f}")
    print(f"  状态快照: {comfort_snapshot}")

    now = time.time()

    # 冷却：同一句话10分钟内不说第二次
    if now - _last_instinct_time < 600:
        print(f"  [冷却] 距离上次本能话语不足10分钟，跳过")
        return

    # 获取人设和舒适度模型
    persona = get_persona()
    comfort_model = get_comfort_model()

    # 如果没有LLM实例，使用预设文本作为后备
    if _llm_instance is None:
        print(f"  [WARN] LLM实例未初始化，使用预设文本")
        _use_preset_response(event, urge_type, comfort_level)
        return

    try:
        # 获取当前舒适度快照
        current_snapshot = comfort_model.snapshot() if hasattr(comfort_model, 'snapshot') else comfort_snapshot

        # 构建人设化的 prompt
        prompt = persona.get_instinct_prompt(urge_type, current_snapshot)
        print(f"  [Prompt] 生成本能话语prompt ({len(prompt)} 字符)")
        if len(prompt) > 300:
            print(f"  [Prompt预览] {prompt[:250]}...")

        # 调用 LLM 生成（用轻量调用，不需要双模型协作）
        # 使用ask方法，temperature=0.9让回复更有创造性
        text = _llm_instance.ask(prompt, temperature=0.9)

        # 去掉可能的引号包裹
        text = text.strip().strip('"').strip("'").strip("'")

        # 去重检查
        if text == _last_instinct_text:
            print(f"  [去重] 与上次本能话语相同，跳过")
            return

        # 截断过长的文本（避免TTS过长）
        if len(text) > 100:
            text = text[:97] + "..."

        _last_instinct_text = text
        _last_instinct_time = now

        # 发布 TTS 事件
        event_bus.publish(
            EventType.TTS_REQUESTED,
            source="InstinctHandler.handle_instinct",
            text=text,
            emotion="neutral",
            instinct_type=urge_type,
            comfort_level=comfort_level,
            timestamp=time.time()
        )

        print(f"  [Audio] 人设化本能响应: '{text}'")

        # 记录本能触发
        try:
            MemoryCore.append_to_file("mood_blank.md",
                f"\n[本能触发] {time.strftime('%H:%M:%S')} {urge_type}: {text}")
        except Exception as e:
            print(f"  [WARN] 记录本能触发失败: {e}")

        # 同时记录舒适度更新
        event_bus.publish(
            EventType.COMFORT_UPDATED,
            source="InstinctHandler.handle_instinct",
            instinct_said=text,
            timestamp=time.time()
        )

    except Exception as e:
        # 本能话语生成失败不影响主流程，回退到预设文本
        print(f"  [ERROR] 生成本能话语失败: {e}")
        _use_preset_response(event, urge_type, comfort_level)


def _use_preset_response(event, urge_type, comfort_level):
    """使用预设文本作为后备响应"""
    # 简单的本能响应映射（后备）
    INSTINCT_RESPONSES = {
        "escape": [
            "唔...有点累了，想休息一下",
            "啧，状态不太好，让我缓一缓",
            "感觉有点烦躁，不想继续了",
            "嗯...需要调整一下状态",
            "注意力有点分散，想发会儿呆"
        ],
        "initiative": [
            "诶，精力不错，想做点什么",
            "状态挺好，找点事情做吧",
            "嗯...感觉可以主动做点事",
            "心情不错，想主动一点",
            "有干劲了，想做点什么"
        ]
    }

    responses = INSTINCT_RESPONSES.get(urge_type, [])
    if responses:
        import random
        text = random.choice(responses)
    else:
        # 默认响应
        if urge_type == "escape":
            text = "有点累了，想休息一下"
        elif urge_type == "initiative":
            text = "嗯...想做点什么"
        else:
            text = "感觉有点不一样"

    # 发布TTS请求事件
    event_bus.publish(
        EventType.TTS_REQUESTED,
        source="InstinctHandler.handle_instinct",
        text=text,
        emotion="neutral",
        instinct_type=urge_type,
        comfort_level=comfort_level,
        timestamp=time.time()
    )

    print(f"  [Audio] 预设本能响应: {text}")

    # 记录本能触发（可选）
    try:
        MemoryCore.append_to_file("mood_blank.md",
            f"\n[本能触发] {time.strftime('%H:%M:%S')} {urge_type}: {text}")
    except Exception as e:
        print(f"  [WARN] 记录本能触发失败: {e}")


def setup_instinct_handler():
    """设置本能处理器（显式调用以确保注册）"""
    print("[InstinctHandler] 本能处理器已就绪")
    return True


# 自动设置处理器（但不初始化LLM实例）
setup_instinct_handler()