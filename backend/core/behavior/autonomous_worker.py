"""
AI自驱动冲浪：取代旧待机独白，实现Agent的"后台生活"

当自驱力满值时，DeepSeek去查Qwen喜欢的东西，查到后丢给Qwen念。
"""

import random
import asyncio
import threading
from datetime import datetime
from typing import Optional
from core.event.event_bus import event_bus, EventType, Event, event_handler
from .persona import Persona
from core.memory.memory_core import MemoryCore

# 导入工具调用函数
try:
    from core.agent.agent_brain import call_tool
except ImportError:
    print("[AutonomousWorker] 警告: 无法导入call_tool，将使用模拟调用")
    call_tool = None

# 全局人设实例
_persona: Optional[Persona] = None
_running = False
_lock = threading.Lock()


def get_persona() -> Persona:
    """获取人设单例"""
    global _persona
    if _persona is None:
        _persona = Persona()
    return _persona


# [V1→V3] 旧自驱力已由 SpontaneousEngine 接管
# @event_handler(EventType.SPONTANEOUS_ACTION_TRIGGERED)
# def handle_spontaneous_action(event: Event):
#     """
#     内驱力满了，去干点自己喜欢的事
#
#     流程：
#     1. 从人设喜好里随机挑一个
#     2. DeepSeek默默搜索相关知识
#     3. 把发现扔给Qwen处理
#     """
#     global _running
#
#     # 防止并发处理多个自发动作
#     with _lock:
#         if _running:
#             print("[AutonomousWorker] 已在处理自发动作，跳过")
#             return
#
#         _running = True
#
#     try:
#         print("[AutonomousEngine] 内驱力溢出，开始后台冲浪...")
#
#         # 0. 检查是否需要冲浪回顾
#         surfing_content = MemoryCore.load_files(["surfing_memories.md"])
#         if surfing_content:
#             # 按 ## 切割计算条目数
#             entries = [entry.strip() for entry in surfing_content.split("## ") if entry.strip()]
#             entry_count = len(entries)
#             print(f"[AutonomousWorker] 冲浪草稿纸已有 {entry_count} 条记录")
#             if entry_count >= 5:
#                 print("[AutonomousWorker] 草稿纸已满5条，触发冲浪回顾，跳过本次新搜索")
#                 event_bus.publish(
#                     EventType.SURFING_REVIEW_NEEDED,
#                     source="autonomous_worker",
#                     entry_count=entry_count,
#                     timestamp=event.timestamp
#                 )
#                 return
#         else:
#             print("[AutonomousWorker] 冲浪草稿纸为空，继续新搜索")
#
#         # 1. 从人设喜好里随机挑一个
#         persona = get_persona()
#         if not hasattr(persona, 'likes') or not persona.likes:
#             print("[AutonomousWorker] 警告: 人设没有定义likes")
#             return
#
#         topic = random.choice(persona.likes)
#         print(f"[AutonomousWorker] 选择主题: {topic}")
#
#         # 2. 构建搜索任务
#         query = f"关于'{topic}'的最新有趣知识或动态，总结一段50字以内的冷知识。"
#         print(f"[AutonomousWorker] 构建查询: {query}")
#
#         # 3. DeepSeek默默干活
#         # 注意：这里不要触发SUBCONSCIOUS_ACTION事件，这是后台偷懒
#         discovery = _call_deepseek_for_discovery(topic, query)
#         if not discovery:
#             print("[AutonomousWorker] DeepSeek搜索无结果")
#             return
#
#         print(f"[AutonomousWorker] 发现新知识: {discovery[:100]}...")
#
#         # 4. 将发现追加到冲浪草稿纸
#         now = datetime.now().strftime("%Y-%m-%d %H:%M")
#         entry = f"## {now}\n主题: {topic}\n内容: {discovery}\n"
#         # [V1→V3] 已废弃：冲浪记忆暂不写入
#         # MemoryCore.append_to_file("surfing_memories.md", entry)
#         print(f"[AutonomousWorker] 已追加到冲浪草稿纸: {topic[:30]}...")
#
#         # 5. 把发现扔给Qwen
#         event_bus.publish(
#             EventType.DISCOVERY_MADE,
#             source="autonomous_worker",
#             topic=topic,
#             content=discovery,
#             timestamp=event.timestamp
#         )
#
#         print("[AutonomousWorker] 后台冲浪完成")
#
#     except Exception as e:
#         print(f"[AutonomousWorker] 自发动作异常: {e}")
#         # 偷懒失败了就算了，不打扰用户
#     finally:
#         with _lock:
#             _running = False


def _call_deepseek_for_discovery(topic: str, query: str) -> Optional[str]:
    """
    调用DeepSeek进行后台搜索

    注意：这是后台任务，不要触发嘟囔事件
    """
    if call_tool is None:
        # 模拟返回
        fake_discoveries = [
            f"关于{topic}，最近研究发现它比想象中更有趣。",
            f"没想到{topic}还有这么多门道，真是有意思。",
            f"{topic}的最新动态显示，这个领域正在快速发展。",
            f"原来{topic}背后还有这样的历史，长见识了。",
        ]
        return random.choice(fake_discoveries)

    try:
        # TODO: 实现实际的DeepSeek调用
        # 这里需要根据实际工具调用机制实现
        # 暂时返回模拟结果
        fake_discoveries = [
            f"关于{topic}，最近研究发现它比想象中更有趣。",
            f"没想到{topic}还有这么多门道，真是有意思。",
            f"{topic}的最新动态显示，这个领域正在快速发展。",
            f"原来{topic}背后还有这样的历史，长见识了。",
        ]
        return random.choice(fake_discoveries)

        # 实际调用示例（需根据实际工具调整）:
        # result = call_tool("web_search", {"query": query}, llm=None)
        # return _extract_content_from_result(result)

    except Exception as e:
        print(f"[AutonomousWorker] DeepSeek调用失败: {e}")
        return None


def _extract_content_from_result(result) -> str:
    """从工具调用结果中提取内容"""
    if isinstance(result, str):
        return result
    elif isinstance(result, dict):
        # 尝试从常见字段提取
        for field in ["content", "text", "result", "summary", "answer"]:
            if field in result and isinstance(result[field], str):
                return result[field]
        return str(result)
    else:
        return str(result)


def register_autonomous_worker():
    """注册自主工作者（已通过装饰器自动注册，此函数用于显式初始化）"""
    print("[AutonomousWorker] AI自驱动冲浪处理器已注册")
    # 装饰器已自动注册，这里只是打印日志
    return True