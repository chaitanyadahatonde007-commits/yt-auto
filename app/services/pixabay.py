from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from app.config import load_settings
from app.services.pexels import search_query

LAST_ERROR: str | None = None


def last_error() -> str | None:
    return LAST_ERROR


def _key() -> str:
    return (load_settings().get("pixabay_api_key") or "").strip()


def _orientation(aspect: str) -> str:
    return "vertical" if aspect in {"9:16", "9x16"} else "horizontal"


async def _download(client: httpx.AsyncClient, url: str, dest: Path) -> bool:
    res = await client.get(url, headers={"User-Agent": "ChannelForge/1.0"}, follow_redirects=True)
    if res.status_code >= 400 or len(res.content) < 8000:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(res.content)
    return True


def _pick_video_url(hit: dict[str, Any], aspect: str) -> str | None:
    want_portrait = aspect in {"9:16", "9x16"}
    videos = hit.get("videos") or {}
    ranked: list[tuple[float, str]] = []
    for name in ("large", "medium", "small"):
        item = videos.get(name) or {}
        url = item.get("url")
        if not url:
            continue
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        if width < 480 or height < 360 or max(width, height) > 2560:
            continue
        ori_pen = 0.0 if (height > width) == want_portrait else 40.0
        size_pen = 0.0 if name == "medium" else (1.0 if name == "large" else 4.0)
        ranked.append((ori_pen + size_pen, str(url)))
    ranked.sort(key=lambda row: row[0])
    return ranked[0][1] if ranked else None


async def fetch_video(
    prompt: str,
    dest: Path,
    aspect: str = "16:9",
    hint: str = "",
    used: set[int] | None = None,
    index: int = 0,
) -> bool:
    global LAST_ERROR
    LAST_ERROR = None
    if not _key():
        LAST_ERROR = "No Pixabay API key"
        return False
    used = used if used is not None else set()
    errors: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
            for query in search_query(prompt, hint):
                res = await client.get(
                    "https://pixabay.com/api/videos/",
                    params={
                        "key": _key(),
                        "q": query,
                        "orientation": _orientation(aspect),
                        "per_page": 12,
                        "page": (index % 4) + 1,
                        "safesearch": "true",
                    },
                )
                if res.status_code >= 400:
                    errors.append(f"video {res.status_code}")
                    continue
                hits = (res.json() or {}).get("hits") or []
                for hit in hits:
                    vid = int(hit.get("id") or 0)
                    if vid and vid in used:
                        continue
                    url = _pick_video_url(hit, aspect)
                    if not url:
                        continue
                    if await _download(client, url, dest):
                        if vid:
                            used.add(vid)
                        return True
                    errors.append("download failed")
    except Exception as exc:
        LAST_ERROR = f"Pixabay video: {exc}"
        return False
    LAST_ERROR = "Pixabay video failed. " + " | ".join(errors[-3:])
    return False


async def fetch_still(
    prompt: str,
    dest: Path,
    aspect: str = "16:9",
    hint: str = "",
    index: int = 0,
) -> bool:
    global LAST_ERROR
    LAST_ERROR = None
    if not _key():
        LAST_ERROR = "No Pixabay API key"
        return False
    errors: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for query in search_query(prompt, hint):
                res = await client.get(
                    "https://pixabay.com/api/",
                    params={
                        "key": _key(),
                        "q": query,
                        "image_type": "photo",
                        "orientation": _orientation(aspect),
                        "per_page": 10,
                        "page": (index % 4) + 1,
                        "safesearch": "true",
                    },
                )
                if res.status_code >= 400:
                    errors.append(f"photo {res.status_code}")
                    continue
                hits = (res.json() or {}).get("hits") or []
                if not hits:
                    continue
                hit = hits[index % len(hits)]
                url = hit.get("largeImageURL") or hit.get("webformatURL") or hit.get("fullHDURL")
                if url and await _download(client, str(url), dest):
                    return True
    except Exception as exc:
        LAST_ERROR = f"Pixabay photo: {exc}"
        return False
    LAST_ERROR = "Pixabay photo failed. " + " | ".join(errors[-3:])
    return False
