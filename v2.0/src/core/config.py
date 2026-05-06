"""配置管理模块。"""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

load_dotenv()


class Config:
    """单例配置类，支持环境变量替换。"""

    _instance = None
    _config: dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self) -> None:
        config_path = Path(__file__).parent.parent.parent / "config" / "settings.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        self._config = self._interpolate(raw)

    def _interpolate(self, obj: Any) -> Any:
        """递归替换 ${VAR} 为环境变量值。"""
        if isinstance(obj, str):
            import re

            def replacer(match: re.Match) -> str:
                var_name = match.group(1)
                return os.environ.get(var_name, match.group(0))

            return re.sub(r"\$\{([^}]+)\}", replacer, obj)
        if isinstance(obj, dict):
            return {k: self._interpolate(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._interpolate(item) for item in obj]
        return obj

    def get(self, key: str, default: Any = None) -> Any:
        """点号路径访问配置，如 'llm.kimi.api_key'。"""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    @property
    def raw(self) -> dict[str, Any]:
        return self._config


# 全局便捷访问函数
def get_config() -> Config:
    return Config()
