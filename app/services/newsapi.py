from __future__ import annotations

from typing import Any

import httpx

from app.config import load_settings

LAST_ERROR: str | None = None
COUNTRY = {"IN": "in", "US": "us", "GB": "gb"}


def last_error() -> str | None:
    return LAST_ERROR


def _key() -> str:
    return (load_settings().get("newsapi_api_key") or "").strip()


async def top_headlines(region: str = "IN", page_size: int = 15) -> list[dict[str, Any]]:
    global LAST_ERROR
    LAST_ERROR = None
    if not _key():
        LAST_ERROR = "No NewsAPI key"
        return []
    country = COUNTRY.get((region or "IN").upper(), "in")
    out: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for extra in ({"category": "entertainment"}, {"category": "sports"}, {}):
                params = {"apiKey": _key(), "country": country, "pageSize": page_size, **extra}
                res = await client.get("https://newsapi.org/v2/top-headlines", params=params)
                if res.status_code >= 400:
                    LAST_ERROR = f"NewsAPI {res.status_code}"
                    continue
                for art in (res.json() or {}).get("articles") or []:
                    title = (art.get("title") or "").split(" - ")[0].strip()
                    if len(title) < 8 or title.lower() == "[removed]":
                        continue
                    out.append(
                        {
                            "title": title[:90],
                            "source": "newsapi",
                            "why": f"Headline now ({(art.get('source') or {}).get('name') or 'news'})",
                            "url": art.get("url"),
                            "description": (art.get("description") or "").strip(),
                        }
                    )
    except Exception as exc:
        LAST_ERROR = f"NewsAPI: {exc}"
        return []
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in out:
        key = item["title"].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:20]


async def search_topic(topic: str, limit: int = 8) -> list[dict[str, Any]]:
    global LAST_ERROR
    LAST_ERROR = None
    if not _key() or not (topic or "").strip():
        return []
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            res = await client.get(
                "https://newsapi.org/v2/everything",
                params={
                    "apiKey": _key(),
                    "q": topic.strip()[:80],
                    "language": "en",
                    "sortBy": "relevancy",
                    "pageSize": limit,
                },
            )
        if res.status_code >= 400:
            LAST_ERROR = f"NewsAPI search {res.status_code}"
            return []
        items = []
        for art in (res.json() or {}).get("articles") or []:
            title = (art.get("title") or "").split(" - ")[0].strip()
            blurb = (art.get("description") or art.get("content") or "").strip()
            if len(title) < 8:
                continue
            items.append(
                {
                    "title": title[:120],
                    "description": blurb[:280],
                    "url": art.get("url"),
                    "source": (art.get("source") or {}).get("name") or "news",
                }
            )
        return items[:limit]
    except Exception as exc:
        LAST_ERROR = f"NewsAPI search: {exc}"
        return []
