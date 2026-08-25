from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import load_settings

LAST_ERROR: str | None = None

SYSTEM = """You are ChannelForge, an entertainment YouTube showrunner. Your job is to keep a stranger watching.

Write spoken-word narration people cannot skip. Sound like a sharp friend telling a story at 1am — not a textbook, not a news anchor, not a corporate explainer.

Retention rules:
- First 8 words must stop the scroll. No hello, no welcome, no "in this video".
- Open a loop in sentence one. Do not pay it off until the last third.
- Rehook every scene: a twist, a "wait", a "that's not even the part", a concrete image.
- Short sentences. Punch, then picture. Max ~20 words per sentence.
- One idea per scene. End scenes on unfinished business so the next scene is required.
- For Shorts: 4–6 scenes, cold open, one twist, one payoff, one follow CTA.
- For long: cold open story, three turns, then the real reason.
- Title: curiosity + specificity, under 60 characters. No all-caps spam. No fake "GONE WRONG".
- on_screen: 2–4 punchy words, not a sentence.
- visual_prompt: one filmable cinematic moment that matches THAT line — faces, weather, stadium lights, film sets, night streets. No text, no letters, no logos, no watermark.

Language: follow the brief. For hinglish, write Roman Hinglish like Indian YouTube comedy (Hindi + English mix, no Devanagari). For hindi, still prefer Roman Hinglish on_screen so captions render.
Funny. Two cartoon hosts act every line: Golu (loud, usually wrong) and Pihu (roast + twist). Alternate speakers. Put "character": "Golu" or "Pihu" on each scene.
Stay honest. Never invent statistics, quotes, or "leaked" events. If something is a theory, say it is a theory. No celebrity harassment, no medical advice, no political fight.

Return ONLY valid JSON with this shape:
{
  "title": "clickable title under 60 chars",
  "hook": "first 1-2 spoken sentences",
  "description": "YouTube description with a hook line, 2 short paragraphs, and a comment prompt",
  "tags": ["tag1", "tag2"],
  "scenes": [
     {
       "kind": "title|narration|stat|outro",
       "text": "spoken words for this shot only",
       "on_screen": "2-4 word graphic in Roman letters",
       "character": "Golu or Pihu",
       "visual_prompt": "the named cartoon host acting this line, consistent character design, no text, no letters, no logos, no watermark"
     }
  ]
}
The scenes together must be the full narration, in order, with no missing words.
visual_prompt must change every scene.
"""

GEMINI_MODELS = (
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
)


def _parse_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict) and data.get("scenes"):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]+\}", text)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        if isinstance(data, dict) and data.get("scenes"):
            return data
    except json.JSONDecodeError:
        return None
    return None


def last_error() -> str | None:
    return LAST_ERROR


GROQ_MODELS = (
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-120b",
    "meta-llama/llama-4-scout-17b-16e-instruct",
)


async def generate_script_llm(brief: str) -> dict[str, Any] | None:
    global LAST_ERROR
    LAST_ERROR = None
    settings = load_settings()
    if settings.get("groq_api_key"):
        data = await _groq(brief, settings)
        if data:
            return data
    if settings.get("openai_api_key"):
        data = await _openai(brief, settings)
        if data:
            return data
    if settings.get("anthropic_api_key"):
        data = await _anthropic(brief, settings)
        if data:
            return data
    if settings.get("gemini_api_key"):
        data = await _gemini(brief, settings)
        if data:
            return data
    return None


async def _groq(brief: str, settings: dict[str, Any]) -> dict[str, Any] | None:
    global LAST_ERROR
    preferred = settings.get("groq_model") or GROQ_MODELS[0]
    models: list[str] = []
    for name in (preferred, *GROQ_MODELS):
        if name and name not in models:
            models.append(name)
    errors: list[str] = []
    key = settings["groq_api_key"].strip()
    try:
        async with httpx.AsyncClient(timeout=22.0) as client:
            for model in models:
                res = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "temperature": 0.85,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": SYSTEM},
                            {"role": "user", "content": brief},
                        ],
                    },
                )
                if res.status_code >= 400:
                    errors.append(f"{model} {res.status_code}: {res.text[:160]}")
                    continue
                content = res.json()["choices"][0]["message"]["content"]
                parsed = _parse_json(content)
                if parsed:
                    parsed["engine"] = "groq"
                    parsed["model"] = model
                    return parsed
                errors.append(f"{model}: could not parse JSON script")
    except Exception as exc:
        LAST_ERROR = f"Groq error: {exc}"
        return None
    LAST_ERROR = "Groq failed. " + " | ".join(errors[-3:])
    return None


async def _openai(brief: str, settings: dict[str, Any]) -> dict[str, Any] | None:
    global LAST_ERROR
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings['openai_api_key']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.get("openai_model") or "gpt-4o-mini",
                    "temperature": 0.85,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": brief},
                    ],
                },
            )
        if res.status_code >= 400:
            LAST_ERROR = f"OpenAI {res.status_code}: {res.text[:240]}"
            return None
        content = res.json()["choices"][0]["message"]["content"]
        return _parse_json(content)
    except Exception as exc:
        LAST_ERROR = f"OpenAI error: {exc}"
        return None


async def _anthropic(brief: str, settings: dict[str, Any]) -> dict[str, Any] | None:
    global LAST_ERROR
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings["anthropic_api_key"],
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.get("anthropic_model") or "claude-3-5-haiku-latest",
                    "max_tokens": 4000,
                    "system": SYSTEM,
                    "messages": [{"role": "user", "content": brief}],
                },
            )
        if res.status_code >= 400:
            LAST_ERROR = f"Anthropic {res.status_code}: {res.text[:240]}"
            return None
        content = res.json()["content"][0]["text"]
        return _parse_json(content)
    except Exception as exc:
        LAST_ERROR = f"Anthropic error: {exc}"
        return None


async def _gemini(brief: str, settings: dict[str, Any]) -> dict[str, Any] | None:
    global LAST_ERROR
    preferred = settings.get("gemini_model") or GEMINI_MODELS[0]
    models: list[str] = []
    for name in (preferred, *GEMINI_MODELS):
        if name and name not in models:
            models.append(name)
    errors: list[str] = []
    key = settings["gemini_api_key"].strip()
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM}]},
        "contents": [{"parts": [{"text": brief}]}],
        "generationConfig": {"temperature": 0.85, "responseMimeType": "application/json"},
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            for model in models:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                res = await client.post(
                    url,
                    params={"key": key},
                    headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                    json=payload,
                )
                if res.status_code >= 400:
                    errors.append(f"{model} {res.status_code}: {res.text[:180]}")
                    continue
                body = res.json()
                parts = (((body.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
                text = "".join(p.get("text") or "" for p in parts)
                parsed = _parse_json(text)
                if parsed:
                    parsed["engine"] = "gemini"
                    parsed["model"] = model
                    return parsed
                errors.append(f"{model}: could not parse JSON script")
    except Exception as exc:
        LAST_ERROR = f"Gemini error: {exc}"
        return None
    LAST_ERROR = "Gemini failed. " + " | ".join(errors[-3:])
    return None
