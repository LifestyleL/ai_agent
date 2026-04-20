# tts_config.py
# TTS特定配置（情绪预设、指令等）
# API配置现在统一在config.py中管理

import sys
import os

# 添加项目根目录到Python路径，以便导入config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from config import DASHSCOPE_API_KEY, TTS_MODEL, TTS_VOICE, TTS_BASE_URL
except ImportError:
    # 回退到环境变量（兼容旧版本）
    import os
    DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
    TTS_MODEL = os.environ.get("TTS_MODEL", "qwen3-tts-vd-realtime-2026-01-15")
    TTS_VOICE = os.environ.get("TTS_VOICE", "qwen-tts-vd-live2d_girl-voice-20260413174053978-a5da")
    TTS_BASE_URL = os.environ.get("TTS_BASE_URL", "wss://dashscope.aliyuncs.com/api-ws/v1/realtime")

class TTSConfig:
    # ─── API配置（从统一配置导入） ───
    API_KEY = DASHSCOPE_API_KEY
    MODEL = TTS_MODEL
    voice = TTS_VOICE
    BASE_URL = TTS_BASE_URL
    
    # voice = "longanyang"#少年
    # ✅ 加上这个
    base_instructions = "自然流畅地朗读，语气亲切"
    # ─── 情绪预设（自然语言指令，直接注入 instructions） ───
    emotion_presets = {
        # ─── 英文 Key ───
        "cute":    ("更加俏皮可爱，语气上扬", "活泼"),
        "happy":   ("开心愉快，语速稍快，声音明亮", "开心"),
        "sad":     ("有些低落，语速放慢，声音轻柔", "伤心"),
        "angry":   ("有些生气，语速加快，语气加重", "生气"),
        "fear":    ("紧张害怕，声音有些发抖，轻声", "恐惧"),
        "gentle":  ("温柔轻柔，语速缓慢，像哄人一样", "温柔"),
        "serious": ("认真严肃，语气平稳", "严肃"),
        "neutral": ("", "平静"),
        # ─── 中文 Key（兼容旧代码） ───
        "可爱": ("更加俏皮可爱，语气上扬", "活泼"),
        "开心": ("开心愉快，语速稍快，声音明亮", "开心"),
        "伤心": ("有些低落，语速放慢，声音轻柔", "伤心"),
        "生气": ("有些生气，语速加快，语气加重", "生气"),
        "恐惧": ("紧张害怕，声音有些发抖，轻声", "恐惧"),
        "温柔": ("温柔轻柔，语速缓慢，像哄人一样", "温柔"),
        "严肃": ("认真严肃，语气平稳", "严肃"),
        "平静": ("", "平静"),
    }

    # ─── 网络配置 ───
    proxy = None

    # ─── viseme 生成参数 ───
    # ⚠️ 以下两个参数现在不需要了，可以删除或保留
    viseme_min_gap = 0.08
    viseme_bytes_per_ms = 16.0  # 这个是 MP3 的估算值，PCM 不适用

    # ─── 启动校验 ───
    @classmethod
    def validate(cls):
        if not cls.API_KEY:  # ✅ 现在检查的是正确的属性名
            raise EnvironmentError(
                "DASHSCOPE_API_KEY 未设置。\n"
                "Windows: set DASHSCOPE_API_KEY=sk-xxx && python main.py\n"
                "Linux:   export DASHSCOPE_API_KEY=sk-xxx && python main.py\n"
                "请从阿里云DashScope控制台获取API密钥：https://dashscope.console.aliyun.com/"
            )

        # 检查API密钥格式
        if not cls.API_KEY.startswith("sk-"):
            print(f"⚠️ 警告：API密钥格式异常，应以'sk-'开头，当前: {cls.API_KEY[:8]}...")
            # 不抛出错误，因为可能有其他格式
