import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_LOCALES_DIR = Path(__file__).resolve().parents[2] / "locales"
SUPPORTED_LANGUAGES = ("uz", "ru")


@lru_cache
def _load(lang: str) -> dict[str, Any]:
    path = _LOCALES_DIR / f"{lang}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def translate(lang: str, key: str, **kwargs: Any) -> str:
    """Dot-path lookup into locales/<lang>.json with {placeholder} interpolation.
    Falls back to the key itself if missing, so a broken translation is visibly wrong
    in the running bot rather than silently swallowed."""
    if lang not in SUPPORTED_LANGUAGES:
        lang = "uz"
    node: Any = _load(lang)
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return key
        node = node[part]
    if isinstance(node, str) and kwargs:
        return node.format(**kwargs)
    return node if isinstance(node, str) else key


def menu_button_texts(key: str) -> set[str]:
    """All localized variants of a reply-keyboard button's text, for matching incoming
    messages against a button regardless of the user's selected language."""
    return {translate(lang, key) for lang in SUPPORTED_LANGUAGES}
