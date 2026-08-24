from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from app.config import load_settings

LAST_ERROR: str | None = None
MODELS = (
    "wavespeed-ai/flux-schnell",
    "wavespeed-ai/flux-dev",
)


def last_error() -> str | None:
    return LAST_ERROR


def _size(aspect: str) -> str:
    if aspect in {"9:16", "9x16"}:
        return "720*1280"
    return "1280*720"


async def generate_still(prompt: str, dest: Path, aspect: str = "16:9") -> bool:
    global LAST_ERROR
    LAST_ERROR = None
    settings = load_settings()
    key = (settings.get("wavespeed_api_key") or "").strip()
    if not key:
        LAST_ERROR = "No WaveSpeed API key"
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    clean = (
        f"{prompt.strip()}. Photoreal cinematic still, no text, no letters, "
        "no watermark, no logo, documentary lighting."
    )
    errors: list[str] = []
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
            for model in MODELS:
                submit = await client.post(
                    f"https://api.wavespeed.ai/api/v3/{model}",
                    headers=headers,
                    json={"prompt": clean, "size": _size(aspect), "output_format": "jpeg"},
                )
                if submit.status_code >= 400:
                    errors.append(f"{model} {submit.status_code}")
                    continue
                body = submit.json()
                task = body.get("data") or body
                pred_id = task.get("id")
                result_url = (task.get("urls") or {}).get("get") or (
                    f"https://api.wavespeed.ai/api/v3/predictions/{pred_id}/result" if pred_id else ""
                )
                if not result_url:
                    errors.append(f"{model}: no prediction id")
                    continue
                for _ in range(40):
                    poll = await client.get(result_url, headers={"Authorization": f"Bearer {key}"})
                    result = (poll.json().get("data") or poll.json()) if poll.status_code < 400 else {}
                    status = result.get("status")
                    if status == "completed":
                        outputs = result.get("outputs") or []
                        url = outputs[0] if outputs else None
                        if isinstance(url, dict):
                            url = url.get("url") or url.get("download_url")
                        if not url:
                            errors.append(f"{model}: empty outputs")
                            break
                        img = await client.get(str(url), timeout=60.0)
                        if img.status_code >= 400 or len(img.content) < 800:
                            errors.append(f"{model}: download failed")
                            break
                        dest.write_bytes(img.content)
                        return True
                    if status in {"failed", "cancelled", "timeout"}:
                        errors.append(f"{model}: {result.get('error') or status}")
                        break
                    await asyncio.sleep(2)
    except Exception as exc:
        LAST_ERROR = f"WaveSpeed error: {exc}"
        return False
    LAST_ERROR = "WaveSpeed failed. " + " | ".join(errors[-4:])
    return False
