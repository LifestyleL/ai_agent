"""
VLM 客户端：调用 Qwen-VL 模型，一次性描述屏幕截图
无状态：创建 → describe(base64) → 返回描述文字 → 销毁
"""
from __future__ import annotations

from core.llm.llm_api import LLMAPI
import config


_VLM_SYSTEM = (
    "你正在看用户的屏幕截图。用口语化、自然的中文，"
    "用一句话描述屏幕上主要显示的内容。"
    "像朋友一样随口说：'你在看...' '屏幕上显示着...'"
    "不要用'这张图片显示'这类元描述。"
    "**禁止描述屏幕上出现的任何动漫角色、猫耳少女、看板娘等二次元形象**——"
    "那是我自己的Live2D虚拟形象，不是屏幕内容。"
    "只看用户在做什么：写什么代码、玩什么游戏、看什么网页等。不超过40字。"
)


class VLMClient:
    """无状态 VLM 客户端"""

    def __init__(self):
        api_key = _read_api_key()
        base_url = getattr(config, "VISION_BASE_URL",
                           "https://dashscope.aliyuncs.com/compatible-mode/v1")
        model = getattr(config, "VISION_MODEL", "qwen-vl-plus")
        self._api = LLMAPI(api_key=api_key, base_url=base_url, model=model, timeout=30)

    def describe(self, base64_image: str) -> str:
        """调用 VLM 返回中文描述。失败返回空字符串。"""
        messages = [
            {"role": "system", "content": _VLM_SYSTEM},
            {"role": "user", "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                {"type": "text", "text": "简要描述屏幕上显示的内容"},
            ]},
        ]
        try:
            result = self._api.chat(messages, temperature=0.3)
            if "error" in result:
                print(f"[VLMClient] API 错误: {result['error']}")
                return ""
            text = result["choices"][0]["message"]["content"].strip()
            # 截断过长描述
            max_chars = getattr(config, "VISION_MAX_DESCRIPTION_CHARS", 120)
            if len(text) > max_chars:
                text = text[:max_chars] + "..."
            return text
        except Exception as e:
            print(f"[VLMClient] 调用失败: {e}")
            return ""


def _read_api_key() -> str:
    # 优先用独立的 VISION_API_KEY，fallback 到 TTS 共用的 DASHSCOPE_API_KEY
    import os
    env_key = getattr(config, "VISION_API_KEY_ENV", "DASHSCOPE_API_KEY")
    return os.environ.get(env_key, "") or getattr(config, "DASHSCOPE_API_KEY", "")
