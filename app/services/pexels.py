from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import httpx

from app.config import load_settings

LAST_ERROR: str | None = None
_STOP = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "your",
    "about",
    "photoreal",
    "cinematic",
    "still",
    "text",
    "letters",
    "watermark",
    "logo",
    "documentary",
    "lighting",
    "camera",
    "shot",
    "scene",
    "show",
    "picture",
    "without",
    "typography",
    "film",
    "grade",
    "rich",
    "texture",
    "mood",
    "host",
    "saying",
    "headline",
    "idea",
    "what",
    "line",
    "matches",
    "specific",
    "real",
    "world",
    "scientific",
    "slow",
    "natural",
    "motion",
    "prompt",
    "visual",
    "image",
    "video",
    "background",
    "none",
    "not",
}


def last_error() -> str | None:
    return LAST_ERROR


def _key() -> str:
    return (load_settings().get("pexels_api_key") or "").strip()


def _headers() -> dict[str, str]:
    return {
        "Authorization": _key(),
        "User-Agent": "ChannelForge/1.0",
        "Accept": "application/json",
    }


def search_query(prompt: str, hint: str = "") -> list[str]:
    def words(text: str) -> list[str]:
        found = re.findall(r"[A-Za-z]{3,}", text or "")
        return [w for w in found if w.lower() not in _STOP]

    primary = words(prompt)
    extra = words(hint)
    queries: list[str] = []
    if len(primary) >= 2:
        queries.append(" ".join(primary[:5]))
    if len(primary) >= 4:
        queries.append(" ".join(primary[:2]))
    if extra:
        blob = " ".join(extra[:4])
        if blob.lower() not in {q.lower() for q in queries}:
            queries.append(blob)
    if not queries:
        queries.append((hint or prompt or "cinematic landscape").strip()[:60])
    return [q for q in queries if q]


def _orientation(aspect: str) -> str:
    return "portrait" if aspect in {"9:16", "9x16"} else "landscape"


def _pick_video_file(video: dict[str, Any], aspect: str) -> dict[str, Any] | None:
    want_portrait = _orientation(aspect) == "portrait"
    target_w, target_h = (1080, 1920) if want_portrait else (1920, 1080)
    files = [f for f in (video.get("video_files") or []) if f.get("link")]
    scored: list[tuple[float, dict[str, Any]]] = []
    for item in files:
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        if width < 480 or height < 480 or max(width, height) > 2560:
            continue
        kind = (item.get("file_type") or "").lower()
        if kind and "mp4" not in kind and "video" not in kind:
            continue
        ori_pen = 0.0 if (height > width) == want_portrait else 50.0
        size_pen = (abs(width - target_w) + abs(height - target_h)) / 40.0
        scored.append((ori_pen + size_pen, item))
    scored.sort(key=lambda row: row[0])
    return scored[0][1] if scored else None


async def _download(client: httpx.AsyncClient, url: str, dest: Path) -> bool:
    res = await client.get(url, headers={"User-Agent": "ChannelForge/1.0"}, follow_redirects=True)
    if res.status_code >= 400 or len(res.content) < 8000:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(res.content)
    return True


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
        LAST_ERROR = "No Pexels API key"
        return False
    used = used if used is not None else set()
    orientation = _orientation(aspect)
    errors: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
            for query in search_query(prompt, hint):
                res = await client.get(
                    "https://api.pexels.com/videos/search",
                    headers=_headers(),
                    params={
                        "query": query,
                        "orientation": orientation,
                        "size": "medium",
                        "per_page": 12,
                        "page": (index % 4) + 1,
                    },
                )
                if res.status_code >= 400:
                    errors.append(f"video {res.status_code}")
                    continue
                videos = (res.json() or {}).get("videos") or []
                for video in videos:
                    vid = int(video.get("id") or 0)
                    if vid and vid in used:
                        continue
                    chosen = _pick_video_file(video, aspect)
                    if not chosen:
                        continue
                    if await _download(client, str(chosen["link"]), dest):
                        if vid:
                            used.add(vid)
                        return True
                    errors.append("download failed")
    except Exception as exc:
        LAST_ERROR = f"Pexels video: {exc}"
        return False
    LAST_ERROR = "Pexels video failed. " + " | ".join(errors[-3:])
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
        LAST_ERROR = "No Pexels API key"
        return False
    orientation = _orientation(aspect)
    errors: list[str] = []
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for query in search_query(prompt, hint):
                res = await client.get(
                    "https://api.pexels.com/v1/search",
                    headers=_headers(),
                    params={
                        "query": query,
                        "orientation": orientation,
                        "per_page": 8,
                        "page": (index % 4) + 1,
                    },
                )
                if res.status_code >= 400:
                    errors.append(f"photo {res.status_code}")
                    continue
                photos = (res.json() or {}).get("photos") or []
                if not photos:
                    continue
                photo = photos[index % len(photos)]
                src = photo.get("src") or {}
                url = src.get("large2x") or src.get("large") or src.get("original")
                if url and await _download(client, str(url), dest):
                    return True
    except Exception as exc:
        LAST_ERROR = f"Pexels photo: {exc}"
        return False
    LAST_ERROR = "Pexels photo failed. " + " | ".join(errors[-3:])
    return False
