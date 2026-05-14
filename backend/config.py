"""
应用配置 (V2.0 — 单一声源)

- YAML 树是唯一数据源 (default.yaml + {env}.yaml + .env)
- AppConfig 对象提供统一访问
- 模块级 __getattr__ 保持向后兼容：from config import WS_PORT 仍然有效
- 新增配置项只需在 default.yaml 和 _KEY_MAP 中各加一行
"""
import os
from utils.config_loader import init_config, get_config

# ── 初始化 YAML ──
init_config()
_YAML_CONFIG = get_config()

# ── 单一映射表：UPPER_CASE 模块名 → YAML 路径 ──
# 新增配置项只需在这里加一行（YAML 中也要有默认值）
_KEY_MAP = {
    # WebSocket
    "WS_PORT": ("websocket", "port"),
    "ENABLE_JSONRPC_RESPONSE": ("websocket", "enable_jsonrpc"),
    "LIVE2D_ENABLED": ("live2d", "enabled"),

    # AI (统一 DeepSeek)
    "DEEPSEEK_API_KEY": ("ai", "deepseek", "api_key"),
    "DEEPSEEK_BASE_URL": (("ai", "deepseek", "base_url"), "https://api.deepseek.com/v1"),
    "DEEPSEEK_MODEL": (("ai", "deepseek", "model"), "deepseek-chat"),
    "DASHSCOPE_API_KEY": ("tts", "api_key"),

    # TTS
    "TTS_ENABLED": (("tts", "enabled"), True),
    "TTS_VOICE": (("tts", "voice"), "zhixiaoxia"),
    "TTS_SPEED": (("tts", "speed"), 1.0),
    "TTS_PITCH": (("tts", "pitch"), 1.0),
    "TTS_MODEL": (("tts", "model"), "qwen3-tts-vd-realtime-2026-01-15"),
    "TTS_BASE_URL": (("tts", "base_url"), "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"),

    # Memory
    "SHORT_TERM_MAX_TOKENS": ("memory", "short_term_max_tokens"),
    "SHORT_TERM_CAPACITY_BASE": ("memory", "short_term_capacity_base"),
    "SHORT_TERM_CAPACITY_DYNAMIC": ("memory", "short_term_capacity_dynamic"),
    "SHORT_TERM_CAPACITY_MAX": ("memory", "short_term_capacity_max"),
    "ENABLE_VECTOR_MEMORY": ("memory", "enable_vector_memory"),
    "FORGETTING_STRATEGY": ("memory", "forgetting_strategy"),
    "FORGETTING_MAX_CAPACITY": ("memory", "forgetting_max_capacity"),
    "FORGETTING_AGGRESSIVENESS": ("memory", "forgetting_aggressiveness"),
    "ENABLE_WAL_LOGGING": ("memory", "enable_wal_logging"),
    "SHORT_TERM_HISTORY_TOKENS": ("memory", "short_term_history_tokens"),
    "CARD_AUTO_APPROVE_THRESHOLD": (("memory", "card", "auto_approve_threshold"), 0.6),
    "CARD_SUGGESTION_MODE": (("memory", "card", "suggestion_mode"), False),

    # Agent
    "IDLE_TIMEOUT": ("agent", "idle_timeout"),
    "AGENT_IDLE_TIMEOUT": ("agent", "idle_timeout"),
    "AGENT_IDLE_INTERVAL_MIN": (("agent", "idle_interval_min"), 60),
    "AGENT_IDLE_INTERVAL_MAX": (("agent", "idle_interval_max"), 65),
    "MAX_CONCURRENT_TTS": ("agent", "max_concurrent_tts"),
    "MAX_STEPS": ("agent", "max_steps"),

    # Spontaneous engine
    "SPONTANEOUS_ENABLED": ("spontaneous", "enabled"),
    "SPONTANEOUS_CHECK_INTERVAL": ("spontaneous", "check_interval"),
    "SPONTANEOUS_MIN_SILENCE": ("spontaneous", "min_silence"),
    "SPONTANEOUS_MIN_INTERVAL": ("spontaneous", "min_interval"),
    "SPONTANEOUS_MAX_PER_HOUR": ("spontaneous", "max_per_hour"),
    "SPONTANEOUS_MAX_PER_DAY": ("spontaneous", "max_per_day"),
    "SPONTANEOUS_COOL_DOWN_AFTER_REJECT": ("spontaneous", "cool_down_after_reject"),
    "SPONTANEOUS_CONSECUTIVE_MAX": ("spontaneous", "consecutive_max"),
    "SPONTANEOUS_CONSECUTIVE_STOP_PROB": ("spontaneous", "consecutive_stop_prob"),
    "SPONTANEOUS_USE_LLM_THRESHOLD": ("spontaneous", "use_llm_threshold"),
    "SPONTANEOUS_NIGHT_START": ("spontaneous", "night_start"),
    "SPONTANEOUS_NIGHT_END": ("spontaneous", "night_end"),
    "SPONTANEOUS_GOAL_UPDATE_MIN_TURNS": ("spontaneous", "goal_update_min_turns"),
    "SPONTANEOUS_WINDOW_CONTINUATION": ("spontaneous", "window_continuation"),
    "SPONTANEOUS_WINDOW_EMOTIONAL": ("spontaneous", "window_emotional"),
    "SPONTANEOUS_WINDOW_GOAL": ("spontaneous", "window_goal"),

    # QQ 适配器
    "QQ_ENABLED": (("qq", "enabled"), False),
    "QQ_WS_HOST": (("qq", "ws_host"), "0.0.0.0"),
    "QQ_WS_PORT": (("qq", "ws_port"), 5800),
    "QQ_WS_PATH": (("qq", "ws_path"), "/onebot"),
    "QQ_CONTEXT_MAX_HISTORY_TURNS": (("qq", "context", "max_history_turns"), 20),
    "QQ_CONTEXT_SHORT_TERM_CAPACITY": (("qq", "context", "short_term_capacity"), 30),
    "QQ_TOOLS_VOICE_ENABLED": (("qq", "tools", "voice_enabled"), True),
    "QQ_TOOLS_VISION_ENABLED": (("qq", "tools", "vision_enabled"), True),

    # Vision (VLM)
    "VISION_ENABLED": ("vision", "enabled"),
    "VISION_MODEL": (("vision", "model"), "qwen3.5-omni-plus-2006-03-15"),
    "VISION_BASE_URL": (("vision", "base_url"), "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    "VISION_API_KEY_ENV": (("vision", "api_key_env"), "DASHSCOPE_API_KEY"),
    "VISION_MAX_DESCRIPTION_CHARS": (("vision", "max_description_chars"), 120),
    "VISION_FRAME_DIFF_THRESHOLD": (("vision", "frame_diff_threshold"), 0.08),
    "VISION_BASE_INTERVAL": (("vision", "base_interval"), 180),
    "VISION_SILENCE_BOOST_INTERVAL": (("vision", "silence_boost_interval"), 60),
    "VISION_COOLDOWN_SECONDS": (("vision", "cooldown_seconds"), 30),

    # Emotion engine
    "EMOTION_SMOOTHING_FACTOR": ("emotion", "smoothing_factor"),
    "EMOTION_DECAY_FACTOR": ("emotion", "decay_factor"),
    "EMOTION_SWITCH_THRESHOLD": ("emotion", "switch_threshold"),

    # Card memory (V5.0)
    "CARD_ENABLED": ("memory", "card", "enabled"),
    "CARD_MAX_CARDS": ("memory", "card", "max_cards"),
    "CARD_CREATE_INTERVAL": ("memory", "card", "create_interval"),
    "CARD_LINK_THRESHOLD": ("memory", "card", "link_threshold"),
    "CARD_BFS_MAX_DEPTH": ("memory", "card", "bfs_max_depth"),
    "CARD_BFS_LIMIT": ("memory", "card", "bfs_limit"),
    "CARD_RECENCY_HALFLIFE_DAYS": ("memory", "card", "recency_halflife_days"),
    "CARD_TIER1_AGE_DAYS": ("memory", "card", "tier1_age_days"),
    "CARD_TIER2_AGE_DAYS": ("memory", "card", "tier2_age_days"),
    "CARD_COMPRESSION_INTERVAL_HOURS": ("memory", "card", "compression_interval_hours"),
    "CARD_KEYWORD_SCORE_WEIGHT": ("memory", "card", "keyword_score_weight"),
    "CARD_RECENCY_SCORE_WEIGHT": ("memory", "card", "recency_score_weight"),
    "CARD_IMPORTANCE_SCORE_WEIGHT": ("memory", "card", "importance_score_weight"),

    # Context compression
    "COMPRESSION_ENABLED": (("memory", "compression", "enabled"), True),
    "COMPRESSION_TRIGGER_FILL_RATIO": (("memory", "compression", "trigger_fill_ratio"), 0.8),
    "COMPRESSION_MAX_RECENT_KEEP": (("memory", "compression", "max_recent_keep"), 8),
    "COMPRESSION_SUMMARY_MAX_CHARS": (("memory", "compression", "summary_max_chars"), 500),
    "COMPRESSION_MIN_ENTRIES": (("memory", "compression", "min_entries_to_compress"), 10),

    # App
    "DEBUG": ("app", "debug"),

    # Legacy compat (same YAML paths as primary keys, with same defaults)
    "API_KEY": (("ai", "deepseek", "api_key"),),
    "BASE_URL": (("ai", "deepseek", "base_url"), "https://api.deepseek.com/v1"),
    "MODEL": (("ai", "deepseek", "model"), "deepseek-chat"),
}


class AppConfig:
    """单一配置数据源。通过 __getattr__ 从 YAML 树取值。"""

    def __init__(self, yaml_config: dict, key_map: dict):
        self._config = yaml_config
        self._key_map = key_map

    def __getattr__(self, name: str):
        if name.startswith('_'):
            raise AttributeError(name)
        entry = self._key_map.get(name)
        if entry is None:
            raise AttributeError(f"Unknown config key: {name}")
        # entry 可以是 (keys_tuple,) 或 (keys_tuple, default_value)
        if isinstance(entry[0], tuple):
            keys, default = entry[0], entry[1] if len(entry) > 1 else None
        else:
            keys, default = entry, None
        d = self._config
        for k in keys:
            if isinstance(d, dict):
                d = d.get(k)
            else:
                return default
        return d if d is not None else default

    def validate(self) -> bool:
        """验证必要的配置是否已设置"""
        missing = []

        if not self.DEEPSEEK_API_KEY:
            missing.append("DEEPSEEK_API_KEY")
        if not self.DASHSCOPE_API_KEY:
            missing.append("DASHSCOPE_API_KEY")

        if missing:
            raise EnvironmentError(
                f"以下环境变量未设置: {', '.join(missing)}\n"
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

        for key_name, key_value in [
            ("DEEPSEEK_API_KEY", self.DEEPSEEK_API_KEY),
            ("DASHSCOPE_API_KEY", self.DASHSCOPE_API_KEY),
        ]:
            if key_value and not key_value.startswith("sk-"):
                print(f"[WARN] {key_name}格式异常，应以'sk-'开头，当前: {key_value[:8]}...")

        print("[OK] 配置验证通过")
        return True


# ── 单例 ──
_app_config = AppConfig(_YAML_CONFIG, _KEY_MAP)


# ── 模块级 __getattr__：向后兼容 ──
def __getattr__(name: str):
    """from config import WS_PORT 和 config.WS_PORT 都会走到这里"""
    if name == 'validate_config':
        return validate_config
    if name == 'CONFIG':
        return _build_config_dict()
    if name == 'AppConfig':
        return AppConfig
    if name in ('_app_config', '_KEY_MAP', '_YAML_CONFIG'):
        return globals()[f'_{name}'] if name.startswith('_') else globals().get(name)
    return getattr(_app_config, name)


def _build_config_dict() -> dict:
    """向后兼容的 CONFIG 字典（自动生成，不再手动维护）"""
    return {
        "deepseek": {
            "api_key": _app_config.DEEPSEEK_API_KEY,
            "base_url": _app_config.DEEPSEEK_BASE_URL,
            "model": _app_config.DEEPSEEK_MODEL,
        },
        "tts": {
            "api_key": _app_config.DASHSCOPE_API_KEY,
            "model": _app_config.TTS_MODEL,
            "voice": _app_config.TTS_VOICE,
            "base_url": _app_config.TTS_BASE_URL,
        },
        "agent": {
            "idle_timeout": _app_config.AGENT_IDLE_TIMEOUT,
            "idle_interval_min": _app_config.AGENT_IDLE_INTERVAL_MIN,
            "idle_interval_max": _app_config.AGENT_IDLE_INTERVAL_MAX,
        },
        "memory": {
            "short_term_capacity_base": _app_config.SHORT_TERM_CAPACITY_BASE,
            "short_term_capacity_dynamic": _app_config.SHORT_TERM_CAPACITY_DYNAMIC,
            "short_term_capacity_max": _app_config.SHORT_TERM_CAPACITY_MAX,
            "enable_vector_memory": _app_config.ENABLE_VECTOR_MEMORY,
            "forgetting_strategy": _app_config.FORGETTING_STRATEGY,
            "forgetting_max_capacity": _app_config.FORGETTING_MAX_CAPACITY,
            "forgetting_aggressiveness": _app_config.FORGETTING_AGGRESSIVENESS,
            "enable_wal_logging": _app_config.ENABLE_WAL_LOGGING,
        },
        "websocket": {
            "port": _app_config.WS_PORT,
            "enable_jsonrpc": _app_config.ENABLE_JSONRPC_RESPONSE,
        },
    }


def validate_config() -> bool:
    return _app_config.validate()


# ── 启动时打印 ──
if _app_config.DEBUG:
    print(f"[Config] 环境变量 APP_ENV={os.environ.get('APP_ENV', 'development')}")
    print(f"[Config] WebSocket 端口: {_app_config.WS_PORT}")
    print(f"[Config] JSON-RPC 启用: {_app_config.ENABLE_JSONRPC_RESPONSE}")
    print(f"[Config] 调试模式: {_app_config.DEBUG}")
