"""配置加载：.env + config.yaml 合并为运行时配置。"""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "config.yaml"

# 内置默认配置：config.yaml 缺失或字段不全时的兜底，保证 CLI 不因配置问题崩溃。
# 值与 config/config.yaml 保持一致；改阈值请以 yaml 为准，这里同步即可。
DEFAULT_CONFIG: dict = {
    "face": {
        "threshold_high": 0.40,
        "threshold_low": 0.25,
        "sample_step_seconds": 2.0,
        "merge_gap_seconds": 4.0,
    },
    "clip": {
        "padding_seconds": 2.0,
        "min_duration_seconds": 3.0,
    },
    "vlm": {
        "provider": "cloud",
        "weekly_frame_limit": 12,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """把 override 递归覆盖到 base 上，返回新 dict（不改原对象）。"""
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


class Settings(BaseSettings):
    # 本地存储根目录（路径 A：不用 MinIO / Docker）
    watch_dir: str = "./data/inbox"
    data_dir: str = "./data"
    vlm_provider: str = "cloud"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    local_vlm_model: str = "mlx-community/Qwen2.5-VL-3B-Instruct-4bit"
    # 注意：实际比对阈值以 config.yaml 为准（0.40 / 0.25），这里保持同步即可
    face_threshold_high: float = 0.40
    face_threshold_low: float = 0.25

    class Config:
        env_file = ROOT / ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_yaml_config() -> dict:
    """读取 config/config.yaml；文件缺失时回退到内置默认，不让程序崩掉。"""
    if not CONFIG_PATH.exists():
        print(f"[config] 未找到 config/config.yaml，使用内置默认配置")
        return deepcopy(DEFAULT_CONFIG)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    if not isinstance(loaded, dict):
        print("[config] config.yaml 顶层不是字典，使用内置默认配置")
        return deepcopy(DEFAULT_CONFIG)
    # 用默认值补齐 yaml 里缺的字段，避免将来新增参数时 KeyError
    return _deep_merge(DEFAULT_CONFIG, loaded)
