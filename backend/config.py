"""
应用配置入口

保持向后兼容：
- CONFIG 字典仍然可用
- 原有的常量（WS_PORT 等）仍然可用
- 但现在它们都从 YAML 加载
"""

import os
from utils.config_loader import init_config, get_config, get

# 初始化配置
init_config()

# 获取完整配置
CONFIG = get_config()

# ===== 向后兼容的常量导出 =====

# WebSocket 配置
WS_PORT = get("websocket", "port", default=8765)
ENABLE_JSONRPC_RESPONSE = get("websocket", "enable_jsonrpc", default=True)
LIVE2D_ENABLED = get("live2d", "enabled", default=False)

# AI 配置
QWEN_API_KEY = get("ai", "qwen", "api_key", default="")
QWEN_BASE_URL = get("ai", "qwen", "base_url", default="https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_MODEL = get("ai", "qwen", "model", default="qwen-max")
DEEPSEEK_API_KEY = get("ai", "deepseek", "api_key", default="")
DEEPSEEK_BASE_URL = get("ai", "deepseek", "base_url", default="https://api.deepseek.com/v1")
DEEPSEEK_MODEL = get("ai", "deepseek", "model", default="deepseek-chat")
DASHSCOPE_API_KEY = get("tts", "api_key", default="")

# TTS 配置
TTS_VOICE = get("tts", "voice", default="zhixiaoxia")
TTS_SPEED = get("tts", "speed", default=1.0)
TTS_PITCH = get("tts", "pitch", default=1.0)
TTS_MODEL = get("tts", "model", default="qwen3-tts-vd-realtime-2026-01-15")
TTS_BASE_URL = get("tts", "base_url", default="wss://dashscope.aliyuncs.com/api-ws/v1/realtime")

# 记忆配置
SHORT_TERM_MAX_TOKENS = get("memory", "short_term_max_tokens", default=4096)
SHORT_TERM_CAPACITY_BASE = get("memory", "short_term_capacity_base", default=15)
SHORT_TERM_CAPACITY_DYNAMIC = get("memory", "short_term_capacity_dynamic", default=True)
SHORT_TERM_CAPACITY_MAX = get("memory", "short_term_capacity_max", default=30)
ENABLE_VECTOR_MEMORY = get("memory", "enable_vector_memory", default=False)
FORGETTING_STRATEGY = get("memory", "forgetting_strategy", default="importance_based")
FORGETTING_MAX_CAPACITY = get("memory", "forgetting_max_capacity", default=2000)
FORGETTING_AGGRESSIVENESS = get("memory", "forgetting_aggressiveness", default=0.5)
ENABLE_WAL_LOGGING = get("memory", "enable_wal_logging", default=True)
SHORT_TERM_HISTORY_TOKENS = get("memory", "short_term_history_tokens", default=1500)

# Agent 配置
IDLE_TIMEOUT = get("agent", "idle_timeout", default=60)
AGENT_IDLE_TIMEOUT = IDLE_TIMEOUT
AGENT_IDLE_INTERVAL_MIN = get("agent", "idle_interval_min", default=60)
AGENT_IDLE_INTERVAL_MAX = get("agent", "idle_interval_max", default=65)
MAX_CONCURRENT_TTS = get("agent", "max_concurrent_tts", default=1)
MAX_STEPS = get("agent", "max_steps", default=8)

# 自驱动引擎配置
SPONTANEOUS_ENABLED = get("spontaneous", "enabled", default=True)
SPONTANEOUS_CHECK_INTERVAL = get("spontaneous", "check_interval", default=60)
SPONTANEOUS_MIN_SILENCE = get("spontaneous", "min_silence", default=600)
SPONTANEOUS_MIN_INTERVAL = get("spontaneous", "min_interval", default=300)
SPONTANEOUS_MAX_PER_HOUR = get("spontaneous", "max_per_hour", default=3)
SPONTANEOUS_MAX_PER_DAY = get("spontaneous", "max_per_day", default=10)
SPONTANEOUS_COOL_DOWN_AFTER_REJECT = get("spontaneous", "cool_down_after_reject", default=120)
SPONTANEOUS_CONSECUTIVE_MAX = get("spontaneous", "consecutive_max", default=4)
SPONTANEOUS_CONSECUTIVE_STOP_PROB = get("spontaneous", "consecutive_stop_prob", default=0.3)
SPONTANEOUS_USE_LLM_THRESHOLD = get("spontaneous", "use_llm_threshold", default=3)
SPONTANEOUS_NIGHT_START = get("spontaneous", "night_start", default=2)
SPONTANEOUS_NIGHT_END = get("spontaneous", "night_end", default=5)
SPONTANEOUS_GOAL_UPDATE_MIN_TURNS = get("spontaneous", "goal_update_min_turns", default=2)
# V5.0 多层触发窗口
_wc = get("spontaneous", "window_continuation", default=[8, 30])
SPONTANEOUS_WINDOW_CONTINUATION = (int(_wc[0]), int(_wc[1]))
_we = get("spontaneous", "window_emotional", default=[30, 120])
SPONTANEOUS_WINDOW_EMOTIONAL = (int(_we[0]), int(_we[1]))
_wg = get("spontaneous", "window_goal", default=[60, 300])
SPONTANEOUS_WINDOW_GOAL = (int(_wg[0]), int(_wg[1]))

# 情绪引擎配置
EMOTION_SMOOTHING_FACTOR = get("emotion", "smoothing_factor", default=0.7)
EMOTION_DECAY_FACTOR = get("emotion", "decay_factor", default=0.9)
EMOTION_SWITCH_THRESHOLD = get("emotion", "switch_threshold", default=2)

# V5.0 卡片记忆配置
CARD_ENABLED = get("memory", "card", "enabled", default=True)
CARD_MAX_CARDS = get("memory", "card", "max_cards", default=2000)
CARD_CREATE_INTERVAL = get("memory", "card", "create_interval", default=1)
CARD_LINK_THRESHOLD = get("memory", "card", "link_threshold", default=0.25)
CARD_BFS_MAX_DEPTH = get("memory", "card", "bfs_max_depth", default=3)
CARD_BFS_LIMIT = get("memory", "card", "bfs_limit", default=10)
CARD_RECENCY_HALFLIFE_DAYS = get("memory", "card", "recency_halflife_days", default=7)
CARD_TIER1_AGE_DAYS = get("memory", "card", "tier1_age_days", default=3)
CARD_TIER2_AGE_DAYS = get("memory", "card", "tier2_age_days", default=30)
CARD_COMPRESSION_INTERVAL_HOURS = get("memory", "card", "compression_interval_hours", default=6)
CARD_KEYWORD_SCORE_WEIGHT = get("memory", "card", "keyword_score_weight", default=0.5)
CARD_RECENCY_SCORE_WEIGHT = get("memory", "card", "recency_score_weight", default=0.3)
CARD_IMPORTANCE_SCORE_WEIGHT = get("memory", "card", "importance_score_weight", default=0.2)

# 调试模式
DEBUG = get("app", "debug", default=True)

# 兼容旧配置（逐步迁移）
API_KEY = DEEPSEEK_API_KEY
BASE_URL = DEEPSEEK_BASE_URL
MODEL = DEEPSEEK_MODEL

# 构建向后兼容的CONFIG字典（保持旧结构）
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
    },
    "memory": {
        "short_term_capacity_base": SHORT_TERM_CAPACITY_BASE,
        "short_term_capacity_dynamic": SHORT_TERM_CAPACITY_DYNAMIC,
        "short_term_capacity_max": SHORT_TERM_CAPACITY_MAX,
        "enable_vector_memory": ENABLE_VECTOR_MEMORY,
        "forgetting_strategy": FORGETTING_STRATEGY,
        "forgetting_max_capacity": FORGETTING_MAX_CAPACITY,
        "forgetting_aggressiveness": FORGETTING_AGGRESSIVENESS,
        "enable_wal_logging": ENABLE_WAL_LOGGING
    },
    "websocket": {
        "port": WS_PORT,
        "enable_jsonrpc": ENABLE_JSONRPC_RESPONSE
    }
}

# 打印配置加载状态（仅 debug 模式）
if DEBUG:
    print(f"[Config] 环境变量 APP_ENV={os.environ.get('APP_ENV', 'development')}")
    print(f"[Config] WebSocket 端口: {WS_PORT}")
    print(f"[Config] JSON-RPC 启用: {ENABLE_JSONRPC_RESPONSE}")
    print(f"[Config] 调试模式: {DEBUG}")

# ─── 配置验证（保持向后兼容） ───
def validate_config():
    """验证必要的配置是否已设置"""
    missing_keys = []

    # 检查DeepSeek配置
    if not DEEPSEEK_API_KEY:
        missing_keys.append("DEEPSEEK_API_KEY")

    # 千问已废弃，不再强制要求
    if QWEN_API_KEY:
        print("[Config] Qwen API 已配置（已废弃，系统使用 DeepSeek 单模型）")

    # 检查TTS配置
    if not DASHSCOPE_API_KEY:
        missing_keys.append("DASHSCOPE_API_KEY")

    if missing_keys:
        raise EnvironmentError(
            f"以下环境变量未设置: {', '.join(missing_keys)}\n"
            "请在.env文件中设置这些变量，或设置对应的环境变量。\n"
            "示例.env文件内容:\n"
            "DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
            "DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
            "\n可选配置（可使用默认值）:\n"
            "DEEPSEEK_BASE_URL=https://api.deepseek.com/v1\n"
            "DEEPSEEK_MODEL=deepseek-chat\n"
            "TTS_MODEL=qwen3-tts-vd-realtime-2026-01-15\n"
            "TTS_VOICE=qwen-tts-vd-live2d_girl-voice-20260413174053978-a5da\n"
            "TTS_BASE_URL=wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
        )

    # 检查API密钥格式
    for key_name, key_value in [
        ("DEEPSEEK_API_KEY", DEEPSEEK_API_KEY),
        ("DASHSCOPE_API_KEY", DASHSCOPE_API_KEY)
    ]:
        if key_value and not key_value.startswith("sk-"):
            print(f"[WARN] {key_name}格式异常，应以'sk-'开头，当前: {key_value[:8]}...")

    print("[OK] 配置验证通过")
    return True