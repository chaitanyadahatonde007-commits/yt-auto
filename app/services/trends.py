from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree as ET

import httpx

from app.config import load_settings
from app.store import autopilot_used_topics

UA = "ChannelForge/1.0 (autopilot; +https://localhost)"


def _clean_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"\s*[-–|].{0,40}$", "", text).strip()
    return text[:90]


async def _youtube_popular(region: str) -> list[dict[str, Any]]:
    from app.services.youtube_pub import load_credentials

    creds = load_credentials()
    if not creds:
        return []
    try:
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        youtube = build("youtube", "v3", credentials=creds)
        res = youtube.videos().list(
            part="snippet,statistics",
            chart="mostPopular",
            regionCode=region or "IN",
            maxResults=15,
        ).execute()
        out = []
        for item in res.get("items") or []:
            title = _clean_title((item.get("snippet") or {}).get("title") or "")
            if title:
                out.append({"title": title, "source": "youtube", "why": "YouTube most popular right now"})
        return out
    except Exception:
        return []


async def _google_trends(region: str) -> list[dict[str, Any]]:
    url = f"https://trends.google.com/trending/rss?geo={region or 'IN'}"
    try:
        async with httpx.AsyncClient(timeout=12.0, headers={"User-Agent": UA}, follow_redirects=True) as client:
            res = await client.get(url)
        if res.status_code >= 400:
            return []
        root = ET.fromstring(res.text)
        items = []
        for item in root.findall(".//item"):
            title = _clean_title((item.findtext("title") or ""))
            if title:
                items.append({"title": title, "source": "google_trends", "why": "Google Trends now"})
        return items[:15]
    except Exception:
        return []


async def _reddit() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    headers = {"User-Agent": UA}
    try:
        async with httpx.AsyncClient(timeout=12.0, headers=headers, follow_redirects=True) as client:
            for sub in ("popular", "todayilearned", "explainlikeimfive", "science"):
                res = await client.get(f"https://www.reddit.com/r/{sub}/hot.json", params={"limit": 8})
                if res.status_code >= 400:
                    continue
                for child in ((res.json().get("data") or {}).get("children") or []):
                    data = child.get("data") or {}
                    title = _clean_title(data.get("title") or "")
                    if title and not data.get("over_18"):
                        out.append({"title": title, "source": f"reddit/{sub}", "why": "Rising on Reddit"})
    except Exception:
        return out
    return out[:20]


async def _wikipedia_today() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    url = f"https://en.wikipedia.org/api/rest_v1/feed/featured/{now:%Y}/{now:%m}/{now:%d}"
    try:
        async with httpx.AsyncClient(timeout=12.0, headers={"User-Agent": UA}, follow_redirects=True) as client:
            res = await client.get(url)
        if res.status_code >= 400:
            return []
        data = res.json()
        out = []
        tfa = (data.get("tfa") or {}).get("titles") or {}
        if tfa.get("normalized"):
            out.append({"title": tfa["normalized"], "source": "wikipedia", "why": "Wikipedia featured today"})
        for ev in (data.get("mostread") or {}).get("articles") or []:
            name = (ev.get("titles") or {}).get("normalized")
            if name:
                out.append({"title": name, "source": "wikipedia", "why": "Most read on Wikipedia"})
        return out[:12]
    except Exception:
        return []


async def _refine_topic(raw: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings()
    key = (settings.get("groq_api_key") or "").strip()
    if not key:
        return {
            "topic": raw["title"],
            "source": raw["source"],
            "why": raw.get("why") or "",
            "notes": f"Trending via {raw.get('source')}: {raw.get('title')}",
        }
    prompt = (
        "Turn this trending headline into one original YouTube explainer topic. "
        "Do not copy the headline as news. Make it a curiosity question or mechanism. "
        "No celebrity gossip, no medical advice, no politics as a fight. "
        "Return JSON only: {\"topic\":\"...\",\"angle\":\"...\"}\n\n"
        f"Headline: {raw['title']}\nSource: {raw.get('source')}"
    )
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": settings.get("groq_model") or "llama-3.3-70b-versatile",
                    "temperature": 0.5,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        if res.status_code >= 400:
            raise RuntimeError(res.text[:120])
        data = res.json()["choices"][0]["message"]["content"]
        import json

        parsed = json.loads(data)
        topic = (parsed.get("topic") or raw["title"]).strip()
        angle = (parsed.get("angle") or "").strip()
        return {
            "topic": topic[:90],
            "source": raw["source"],
            "why": raw.get("why") or "",
            "notes": f"Trending now ({raw.get('source')}): {raw['title']}. Angle: {angle}".strip(),
        }
    except Exception:
        return {
            "topic": raw["title"],
            "source": raw["source"],
            "why": raw.get("why") or "",
            "notes": f"Trending via {raw.get('source')}: {raw.get('title')}",
        }


async def discover_trends(region: str | None = None) -> list[dict[str, Any]]:
    settings = load_settings()
    region = region or settings.get("autopilot_region") or "IN"
    used = autopilot_used_topics()
    buckets = await _gather(region)
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in buckets:
        key = item["title"].lower()
        if key in seen or key in used or len(key) < 8:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:24]


async def _gather(region: str) -> list[dict[str, Any]]:
    yt, trends, reddit, wiki = [], [], [], []
    try:
        yt = await _youtube_popular(region)
    except Exception:
        pass
    try:
        trends = await _google_trends(region)
    except Exception:
        pass
    try:
        reddit = await _reddit()
    except Exception:
        pass
    try:
        wiki = await _wikipedia_today()
    except Exception:
        pass
    # Prefer YouTube + Trends first
    return yt + trends + wiki + reddit


async def pick_topic(region: str | None = None) -> dict[str, Any]:
    candidates = await discover_trends(region)
    if not candidates:
        raise RuntimeError("Could not read any trending feed. Check the network and try again.")
    return await _refine_topic(candidates[0])
