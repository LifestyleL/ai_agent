"""
用户参与度画像数据模型
合并 default.yaml 全局默认值与用户类型 profile
"""
from dataclasses import dataclass, field
from typing import Optional
import yaml
import os
from pathlib import Path


@dataclass
class EngagementParameters:
    """运行时参数（默认值与 default.yaml spontaneous 段一致）"""
    check_interval: int = 60
    max_per_hour: int = 3
    max_per_day: int = 10
    min_interval: int = 300
    allow_follow_up: bool = True
    follow_up_gentle_delay: int = 300
    follow_up_max_count: int = 1
    wake_up_delay: int = 1800
    wake_up_max_count: int = 1
    silent_cooling_after_no_reply: int = 2
    allow_consecutive: bool = True
    consecutive_backoff_base: float = 1.5
    night_start: int = 2
    night_end: int = 5
    reject_multiplier_max: float = 3.0
    silent_cooling_daily_greeting: bool = False
    allow_spontaneous: bool = True

    @classmethod
    def from_default_and_profile(cls, default_dict: dict, profile_overrides: dict):
        """从 default.yaml spontaneous 段 + profile 覆盖合成最终参数。
        default_dict 可能含多余 key，自动过滤。
        """
        valid_keys = set(cls.__dataclass_fields__.keys())
        filtered = {k: v for k, v in default_dict.items() if k in valid_keys}
        base = cls(**filtered)
        for k, v in profile_overrides.items():
            if k in valid_keys:
                setattr(base, k, v)
        return base


class EngagementProfile:
    """用户参与度画像，可手动指定或自动推断"""

    def __init__(self, mode: str = "auto", profile_type: str = "normal",
                 parameters: Optional[EngagementParameters] = None):
        self.mode = mode
        self.profile_type = profile_type
        self.parameters = parameters or EngagementParameters()
        self.auto_inferred_type: Optional[str] = None
        self.last_updated: float = 0.0

    @classmethod
    def create_from_config(cls, user_config: dict, defaults: dict, profiles: dict):
        """构造器：
        user_config — 用户存储的画像配置（engagement.json）
        defaults   — default.yaml 的 spontaneous 段
        profiles   — engagement_delta.yaml 的 profiles 段
        """
        mode = user_config.get("mode", "auto")
        ptype = user_config.get("profile_type", "normal")
        overrides = profiles.get(ptype, {})
        params = EngagementParameters.from_default_and_profile(defaults, overrides)
        if "override_params" in user_config:
            valid = set(EngagementParameters.__dataclass_fields__.keys())
            for k, v in user_config["override_params"].items():
                if k in valid:
                    setattr(params, k, v)
        return cls(mode=mode, profile_type=ptype, parameters=params)

    def apply_preset(self, profile_type: str, defaults: dict, profiles: dict):
        """运行时切换用户类型"""
        overrides = profiles.get(profile_type, {})
        self.parameters = EngagementParameters.from_default_and_profile(defaults, overrides)
        self.profile_type = profile_type


def load_profiles_dict(yaml_path: str) -> dict:
    """加载 engagement_delta.yaml 的 profiles 段"""
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data.get("profiles", {})


# 预设路径
PRESET_PROFILES_PATH = os.path.join(os.path.dirname(__file__), "../../config/engagement_delta.yaml")
