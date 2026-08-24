from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from app.paths import SETTINGS_PATH, ensure_dirs

DEFAULTS: dict[str, Any] = {
    "channel_name": "",
    "default_privacy": "private",
    "default_format": "long",
    "default_style": "explainer",
    "default_voice": "local:en-us",
    "default_mood": "ember",
    "openai_api_key": "",
    "openai_model": "gpt-4o-mini",
    "anthropic_api_key": "",
    "anthropic_model": "claude-3-5-haiku-latest",
    "gemini_api_key": "",
    "gemini_model": "gemini-2.0-flash",
    "google_client_id": "",
    "google_client_secret": "",
    "public_base_url": "",
    "youtube_category_id": "27",
    "made_for_kids": False,
}


def load_settings() -> dict[str, Any]:
    ensure_dirs()
    if not SETTINGS_PATH.exists():
        return deepcopy(DEFAULTS)
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return deepcopy(DEFAULTS)
    merged = deepcopy(DEFAULTS)
    merged.update({k: v for k, v in data.items() if k in DEFAULTS})
    return merged


def save_settings(update: dict[str, Any]) -> dict[str, Any]:
    current = load_settings()
    for key, value in update.items():
        if key not in DEFAULTS:
            continue
        if isinstance(value, str) and value.strip() == "••••••••":
            continue
        current[key] = value
    SETTINGS_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return current


def public_settings() -> dict[str, Any]:
    data = load_settings()
    masked = deepcopy(data)
    for key in (
        "openai_api_key",
        "anthropic_api_key",
        "gemini_api_key",
        "google_client_secret",
    ):
        if masked.get(key):
            masked[key] = "••••••••"
    masked["has_openai"] = bool(data.get("openai_api_key"))
    masked["has_anthropic"] = bool(data.get("anthropic_api_key"))
    masked["has_gemini"] = bool(data.get("gemini_api_key"))
    masked["has_google_oauth"] = bool(data.get("google_client_id") and data.get("google_client_secret"))
    return masked


def llm_available() -> bool:
    data = load_settings()
    return bool(data.get("openai_api_key") or data.get("anthropic_api_key") or data.get("gemini_api_key"))
