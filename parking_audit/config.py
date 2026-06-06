import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"

CONFIG_FILE = CONFIG_DIR / "audit_config.json"

DEFAULT_CONFIG = {
    "matching": {
        "plate_similarity_threshold": 0.8,
        "time_tolerance_minutes": 15,
        "max_parking_hours": 72,
        "cross_day_hour": 0
    },
    "pricing": {
        "default_rate_per_hour": 5.0,
        "free_minutes": 15,
        "max_daily_fee": 50.0
    },
    "import": {
        "encoding": "utf-8",
        "date_formats": [
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y%m%d%H%M%S"
        ]
    },
    "export": {
        "format": "xlsx",
        "encoding": "utf-8-sig"
    },
    "plate_correction": {
        "enabled": True,
        "common_mistakes": {
            "0": ["O", "Q", "D"],
            "1": ["I", "L", "T"],
            "2": ["Z"],
            "5": ["S"],
            "8": ["B"],
            "6": ["G"],
            "9": ["q"]
        }
    }
}


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user_config = json.load(f)
        return deep_merge(DEFAULT_CONFIG, user_config)
    return DEFAULT_CONFIG.copy()


def save_config(config):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def deep_merge(default, override):
    result = default.copy()
    for key, value in override.items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_config_value(*keys, default=None):
    config = load_config()
    current = config
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current
