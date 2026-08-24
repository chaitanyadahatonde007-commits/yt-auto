from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import load_settings

LAST_ERROR: str | None = None

SYSTEM = """You are ChannelForge, a sharp YouTube showrunner.
Write original, spoken-word narration. Short sentences. Concrete images. No hashtags in the script.
Never invent citations or fake statistics. If a fact is uncertain, phrase it as a question or a widely held view.
Return ONLY valid JSON with this shape:
{
  "title": "clickable title under 70 chars",
  "hook": "first 1-2 spoken sentences",
  "description": "YouTube description with 3 short paragraphs and a resources line",
  "tags": ["tag1", "tag2"],
  "scenes": [
     {"kind": "title|narration|stat|outro", "text": "spoken words", "on_screen": "3-6 word graphic"}
  ]
}
The scenes together must be the full narration, in order, with no missing words.
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


async def generate_script_llm(brief: str) -> dict[str, Any] | None:
    global LAST_ERROR
    LAST_ERROR = None
    settings = load_settings()
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
                    "temperature": 0.7,
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
        "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"},
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
