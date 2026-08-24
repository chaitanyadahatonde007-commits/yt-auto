from __future__ import annotations

import re
from typing import Any

import httpx

USER_AGENT = "ChannelForge/1.0 (YouTube automation studio; research@localhost)"


def _clean(text: str) -> str:
    text = re.sub(r"\[[\d,\s]+\]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", _clean(text))
    return [p.strip() for p in parts if len(p.strip()) > 25]


async def wikipedia_research(topic: str) -> dict[str, Any] | None:
    query = topic.strip()
    if not query:
        return None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    timeout = httpx.Timeout(8.0, connect=4.0)
    try:
        async with httpx.AsyncClient(headers=headers, timeout=timeout, follow_redirects=True) as client:
            search = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": 5,
                    "format": "json",
                    "utf8": 1,
                },
            )
            if search.status_code != 200:
                return None
            hits = (search.json().get("query") or {}).get("search") or []
            if not hits:
                return None
            title = hits[0]["title"]
            summary_res = await client.get(
                f"https://en.wikipedia.org/api/rest_v1/page/summary/{title.replace(' ', '_')}"
            )
            extract_res = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "prop": "extracts|pageimages",
                    "exintro": 0,
                    "explaintext": 1,
                    "exchars": 4000,
                    "titles": title,
                    "format": "json",
                    "pithumbsize": 1200,
                    "redirects": 1,
                },
            )
            summary = summary_res.json() if summary_res.status_code == 200 else {}
            extract_json = extract_res.json() if extract_res.status_code == 200 else {}
            pages = (extract_json.get("query") or {}).get("pages") or {}
            page = next(iter(pages.values()), {})
            extract = page.get("extract") or summary.get("extract") or ""
            facts = _sentences(extract)[:14]
            thumb = None
            if page.get("thumbnail"):
                thumb = page["thumbnail"].get("source")
            elif summary.get("thumbnail"):
                thumb = summary["thumbnail"].get("source")
            if not facts:
                return None
            return {
                "source": "wikipedia",
                "title": title,
                "url": summary.get("content_urls", {}).get("desktop", {}).get("page")
                or f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                "summary": _clean(summary.get("extract") or facts[0]),
                "facts": facts,
                "image": thumb,
            }
    except Exception:
        return None


def notes_research(topic: str, notes: str) -> dict[str, Any] | None:
    notes = (notes or "").strip()
    if not notes:
        return None
    facts = [ln.strip(" -•\t") for ln in re.split(r"[\n\r]+|(?<=[.!?])\s+", notes) if len(ln.strip()) > 12]
    return {
        "source": "notes",
        "title": topic,
        "url": None,
        "summary": facts[0] if facts else notes[:280],
        "facts": facts[:16],
        "image": None,
    }


async def gather_research(topic: str, notes: str = "") -> dict[str, Any]:
    wiki = await wikipedia_research(topic)
    extra = notes_research(topic, notes)
    news_facts: list[str] = []
    try:
        from app.services.newsapi import search_topic

        for art in await search_topic(topic, limit=6):
            line = art.get("description") or art.get("title") or ""
            if line:
                news_facts.append(line)
    except Exception:
        news_facts = []
    if wiki and extra:
        merged = list(dict.fromkeys(extra["facts"] + news_facts + wiki["facts"]))
        wiki["facts"] = merged[:16]
        wiki["notes"] = extra["facts"]
        if news_facts:
            wiki["source"] = "wikipedia+news"
        return wiki
    if wiki:
        if news_facts:
            wiki["facts"] = list(dict.fromkeys(news_facts + wiki["facts"]))[:16]
            wiki["source"] = "wikipedia+news"
        return wiki
    if extra:
        if news_facts:
            extra["facts"] = list(dict.fromkeys(extra["facts"] + news_facts))[:16]
            extra["source"] = "notes+news"
        return extra
    if news_facts:
        return {
            "source": "newsapi",
            "title": topic,
            "url": None,
            "summary": news_facts[0],
            "facts": news_facts[:16],
            "image": None,
        }
    return {
        "source": "studio",
        "title": topic,
        "url": None,
        "summary": f"A ChannelForge original briefing on {topic}.",
        "facts": [],
        "image": None,
    }
