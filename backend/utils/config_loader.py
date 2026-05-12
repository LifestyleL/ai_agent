"""
YAML 分层配置加载器

加载顺序（后者覆盖前者）：
1. default.yaml - 默认配置
2. {environment}.yaml - 环境覆盖
3. .env 文件 - 敏感信息（API密钥等，不进YAML）

环境变量优先级：
APP_ENV → 决定加载哪个环境配置文件（默认 development）
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict
from dotenv import load_dotenv


class ConfigLoader:
    """分层配置加载器"""

    def __init__(self, config_dir: str = None):
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / "config"
        else:
            config_dir = Path(config_dir)

        self.config_dir = config_dir
        self._config: Dict[str, Any] = {}

    def load(self) -> Dict[str, Any]:
        """加载完整配置（分层合并）"""
        # 1. 加载默认配置
        self._config = self._load_yaml("default.yaml")

        # 2. 加载环境配置覆盖
        env = os.environ.get("APP_ENV", "development")
        env_file = f"{env}.yaml"
        if (self.config_dir / env_file).exists():
            env_config = self._load_yaml(env_file)
            self._deep_merge(self._config, env_config)

        # 3. 加载 .env 敏感信息（不覆盖已有配置，只补充）
        self._load_env_overrides()

        return self._config

    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """加载单个 YAML 文件"""
        filepath = self.config_dir / filename
        if not filepath.exists():
            return {}

        with open(filepath, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """深度合并字典，override 覆盖 base"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    def _load_env_overrides(self):
        """从 .env 加载敏感信息（API密钥等）"""
        # 加载 .env 文件
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=True)

        # 敏感信息映射：环境变量名 → 配置路径
        sensitive_mappings = {
            "DEEPSEEK_API_KEY": ("ai", "deepseek", "api_key"),
            "DASHSCOPE_API_KEY": ("tts", "api_key"),
            # TTS配置
            "TTS_VOICE": ("tts", "voice"),
            "TTS_MODEL": ("tts", "model"),
            "TTS_BASE_URL": ("tts", "base_url"),
            # AI模型配置
            "DEEPSEEK_MODEL": ("ai", "deepseek", "model"),
        }

        for env_var, config_path in sensitive_mappings.items():
            value = os.environ.get(env_var)
            if value:
                self._set_nested(self._config, config_path, value)

    def _set_nested(self, d: Dict, keys: tuple, value: Any):
        """设置嵌套字典值"""
        for key in keys[:-1]:
            if key not in d:
                d[key] = {}
            d = d[key]
        d[keys[-1]] = value

    def get(self, *keys, default=None) -> Any:
        """获取配置值，支持点分路径: get('ai', 'deepseek', 'model')"""
        d = self._config
        for key in keys:
            if not isinstance(d, dict) or key not in d:
                return default
            d = d[key]
        return d


# 全局单例
_loader: ConfigLoader = None
_config: Dict[str, Any] = {}

def init_config(config_dir: str = None) -> Dict[str, Any]:
    """初始化配置（应用启动时调用一次）"""
    global _loader, _config
    _loader = ConfigLoader(config_dir)
    _config = _loader.load()
    return _config

def get_config() -> Dict[str, Any]:
    """获取完整配置字典"""
    return _config

def get(*keys, default=None) -> Any:
    """获取配置值的快捷方法"""
    if not _config:
        init_config()
    return _loader.get(*keys, default=default)