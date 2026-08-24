from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import load_settings

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


async def generate_script_llm(brief: str) -> dict[str, Any] | None:
    settings = load_settings()
    if settings.get("openai_api_key"):
        return await _openai(brief, settings)
    if settings.get("anthropic_api_key"):
        return await _anthropic(brief, settings)
    if settings.get("gemini_api_key"):
        return await _gemini(brief, settings)
    return None


async def _openai(brief: str, settings: dict[str, Any]) -> dict[str, Any] | None:
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
            return None
        content = res.json()["choices"][0]["message"]["content"]
        return _parse_json(content)
    except Exception:
        return None


async def _anthropic(brief: str, settings: dict[str, Any]) -> dict[str, Any] | None:
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
            return None
        content = res.json()["content"][0]["text"]
        return _parse_json(content)
    except Exception:
        return None


async def _gemini(brief: str, settings: dict[str, Any]) -> dict[str, Any] | None:
    model = settings.get("gemini_model") or "gemini-2.0-flash"
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            res = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key": settings["gemini_api_key"]},
                json={
                    "systemInstruction": {"parts": [{"text": SYSTEM}]},
                    "contents": [{"parts": [{"text": brief}]}],
                    "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"},
                },
            )
        if res.status_code >= 400:
            return None
        content = res.json()["candidates"][0]["content"]["parts"][0]["text"]
        return _parse_json(content)
    except Exception:
        return None
