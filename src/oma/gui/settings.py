from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from ..storage.paths import app_data_dir


SETTINGS_PATH = app_data_dir() / "settings.json"


def load_settings() -> Dict[str, str]:
    if SETTINGS_PATH.exists():
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    return {"language": "zh_CN"}


def save_settings(data: Dict[str, str]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
