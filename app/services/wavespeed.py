from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import Any

import httpx
from PIL import Image, ImageChops, ImageStat

from app.config import load_settings
from app.paths import ffmpeg_exe

LAST_ERROR: str | None = None
IMAGE_MODELS = (
    "wavespeed-ai/flux-schnell",
    "wavespeed-ai/flux-dev",
)
I2V_MODELS = (
    "alibaba/wan-2.6/image-to-video",
    "bytedance/seedance-v1.5-pro/image-to-video",
)
T2V_MODELS = (
    "alibaba/wan-2.6/text-to-video",
    "openai/sora-2/text-to-video",
)


def last_error() -> str | None:
    return LAST_ERROR


def _headers() -> dict[str, str]:
    key = (load_settings().get("wavespeed_api_key") or "").strip()
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _key() -> str:
    return (load_settings().get("wavespeed_api_key") or "").strip()


def _size(aspect: str) -> str:
    if aspect in {"9:16", "9x16"}:
        return "720*1280"
    return "1280*720"


async def _poll(client: httpx.AsyncClient, result_url: str, tries: int = 60, wait: float = 3.0) -> dict[str, Any]:
    for _ in range(tries):
        poll = await client.get(result_url, headers={"Authorization": f"Bearer {_key()}"})
        body = poll.json() if poll.status_code < 400 else {}
        result = body.get("data") or body
        status = result.get("status")
        if status == "completed":
            return result
        if status in {"failed", "cancelled", "timeout"}:
            raise RuntimeError(str(result.get("error") or status))
        await asyncio.sleep(wait)
    raise RuntimeError("WaveSpeed timed out")


async def _run_model(client: httpx.AsyncClient, model: str, payload: dict[str, Any], dest: Path) -> bool:
    submit = await client.post(
        f"https://api.wavespeed.ai/api/v3/{model}",
        headers=_headers(),
        json=payload,
    )
    if submit.status_code >= 400:
        raise RuntimeError(f"{model} {submit.status_code}: {submit.text[:180]}")
    task = submit.json().get("data") or submit.json()
    pred_id = task.get("id")
    result_url = (task.get("urls") or {}).get("get") or (
        f"https://api.wavespeed.ai/api/v3/predictions/{pred_id}/result" if pred_id else ""
    )
    if not result_url:
        raise RuntimeError(f"{model}: no prediction id")
    result = await _poll(client, result_url)
    outputs = result.get("outputs") or []
    url = outputs[0] if outputs else None
    if isinstance(url, dict):
        url = url.get("url") or url.get("download_url")
    if not url:
        raise RuntimeError(f"{model}: empty outputs")
    media = await client.get(str(url), timeout=90.0)
    if media.status_code >= 400 or len(media.content) < 2000:
        raise RuntimeError(f"{model}: download failed")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(media.content)
    return True


async def generate_still(prompt: str, dest: Path, aspect: str = "16:9") -> bool:
    global LAST_ERROR
    LAST_ERROR = None
    if not _key():
        LAST_ERROR = "No WaveSpeed API key"
        return False
    clean = (
        f"{prompt.strip()}. Photoreal cinematic still, no text, no letters, "
        "no watermark, no logo, documentary lighting."
    )
    errors: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            for model in IMAGE_MODELS:
                try:
                    await _run_model(
                        client,
                        model,
                        {"prompt": clean, "size": _size(aspect), "output_format": "jpeg"},
                        dest,
                    )
                    return True
                except Exception as exc:
                    errors.append(str(exc)[:160])
    except Exception as exc:
        LAST_ERROR = f"WaveSpeed error: {exc}"
        return False
    LAST_ERROR = "WaveSpeed still failed. " + " | ".join(errors[-3:])
    return False


async def upload_image(path: Path) -> str | None:
    if not _key() or not path.exists():
        return None
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            with path.open("rb") as handle:
                res = await client.post(
                    "https://api.wavespeed.ai/api/v3/media/upload/binary",
                    headers={"Authorization": f"Bearer {_key()}"},
                    files={"file": (path.name, handle, "image/jpeg")},
                )
        if res.status_code >= 400:
            return None
        data = res.json().get("data") or res.json()
        return data.get("download_url") or data.get("url")
    except Exception:
        return None


async def generate_video_i2v(prompt: str, image_path: Path, dest: Path, duration: int = 5) -> bool:
    global LAST_ERROR
    if not _key():
        return False
    url = await upload_image(image_path)
    if not url:
        LAST_ERROR = "WaveSpeed could not upload the scene still"
        return False
    errors: list[str] = []
    payload = {
        "prompt": f"{prompt.strip()}. Slow cinematic camera, natural motion, no text.",
        "image": url,
        "duration": max(4, min(int(duration), 8)),
    }
    try:
        async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
            for model in I2V_MODELS:
                try:
                    await _run_model(client, model, payload, dest)
                    return True
                except Exception as exc:
                    errors.append(str(exc)[:160])
    except Exception as exc:
        LAST_ERROR = f"WaveSpeed I2V: {exc}"
        return False
    LAST_ERROR = "I2V failed. " + " | ".join(errors[-3:])
    return False


async def generate_video_t2v(prompt: str, dest: Path, aspect: str = "16:9", duration: int = 5) -> bool:
    global LAST_ERROR
    if not _key():
        return False
    payload = {
        "prompt": f"{prompt.strip()}. Cinematic motion, photoreal, no text, no letters.",
        "duration": max(4, min(int(duration), 8)),
        "size": _size(aspect),
    }
    errors: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as client:
            for model in T2V_MODELS:
                try:
                    await _run_model(client, model, payload, dest)
                    return True
                except Exception as exc:
                    errors.append(str(exc)[:160])
    except Exception as exc:
        LAST_ERROR = f"WaveSpeed T2V: {exc}"
        return False
    LAST_ERROR = "T2V failed. " + " | ".join(errors[-3:])
    return False


async def motion_score(path: Path) -> float:
    if not path.exists() or path.stat().st_size < 4000:
        return -1.0
    tmp = path.parent / f"_score_{path.stem}"
    tmp.mkdir(exist_ok=True)
    proc = await asyncio.create_subprocess_exec(
        ffmpeg_exe(),
        "-y",
        "-i",
        str(path),
        "-vf",
        "fps=2,scale=160:-1",
        str(tmp / "f%02d.jpg"),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.communicate()
    frames = sorted(tmp.glob("f*.jpg"))[:6]
    if len(frames) < 2:
        return math.log10(max(path.stat().st_size, 1))
    diffs = []
    prev = Image.open(frames[0]).convert("L")
    for frame in frames[1:]:
        cur = Image.open(frame).convert("L")
        if cur.size != prev.size:
            cur = cur.resize(prev.size)
        delta = ImageChops.difference(prev, cur)
        diffs.append(ImageStat.Stat(delta).mean[0])
        prev = cur
    motion = sum(diffs) / len(diffs)
    return motion + math.log10(max(path.stat().st_size, 1))


async def pick_best_clip(candidates: list[tuple[str, Path]]) -> tuple[str, Path] | None:
    best: tuple[float, str, Path] | None = None
    for kind, path in candidates:
        score = await motion_score(path)
        if kind == "i2v":
            score += 8
        elif kind == "pexels":
            score += 6
        elif kind == "t2v":
            score += 5
        if best is None or score > best[0]:
            best = (score, kind, path)
    if not best or best[0] < 0:
        return None
    return best[1], best[2]
