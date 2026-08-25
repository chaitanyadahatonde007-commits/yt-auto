from __future__ import annotations

import asyncio
import base64
import io
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from app.config import load_settings

IMAGE_MODELS = (
    "gemini-2.5-flash-image",
    "gemini-2.0-flash-preview-image-generation",
    "gemini-3.1-flash-image",
)

LAST_IMAGE_ERROR: str | None = None


def last_image_error() -> str | None:
    return LAST_IMAGE_ERROR


def _extract_image(body: dict[str, Any]) -> bytes | None:
    parts = (((body.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    for part in parts:
        blob = part.get("inlineData") or part.get("inline_data") or {}
        data = blob.get("data")
        if data:
            try:
                return base64.b64decode(data)
            except Exception:
                continue
    return None


async def generate_still(prompt: str, dest: Path, aspect: str = "16:9") -> bool:
    """Paint one still. WaveSpeed first, then Gemini."""
    global LAST_IMAGE_ERROR
    LAST_IMAGE_ERROR = None
    dest.parent.mkdir(parents=True, exist_ok=True)
    from app.services.wavespeed import generate_still as wavespeed_still, last_error as wavespeed_error

    try:
        if await asyncio.wait_for(wavespeed_still(prompt, dest, aspect=aspect), timeout=25):
            return True
    except Exception:
        pass
    ws_err = wavespeed_error()

    settings = load_settings()
    key = (settings.get("gemini_api_key") or "").strip()
    if not key:
        LAST_IMAGE_ERROR = ws_err or "No image API key"
        return False

    clean = (
        f"{prompt.strip()}\n\n"
        f"Photoreal cinematic film still, {aspect}, documentary grade lighting, "
        "rich texture, no text, no letters, no typography, no watermark, no logo, no UI."
    )
    payloads = [
        {
            "contents": [{"parts": [{"text": clean}]}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {"aspectRatio": aspect},
            },
        },
        {
            "contents": [{"parts": [{"text": clean}]}],
            "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
        },
    ]
    errors: list[str] = []
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            for model in IMAGE_MODELS:
                for payload in payloads:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                    res = await client.post(
                        url,
                        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                        json=payload,
                    )
                    if res.status_code >= 400:
                        errors.append(f"{model} {res.status_code}")
                        continue
                    raw = _extract_image(res.json())
                    if not raw:
                        errors.append(f"{model}: no image bytes")
                        continue
                    im = Image.open(io.BytesIO(raw)).convert("RGB")
                    im.save(dest, quality=93)
                    return True
    except Exception as exc:
        LAST_IMAGE_ERROR = f"Gemini image error: {exc}"
        return False
    LAST_IMAGE_ERROR = "Gemini image failed. " + " | ".join(errors[-4:])
    return False


def visual_prompt_for(scene: dict[str, Any], project: dict[str, Any], index: int = 0) -> str:
    from app.services.characters import acting_prompt

    return acting_prompt(scene, project, index=index)
