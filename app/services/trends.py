from __future__ import annotations

import asyncio
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
            videoCategoryId="24",
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
            for sub in ("movies", "television", "bollywood", "cricket", "todayilearned", "unexpected"):
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
        "Turn this trending item into one original entertainment YouTube topic that keeps people watching. "
        "Do not copy the headline as news. Make it a story, a missed detail, or a rewind moment. "
        "Movies, cricket, songs, series are good. No celebrity harassment, no medical advice, no political fight. "
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
                    "temperature": 0.8,
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
    try:
        buckets = await asyncio.wait_for(_gather(region), timeout=6.0)
    except Exception:
        buckets = _entertainment_vault()
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for item in buckets:
        key = item["title"].lower()
        if key in seen or key in used or len(key) < 8:
            continue
        seen.add(key)
        unique.append(item)
    if len(unique) < 6:
        for item in _entertainment_vault():
            key = item["title"].lower()
            if key not in seen and key not in used:
                unique.append(item)
    return unique[:24]


async def _gather(region: str) -> list[dict[str, Any]]:
    yt, trends, reddit, wiki, news = [], [], [], [], []
    try:
        yt = await _youtube_popular(region)
    except Exception:
        pass
    try:
        from app.services.newsapi import top_headlines

        news = await top_headlines(region)
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
    vault = _entertainment_vault()
    scored = _prefer_entertainment(news + yt + reddit + trends + wiki)
    return scored + vault


_FUN = {
    "movie", "film", "cinema", "cricket", "ipl", "song", "music", "series", "trailer",
    "netflix", "bollywood", "hollywood", "anime", "match", "goal", "concert", "viral",
    "scene", "ending", "villain", "hero", "ott", "season", "actor", "director",
    "album", "dance", "meme", "plot", "twist", "short", "reel", "episode", "final",
}


def _entertainment_vault() -> list[dict[str, Any]]:
    return [
        {"title": "Shaadi mein uncle dance ka secret timing", "source": "vault", "why": "Desi funny"},
        {"title": "IPL last over mein dimaag kyun band ho jata hai", "source": "vault", "why": "Cricket hook"},
        {"title": "Mummy ka phone aate hi acting change", "source": "vault", "why": "Relatable"},
        {"title": "Bollywood interval ke baad hero alag kyun lagta hai", "source": "vault", "why": "Film hook"},
        {"title": "Auto wale bhaiya ka GPS dimaag", "source": "vault", "why": "Street comedy"},
        {"title": "Exam hall ka last 10 minute horror", "source": "vault", "why": "Student hook"},
        {"title": "Villain actually right tha kya", "source": "vault", "why": "Story hook"},
        {"title": "Woh scene jo cut ho gaya aur film badal gayi", "source": "vault", "why": "Rewind hook"},
        {"title": "Gaana dimaag mein kyun ghumta rehta hai", "source": "vault", "why": "Music hook"},
        {"title": "Series hate karke bhi khatam kyun karte ho", "source": "vault", "why": "OTT hook"},
        {"title": "Trailer jhoot kyun bolta hai", "source": "vault", "why": "Craft hook"},
        {"title": "Background extra ne scene chura liya", "source": "vault", "why": "Detail hook"},
        {"title": "Dost ka late aana aur 50 excuses", "source": "vault", "why": "Friendship comedy"},
        {"title": "WiFi chala gaya toh ghar ka scene", "source": "vault", "why": "Relatable"},
        {"title": "Cricket commentary vs ghar pe commentary", "source": "vault", "why": "Sports funny"},
        {"title": "Hero ka entry music dimaag mein kyun bajta hai", "source": "vault", "why": "Film hook"},
        {"title": "Online class mein camera off wala jeevan", "source": "vault", "why": "Student funny"},
        {"title": "Zomato wale bhaiya ka waiting game", "source": "vault", "why": "Street comedy"},
        {"title": "Interval mein popcorn khatam hone ka dard", "source": "vault", "why": "Cinema funny"},
        {"title": "Villain ka backstory hero se better kyun hota hai", "source": "vault", "why": "Story hook"},
    ]


def _prefer_entertainment(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def score(item: dict[str, Any]) -> int:
        blob = f"{item.get('title','')} {item.get('why','')} {item.get('source','')}".lower()
        return sum(1 for w in _FUN if w in blob)

    return sorted(items, key=score, reverse=True)


async def pick_topic(region: str | None = None) -> dict[str, Any]:
    return pick_topic_now()


def pick_topic_now() -> dict[str, Any]:
    import random

    used = {t.lower() for t in autopilot_used_topics()}
    pool = [item for item in _entertainment_vault() if item["title"].lower() not in used]
    if not pool:
        pool = list(_entertainment_vault())
    raw = random.choice(pool)
    return {
        "topic": raw["title"],
        "source": raw.get("source") or "vault",
        "why": raw.get("why") or "studio topic",
        "notes": raw["title"],
    }


def local_topics() -> list[dict[str, Any]]:
    used = {t.lower() for t in autopilot_used_topics()}
    items = [item for item in _entertainment_vault() if item["title"].lower() not in used]
    return items or list(_entertainment_vault())
