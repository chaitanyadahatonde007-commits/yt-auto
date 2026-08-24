from __future__ import annotations

import json
import os
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
    "gemini_model": "gemini-2.5-flash",
    "groq_api_key": "",
    "groq_model": "llama-3.3-70b-versatile",
    "wavespeed_api_key": "",
    "pexels_api_key": "",
    "pixabay_api_key": "",
    "newsapi_api_key": "",
    "google_client_id": "",
    "google_client_secret": "",
    "public_base_url": "",
    "youtube_category_id": "27",
    "made_for_kids": False,
    "autopilot_enabled": False,
    "autopilot_interval_hours": 6,
    "autopilot_daily_cap": 3,
    "autopilot_format": "short",
    "autopilot_style": "explainer",
    "autopilot_region": "IN",
    "autopilot_publish": "schedule",
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
    env_map = {
        "openai_api_key": "OPENAI_API_KEY",
        "anthropic_api_key": "ANTHROPIC_API_KEY",
        "gemini_api_key": "GEMINI_API_KEY",
        "groq_api_key": "GROQ_API_KEY",
        "wavespeed_api_key": "WAVESPEED_API_KEY",
        "pexels_api_key": "PEXELS_API_KEY",
        "pixabay_api_key": "PIXABAY_API_KEY",
        "newsapi_api_key": "NEWSAPI_API_KEY",
    }
    for field, env_name in env_map.items():
        if not merged.get(field) and os.environ.get(env_name):
            merged[field] = os.environ[env_name].strip()
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
        "groq_api_key",
        "wavespeed_api_key",
        "pexels_api_key",
        "pixabay_api_key",
        "newsapi_api_key",
        "google_client_secret",
    ):
        if masked.get(key):
            masked[key] = "••••••••"
    masked["has_openai"] = bool(data.get("openai_api_key"))
    masked["has_anthropic"] = bool(data.get("anthropic_api_key"))
    masked["has_gemini"] = bool(data.get("gemini_api_key"))
    masked["has_groq"] = bool(data.get("groq_api_key"))
    masked["has_wavespeed"] = bool(data.get("wavespeed_api_key"))
    masked["has_pexels"] = bool(data.get("pexels_api_key"))
    masked["has_pixabay"] = bool(data.get("pixabay_api_key"))
    masked["has_newsapi"] = bool(data.get("newsapi_api_key"))
    masked["has_google_oauth"] = bool(data.get("google_client_id") and data.get("google_client_secret"))
    masked["groq_does"] = [
        "Writes the spoken script and scene list (very fast)",
        "Plans a unique picture prompt for every scene",
        "Optional PlayAI studio voice",
    ]
    masked["wavespeed_does"] = [
        "Paints several scene stills (Flux)",
        "Turns stills into real motion clips (image-to-video)",
        "Also tries text-to-video for the same scene",
        "Keeps the clip with the strongest motion and detail",
        "Paints the thumbnail photograph",
    ]
    masked["pexels_does"] = [
        "Pulls real stock video for each scene",
        "Competes with WaveSpeed motion; we keep the strongest clip",
        "Backup still photos if AI images fail",
    ]
    masked["pixabay_does"] = [
        "Searches royalty-free videos",
        "Searches royalty-free photos",
        "Fills scenes if Pexels misses, then we keep the strongest clip",
    ]
    masked["gemini_does"] = [
        "Backup stills if WaveSpeed fails",
        "Backup thumbnail if WaveSpeed fails",
        "Backup script writer if Groq is down",
    ]
    return masked


def llm_available() -> bool:
    data = load_settings()
    return bool(
        data.get("openai_api_key")
        or data.get("anthropic_api_key")
        or data.get("gemini_api_key")
        or data.get("groq_api_key")
    )
