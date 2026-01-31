from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


class Translator:
    def __init__(self, base_dir: Path, default_lang: str = "zh_CN") -> None:
        self.base_dir = base_dir
        self.default_lang = default_lang
        self.lang = default_lang
        self.translations: Dict[str, Dict[str, str]] = {}
        self._load()

    def _load(self) -> None:
        for code in ("zh_CN", "en_US"):
            path = self.base_dir / f"{code}.json"
            with path.open("r", encoding="utf-8") as handle:
                self.translations[code] = json.load(handle)

    def set_language(self, lang: str) -> None:
        if lang in self.translations:
            self.lang = lang

    def t(self, key: str, **kwargs: str) -> str:
        value = self.translations.get(self.lang, {}).get(key)
        if value is None:
            value = self.translations.get("en_US", {}).get(key, key)
        if kwargs:
            try:
                return value.format(**kwargs)
            except Exception:
                return value
        return value
