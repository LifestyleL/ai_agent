# 统一API配置管理
import os
from dotenv import load_dotenv

# 加载.env文件（覆盖现有环境变量）
load_dotenv(override=True)

# ─── DeepSeek（工具调用模型） ───
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")           # DeepSeek API密钥
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# ─── 阿里千问（人设对话模型） ───
QWEN_API_KEY = os.environ.get("QWEN_API_KEY", "")                   # 阿里千问API密钥
QWEN_BASE_URL = os.environ.get("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = os.environ.get("QWEN_MODEL", "qwen-max")               # 或 qwen-plus、qwen-turbo等

# ─── 阿里 DashScope TTS（流式音频） ───
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")         # DashScope TTS API密钥
TTS_MODEL = os.environ.get("TTS_MODEL", "qwen3-tts-vd-realtime-2026-01-15")
TTS_VOICE = os.environ.get("TTS_VOICE", "qwen-tts-vd-live2d_girl-voice-20260413174053978-a5da")
TTS_BASE_URL = os.environ.get("TTS_BASE_URL", "wss://dashscope.aliyuncs.com/api-ws/v1/realtime")

# ─── Agent驱动配置 ───
AGENT_IDLE_TIMEOUT = int(os.environ.get("AGENT_IDLE_TIMEOUT", "120"))  # 多久没说话开始独白（秒）
AGENT_IDLE_INTERVAL_MIN = int(os.environ.get("AGENT_IDLE_INTERVAL_MIN", "60"))  # 独白间隔最小值（秒）
AGENT_IDLE_INTERVAL_MAX = int(os.environ.get("AGENT_IDLE_INTERVAL_MAX", "65"))  # 独白间隔最大值（秒）

# ─── WebSocket JSON-RPC 包装配置 ───
ENABLE_JSONRPC_RESPONSE = os.environ.get("ENABLE_JSONRPC_RESPONSE", "false").strip().lower() in ("true", "1", "yes", "on")

# 兼容旧配置（逐步迁移）
API_KEY = DEEPSEEK_API_KEY
BASE_URL = DEEPSEEK_BASE_URL
MODEL = DEEPSEEK_MODEL

# ─── 配置验证 ───
def validate_config():
    """验证必要的配置是否已设置"""
    missing_keys = []

    # 检查DeepSeek配置
    if not DEEPSEEK_API_KEY:
        missing_keys.append("DEEPSEEK_API_KEY")

    # 检查千问配置
    if not QWEN_API_KEY:
        missing_keys.append("QWEN_API_KEY")

    # 检查TTS配置
    if not DASHSCOPE_API_KEY:
        missing_keys.append("DASHSCOPE_API_KEY")

    if missing_keys:
        raise EnvironmentError(
            f"以下环境变量未设置: {', '.join(missing_keys)}\n"
            "请在.env文件中设置这些变量，或设置对应的环境变量。\n"
            "示例.env文件内容:\n"
            "DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
            "QWEN_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
            "DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
            "\n可选配置（可使用默认值）:\n"
            "DEEPSEEK_BASE_URL=https://api.deepseek.com/v1\n"
            "DEEPSEEK_MODEL=deepseek-chat\n"
            "QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1\n"
            "QWEN_MODEL=qwen-max\n"
            "TTS_MODEL=qwen3-tts-vd-realtime-2026-01-15\n"
            "TTS_VOICE=qwen-tts-vd-live2d_girl-voice-20260413174053978-a5da\n"
            "TTS_BASE_URL=wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
        )

    # 检查API密钥格式
    for key_name, key_value in [
        ("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY),
        ("QWEN_API_KEY", QWEN_API_KEY),
        ("DASHSCOPE_API_KEY", DASHSCOPE_API_KEY)
    ]:
        if key_value and not key_value.startswith("sk-"):
            print(f"⚠️  警告：{key_name}格式异常，应以'sk-'开头，当前: {key_value[:8]}...")

    print("✅ 配置验证通过")
    return True

# 创建配置字典，便于其他模块导入
CONFIG = {
    "deepseek": {
        "api_key": DEEPSEEK_API_KEY,
        "base_url": DEEPSEEK_BASE_URL,
        "model": DEEPSEEK_MODEL
    },
    "qwen": {
        "api_key": QWEN_API_KEY,
        "base_url": QWEN_BASE_URL,
        "model": QWEN_MODEL
    },
    "tts": {
        "api_key": DASHSCOPE_API_KEY,
        "model": TTS_MODEL,
        "voice": TTS_VOICE,
        "base_url": TTS_BASE_URL
    },
    "agent": {
        "idle_timeout": AGENT_IDLE_TIMEOUT,
        "idle_interval_min": AGENT_IDLE_INTERVAL_MIN,
        "idle_interval_max": AGENT_IDLE_INTERVAL_MAX
    }
}