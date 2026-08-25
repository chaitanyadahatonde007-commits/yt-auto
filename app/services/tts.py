from __future__ import annotations

import asyncio
import json
import re
import wave
from pathlib import Path
from typing import Any

from app.paths import ESPEAK_DIR, ffmpeg_exe, project_dir
from app.services.script_engine import estimate_seconds, word_count

EDGE_VOICES = [
    {"id": "edge:en-US-AndrewNeural", "label": "Andrew · US neural", "gender": "masculine", "engine": "edge"},
    {"id": "edge:en-US-AriaNeural", "label": "Aria · US neural", "gender": "feminine", "engine": "edge"},
    {"id": "edge:en-US-BrianNeural", "label": "Brian · US neural", "gender": "masculine", "engine": "edge"},
    {"id": "edge:en-US-EmmaNeural", "label": "Emma · US neural", "gender": "feminine", "engine": "edge"},
    {"id": "edge:en-US-JennyNeural", "label": "Jenny · US neural", "gender": "feminine", "engine": "edge"},
    {"id": "edge:en-GB-RyanNeural", "label": "Ryan · British neural", "gender": "masculine", "engine": "edge"},
    {"id": "edge:en-GB-SoniaNeural", "label": "Sonia · British neural", "gender": "feminine", "engine": "edge"},
    {"id": "edge:en-AU-WilliamNeural", "label": "William · Australian neural", "gender": "masculine", "engine": "edge"},
    {"id": "edge:en-AU-NatashaNeural", "label": "Natasha · Australian neural", "gender": "feminine", "engine": "edge"},
    {"id": "edge:en-IN-NeerjaNeural", "label": "Neerja · Indian English neural", "gender": "feminine", "engine": "edge"},
    {"id": "edge:hi-IN-MadhurNeural", "label": "Madhur · Hindi neural", "gender": "masculine", "engine": "edge"},
    {"id": "edge:hi-IN-SwaraNeural", "label": "Swara · Hindi neural", "gender": "feminine", "engine": "edge"},
]

OPENAI_VOICES = [
    {"id": "openai:alloy", "label": "Alloy · OpenAI", "gender": "neutral", "engine": "openai"},
    {"id": "openai:echo", "label": "Echo · OpenAI", "gender": "masculine", "engine": "openai"},
    {"id": "openai:fable", "label": "Fable · OpenAI", "gender": "neutral", "engine": "openai"},
    {"id": "openai:onyx", "label": "Onyx · OpenAI", "gender": "masculine", "engine": "openai"},
    {"id": "openai:nova", "label": "Nova · OpenAI", "gender": "feminine", "engine": "openai"},
    {"id": "openai:shimmer", "label": "Shimmer · OpenAI", "gender": "feminine", "engine": "openai"},
]

GROQ_VOICES = [
    {"id": "groq:Fritz-PlayAI", "label": "Fritz · Groq PlayAI", "gender": "masculine", "engine": "groq"},
    {"id": "groq:Celeste-PlayAI", "label": "Celeste · Groq PlayAI", "gender": "feminine", "engine": "groq"},
    {"id": "groq:Mason-PlayAI", "label": "Mason · Groq PlayAI", "gender": "masculine", "engine": "groq"},
    {"id": "groq:Arista-PlayAI", "label": "Arista · Groq PlayAI", "gender": "feminine", "engine": "groq"},
    {"id": "groq:Thunder-PlayAI", "label": "Thunder · Groq PlayAI", "gender": "masculine", "engine": "groq"},
]

LOCAL_VOICES = [
    {"id": "local:en-us", "label": "Studio US · local", "gender": "masculine", "engine": "local", "espeak": "en-us", "speed": 138, "pitch": 42},
    {"id": "local:en-us-warm", "label": "Studio Warm · local", "gender": "feminine", "engine": "local", "espeak": "en-us", "speed": 142, "pitch": 62},
    {"id": "local:en-gb", "label": "Studio UK · local", "gender": "masculine", "engine": "local", "espeak": "en-gb", "speed": 136, "pitch": 38},
    {"id": "local:en-gb-bright", "label": "Studio Bright UK · local", "gender": "feminine", "engine": "local", "espeak": "en-gb", "speed": 144, "pitch": 58},
    {"id": "local:hi", "label": "Studio Hindi · local", "gender": "masculine", "engine": "local", "espeak": "hi", "speed": 140, "pitch": 44},
]


def list_voices() -> list[dict[str, Any]]:
    from app.config import load_settings

    voices = list(LOCAL_VOICES)
    voices.extend(EDGE_VOICES)
    if load_settings().get("groq_api_key"):
        voices.extend(GROQ_VOICES)
    if load_settings().get("openai_api_key"):
        voices.extend(OPENAI_VOICES)
    return [
        {k: v for k, v in voice.items() if k in {"id", "label", "gender", "engine"}}
        for voice in voices
    ]


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+|[.,!?;:—-]", text)


def _words_only(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+", text)


def align_words(text: str, duration: float) -> list[dict[str, Any]]:
    tokens = _tokenize(text)
    if not tokens:
        return []
    weights = []
    for tok in tokens:
        if re.fullmatch(r"[.,!?;:—-]", tok):
            weights.append(0.35)
        else:
            weights.append(max(0.18, len(tok) * 0.075))
    total_w = sum(weights) or 1.0
    t = 0.0
    words = []
    for tok, w in zip(tokens, weights):
        dur = duration * (w / total_w)
        if re.fullmatch(r"[A-Za-z0-9']+", tok):
            words.append({"word": tok, "start": round(t, 3), "end": round(t + dur, 3)})
        t += dur
    return words


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        return frames / float(rate or 1)


async def ffprobe_duration(path: Path) -> float:
    if path.suffix.lower() == ".wav":
        try:
            return wav_duration(path)
        except Exception:
            pass
    proc = await asyncio.create_subprocess_exec(
        ffmpeg_exe(),
        "-i",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    text = err.decode("utf-8", errors="ignore")
    match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not match:
        return estimate_seconds(path.name)
    h, m, s = match.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


async def _to_wav(src: Path, dest: Path) -> None:
    if src.suffix.lower() == ".wav" and src != dest:
        dest.write_bytes(src.read_bytes())
        return
    if src == dest and src.suffix.lower() == ".wav":
        return
    proc = await asyncio.create_subprocess_exec(
        ffmpeg_exe(),
        "-y",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        "44100",
        str(dest),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0 or not dest.exists():
        raise RuntimeError(err.decode("utf-8", errors="ignore")[-400:] or "audio convert failed")


async def synthesize(project: dict[str, Any], text: str, voice_id: str | None = None) -> dict[str, Any]:
    voice_id = voice_id or project.get("voice") or ""
    lang = (project.get("language") or "").lower()
    if not voice_id or (lang in {"hinglish", "hindi"} and voice_id.startswith("local:en")):
        voice_id = "edge:hi-IN-MadhurNeural"
    folder = project_dir(project["id"])
    wav_path = folder / "voice.wav"
    raw_path = folder / "voice_raw"
    last_error = None

    engines = _engine_order(voice_id)
    for engine, spec in engines:
        try:
            if engine == "edge":
                words = await _edge(text, spec, raw_path.with_suffix(".mp3"))
                await _to_wav(raw_path.with_suffix(".mp3"), wav_path)
            elif engine == "openai":
                await _openai(text, spec, raw_path.with_suffix(".mp3"))
                await _to_wav(raw_path.with_suffix(".mp3"), wav_path)
                words = None
            elif engine == "groq":
                await _groq_tts(text, spec, raw_path.with_suffix(".wav"))
                await _to_wav(raw_path.with_suffix(".wav"), wav_path)
                words = None
            elif engine == "gtts":
                lang = "hi" if "hi" in voice_id or spec == "hi" else "en"
                await _gtts(text, raw_path.with_suffix(".mp3"), lang=lang)
                await _to_wav(raw_path.with_suffix(".mp3"), wav_path)
                words = None
            else:
                await _espeak(text, spec, wav_path)
                words = None
            duration = await ffprobe_duration(wav_path)
            if duration < 0.4:
                raise RuntimeError("voice file too short")
            aligned = words if words else align_words(text, duration)
            return {
                "path": "voice.wav",
                "duration": round(duration, 3),
                "voice": voice_id,
                "engine": engine,
                "words": aligned,
                "word_count": word_count(text),
            }
        except Exception as exc:
            last_error = exc
            continue
    raise RuntimeError(f"All voice engines failed: {last_error}")


def _engine_order(voice_id: str) -> list[tuple[str, Any]]:
    order: list[tuple[str, Any]] = []
    if voice_id.startswith("edge:"):
        order.append(("edge", voice_id.split(":", 1)[1]))
    elif voice_id.startswith("openai:"):
        order.append(("openai", voice_id.split(":", 1)[1]))
    elif voice_id.startswith("groq:"):
        order.append(("groq", voice_id.split(":", 1)[1]))
    else:
        spec = next((v for v in LOCAL_VOICES if v["id"] == voice_id), LOCAL_VOICES[0])
        order.append(("local", spec))
    # Fallbacks
    from app.config import load_settings

    hindi = voice_id.startswith("edge:hi-") or voice_id == "local:hi"
    if hindi:
        if not any(e[0] == "edge" and str(e[1]).startswith("hi-") for e in order):
            order.append(("edge", "hi-IN-MadhurNeural"))
        order.append(("gtts", "hi"))
        hi_local = next((v for v in LOCAL_VOICES if v["id"] == "local:hi"), None)
        if hi_local:
            order.append(("local", hi_local))
        return order
    if load_settings().get("groq_api_key") and not any(e[0] == "groq" for e in order):
        order.append(("groq", "Fritz-PlayAI"))
    if not any(e[0] == "edge" for e in order):
        order.append(("edge", "en-IN-NeerjaNeural"))
    order.append(("gtts", "en"))
    if not any(e[0] == "local" for e in order):
        order.append(("local", LOCAL_VOICES[0]))
    return order


async def _edge(text: str, voice: str, dest: Path) -> list[dict[str, Any]]:
    import edge_tts

    dest.parent.mkdir(parents=True, exist_ok=True)
    communicate = edge_tts.Communicate(text, voice)
    words: list[dict[str, Any]] = []
    with dest.open("wb") as handle:
        async def _run() -> None:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    handle.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / 10_000_000
                    dur = chunk["duration"] / 10_000_000
                    words.append(
                        {
                            "word": chunk.get("text") or "",
                            "start": round(start, 3),
                            "end": round(start + dur, 3),
                        }
                    )

        await asyncio.wait_for(_run(), timeout=90)
    if dest.stat().st_size < 1000:
        raise RuntimeError("edge-tts returned empty audio")
    return words


async def _openai(text: str, voice: str, dest: Path) -> None:
    from app.config import load_settings

    settings = load_settings()
    key = settings.get("openai_api_key")
    if not key:
        raise RuntimeError("OpenAI key missing")
    import httpx

    async with httpx.AsyncClient(timeout=90.0) as client:
        res = await client.post(
            "https://api.openai.com/v1/audio/speech",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": "tts-1", "voice": voice, "input": text, "format": "mp3"},
        )
    if res.status_code >= 400:
        raise RuntimeError(res.text[:300])
    dest.write_bytes(res.content)


async def _gtts(text: str, dest: Path, lang: str = "en") -> None:
    from gtts import gTTS

    def _run() -> None:
        tts = gTTS(text=text, lang=lang or "en")
        tts.save(str(dest))

    await asyncio.wait_for(asyncio.to_thread(_run), timeout=40)
    if not dest.exists() or dest.stat().st_size < 500:
        raise RuntimeError("gTTS empty")


def _chunk_text(text: str, limit: int = 480) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    buf = ""
    for sent in sentences:
        if not sent:
            continue
        if buf and len(buf) + 1 + len(sent) > limit:
            chunks.append(buf)
            buf = sent
        else:
            buf = f"{buf} {sent}".strip()
    if buf:
        chunks.append(buf)
    return chunks or [text]


async def _espeak(text: str, spec: dict[str, Any], dest: Path) -> None:
    js = ESPEAK_DIR / "espeak-ng.js"
    wasm = ESPEAK_DIR / "espeak-ng.wasm"
    if not js.exists() or not wasm.exists():
        raise RuntimeError("local espeak runtime missing")
    dest.parent.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    for i, chunk in enumerate(_chunk_text(text)):
        part = dest.parent / f"_esp_{i}.wav"
        await _espeak_chunk(chunk, spec, part, js)
        parts.append(part)
    if len(parts) == 1:
        dest.write_bytes(parts[0].read_bytes())
        return
    listing = dest.parent / "_esp_concat.txt"
    listing.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
    proc = await asyncio.create_subprocess_exec(
        ffmpeg_exe(),
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(listing),
        "-c",
        "copy",
        str(dest),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0 or not dest.exists():
        raise RuntimeError(err.decode("utf-8", errors="ignore")[-400:] or "voice concat failed")


async def _espeak_chunk(text: str, spec: dict[str, Any], dest: Path, js: Path) -> None:
    runner = dest.with_suffix(".mjs")
    runner.write_text(
        f"""
import {{ writeFileSync }} from 'fs';
import ESpeakNg from {json.dumps(js.as_posix())};

const espeak = await ESpeakNg({{
  arguments: [
    '-w', '/out.wav',
    '-s', '{int(spec.get("speed") or 138)}',
    '-p', '{int(spec.get("pitch") or 45)}',
    '-v', '{spec.get("espeak") or "en-us"}',
    {json.dumps(text)}
  ]
}});
const wav = espeak.FS.readFile('/out.wav');
writeFileSync({json.dumps(str(dest))}, wav);
""",
        encoding="utf-8",
    )
    proc = await asyncio.create_subprocess_exec(
        "node",
        str(runner),
        cwd=str(js.parent),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await asyncio.wait_for(proc.communicate(), timeout=45)
    if proc.returncode != 0 or not dest.exists():
        raise RuntimeError((err or out).decode("utf-8", errors="ignore")[-500:] or "espeak failed")


def retimed_scenes(script: dict[str, Any], voiceover: dict[str, Any]) -> list[dict[str, Any]]:
    scenes = [dict(s) for s in script.get("scenes") or []]
    words = voiceover.get("words") or []
    duration = float(voiceover.get("duration") or 0)
    if not scenes:
        return scenes
    if not words or duration <= 0:
        # proportional
        weights = [max(1, word_count(s["text"])) for s in scenes]
        total = sum(weights) or 1
        t = 0.0
        target = duration or sum(float(s.get("duration") or 0) for s in scenes)
        for scene, w in zip(scenes, weights):
            d = target * (w / total)
            scene["start"] = round(t, 3)
            scene["duration"] = round(d, 3)
            scene["end"] = round(t + d, 3)
            t += d
        return scenes

    cursor = 0
    t = 0.0
    for i, scene in enumerate(scenes):
        n = max(1, word_count(scene["text"]))
        chunk = words[cursor : cursor + n]
        cursor += n
        if chunk:
            start = float(chunk[0]["start"])
            end = float(chunk[-1]["end"])
        else:
            start = t
            end = t + float(scene.get("duration") or 2)
        if i == len(scenes) - 1:
            end = max(end, duration)
        scene["start"] = round(start, 3)
        scene["end"] = round(max(end, start + 1.2), 3)
        scene["duration"] = round(scene["end"] - scene["start"], 3)
        t = scene["end"]
    return scenes
