from __future__ import annotations

import hashlib
import math
import random
from pathlib import Path
from collections.abc import Callable
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from app.paths import PLATES_DIR, font, project_dir

MOOD_PLATES = {
    "ember": "plate_ember.jpg",
    "navy": "plate_navy.jpg",
    "teal": "plate_teal.jpg",
    "violet": "plate_violet.jpg",
    "amber": "plate_amber.jpg",
    "steel": "plate_steel.jpg",
    "forest": "plate_forest.jpg",
    "magenta": "plate_magenta.jpg",
}

MOOD_ACCENT = {
    "ember": (255, 72, 48),
    "navy": (232, 196, 92),
    "teal": (72, 224, 198),
    "violet": (214, 132, 255),
    "amber": (255, 176, 64),
    "steel": (186, 210, 230),
    "forest": (198, 220, 120),
    "magenta": (255, 79, 154),
}


def _load_font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(font(name)), size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font_obj: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if draw.textlength(trial, font=font_obj) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines[:6]


def _plate_path(mood: str, index: int) -> Path:
    names = list(MOOD_PLATES.values())
    preferred = MOOD_PLATES.get(mood, names[0])
    ordered = [preferred] + [n for n in names if n != preferred]
    name = ordered[index % len(ordered)]
    path = PLATES_DIR / name
    if path.exists():
        return path
    available = sorted(PLATES_DIR.glob("plate_*.jpg"))
    if available:
        return available[index % len(available)]
    raise FileNotFoundError("No cinematic plates installed")


def _seed(project_id: str, scene_id: str) -> random.Random:
    digest = hashlib.sha256(f"{project_id}:{scene_id}".encode()).hexdigest()
    return random.Random(int(digest[:12], 16))


def _fit_cover(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(im, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def _grain(size: tuple[int, int], rng: random.Random, opacity: int = 28) -> Image.Image:
    w, h = size
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    px = overlay.load()
    step = 2
    for y in range(0, h, step):
        for x in range(0, w, step):
            v = rng.randint(0, 255)
            a = rng.randint(0, opacity)
            px[x, y] = (v, v, v, a)
    return overlay.filter(ImageFilter.GaussianBlur(0.4))


def _vignette(size: tuple[int, int], strength: float = 0.72) -> Image.Image:
    w, h = size
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((-int(w * 0.08), -int(h * 0.12), int(w * 1.08), int(h * 1.12)), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(max(w, h) // 14))
    shade = Image.new("RGBA", size, (0, 0, 0, int(255 * strength)))
    inv = ImageOps.invert(mask)
    shade.putalpha(inv)
    return shade


def render_scene_frame(
    project: dict[str, Any],
    scene: dict[str, Any],
    index: int,
    total: int,
    size: tuple[int, int],
    photo: Image.Image | None = None,
) -> Image.Image:
    mood = project.get("visual_mood") or "ember"
    rng = _seed(project["id"], scene.get("id") or str(index))
    painted = photo is not None
    base = (photo or Image.open(_plate_path(mood, index))).convert("RGB")
    # generate slightly larger for Ken Burns
    frame = _fit_cover(base, (int(size[0] * 1.18), int(size[1] * 1.18)))
    # unique crop origin
    max_x = frame.width - size[0]
    max_y = frame.height - size[1]
    ox = rng.randint(0, max(0, max_x))
    oy = rng.randint(0, max(0, max_y))
    canvas = frame.crop((ox, oy, ox + size[0], oy + size[1])).convert("RGBA")

    accent = MOOD_ACCENT.get(mood, (255, 72, 48))
    kind = scene.get("kind") or "narration"
    wash = 70 if painted else (118 if kind != "title" else 150)
    dark = Image.new("RGBA", size, (6, 6, 10, wash))
    canvas = Image.alpha_composite(canvas, dark)

    # light slab
    slab = Image.new("RGBA", size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(slab)
    if kind == "title":
        sd.rectangle((0, int(size[1] * 0.52), size[0], size[1]), fill=(8, 8, 12, 150))
    elif kind == "outro":
        sd.rectangle((int(size[0] * 0.08), int(size[1] * 0.32), int(size[0] * 0.92), int(size[1] * 0.72)), fill=(8, 8, 12, 160))
    else:
        sd.rectangle((0, 0, 14, size[1]), fill=accent + (220,))
    canvas = Image.alpha_composite(canvas, slab)

    draw = ImageDraw.Draw(canvas)
    w, h = size
    is_short = project.get("format") == "short"

    kicker_size = 28 if not is_short else 34
    display_size = 92 if not is_short else 86
    if kind == "title":
        display_size = 110 if not is_short else 96
    if kind == "stat":
        display_size = 120 if not is_short else 100

    kicker_font = _load_font("Montserrat-SemiBold.ttf", kicker_size)
    display_font = _load_font("BebasNeue.ttf", display_size)
    body_font = _load_font("Inter-Medium.ttf", 26 if not is_short else 24)
    small_font = _load_font("Inter-Regular.ttf", 20)

    kicker = {
        "title": "CHANNELFORGE  ·  OPEN",
        "stat": "HOLD THIS",
        "outro": "STAY IN THE ROOM",
        "narration": f"SCENE {index + 1:02d} / {total:02d}",
    }.get(kind, "SCENE")
    if is_short:
        kicker = kicker.replace("CHANNELFORGE  ·  OPEN", "WATCH THIS")

    on_screen = (scene.get("on_screen") or "").upper()
    topic = (project.get("topic") or "").upper()

    margin = int(w * 0.07)
    max_text_w = int(w * 0.86)
    y = int(h * (0.18 if is_short else 0.16))
    if kind == "title":
        y = int(h * 0.38)
    if kind == "outro":
        y = int(h * 0.38)

    draw.text((margin, int(h * 0.07)), kicker, font=kicker_font, fill=accent + (255,))

    lines = _wrap(draw, on_screen, display_font, max_text_w)
    if not lines:
        lines = _wrap(draw, topic, display_font, max_text_w)
    for line in lines:
        draw.text((margin, y), line, font=display_font, fill=(244, 240, 232, 255))
        y += display_size + 8

    # gold rule
    draw.rectangle((margin, y + 10, margin + 120, y + 16), fill=accent + (255,))

    snippet = scene.get("text") or ""
    if not is_short and not painted:
        snippet_lines = _wrap(draw, snippet, body_font, int(w * 0.62))[:3]
        sy = y + 36
        for line in snippet_lines:
            draw.text((margin, sy), line, font=body_font, fill=(226, 222, 214, 220))
            sy += 34

    draw.text((margin, h - 56), (project.get("title") or topic)[:42], font=small_font, fill=(200, 196, 188, 180))
    draw.text((w - margin - 160, h - 56), "FORGE / AUTO", font=small_font, fill=(200, 196, 188, 160))

    canvas = Image.alpha_composite(canvas, _vignette(size, 0.62))
    canvas = Image.alpha_composite(canvas, _grain(size, rng, 22))
    rgb = canvas.convert("RGB")
    rgb = ImageEnhance.Contrast(rgb).enhance(1.08)
    rgb = ImageEnhance.Color(rgb).enhance(1.04)
    return rgb


async def render_visuals(
    project: dict[str, Any],
    scenes: list[dict[str, Any]],
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    from app.services.gemini_images import generate_still, last_image_error, visual_prompt_for
    from app.services.pexels import fetch_still as pexels_still, fetch_video as pexels_video, last_error as pexels_error
    from app.services.pixabay import fetch_still as pixabay_still, fetch_video as pixabay_video, last_error as pixabay_error
    from app.services.wavespeed import (
        generate_video_i2v,
        generate_video_t2v,
        last_error as ws_error,
        pick_best_clip,
        video_blocked,
    )

    fmt = project.get("format") or "long"
    size = (1080, 1920) if fmt == "short" else (1920, 1080)
    aspect = "9:16" if fmt == "short" else "16:9"
    root = project_dir(project["id"])
    folder = root / "scenes"
    folder.mkdir(parents=True, exist_ok=True)
    motion_dir = root / "motion"
    motion_dir.mkdir(exist_ok=True)
    outputs = []
    painted_n = 0
    pexels_stills = 0
    pixabay_stills = 0
    pexels_clips = 0
    pixabay_clips = 0
    motion_n = 0
    last_err = None
    used_pexels: set[int] = set()
    used_pixabay: set[int] = set()
    total = max(1, len(scenes))
    for i, scene in enumerate(scenes):
        if progress:
            progress(i, total, f"Scene {i + 1}/{total}: stills and motion")
        sid = scene.get("id") or f"sc{i+1:02d}"
        prompt = visual_prompt_for(scene, project)
        hint = scene.get("on_screen") or project.get("topic") or ""
        photo = None
        source = "plate"
        raw = folder / f"{sid}_raw.jpg"
        if i < 12:
            ok = await generate_still(prompt, raw, aspect=aspect)
            if ok and raw.exists():
                photo = Image.open(raw)
                source = "ai"
                painted_n += 1
            elif await pexels_still(prompt, raw, aspect=aspect, hint=hint, index=i) and raw.exists():
                photo = Image.open(raw)
                source = "pexels"
                pexels_stills += 1
            elif await pixabay_still(prompt, raw, aspect=aspect, hint=hint, index=i) and raw.exists():
                photo = Image.open(raw)
                source = "pixabay"
                pixabay_stills += 1
            else:
                last_err = last_image_error() or pexels_error() or pixabay_error()
        frame = render_scene_frame(project, scene, i, len(scenes), size, photo=photo)
        rel = f"scenes/{sid}.jpg"
        dest = root / rel
        frame.save(dest, quality=92, optimize=True)

        clip_rel = None
        clip_kind = None
        if i < 8:
            candidates: list[tuple[str, Path]] = []
            still_src = raw if raw.exists() else dest
            pex = motion_dir / f"{sid}_pexels.mp4"
            pix = motion_dir / f"{sid}_pixabay.mp4"
            i2v = motion_dir / f"{sid}_i2v.mp4"
            t2v = motion_dir / f"{sid}_t2v.mp4"
            dur = max(4, min(8, int(round(float(scene.get("duration") or 5)))))
            if await pexels_video(prompt, pex, aspect=aspect, hint=hint, used=used_pexels, index=i):
                candidates.append(("pexels", pex))
                pexels_clips += 1
            if await pixabay_video(prompt, pix, aspect=aspect, hint=hint, used=used_pixabay, index=i):
                candidates.append(("pixabay", pix))
                pixabay_clips += 1
            # AI motion only for the first two scenes, or if stock found nothing.
            want_ai = (i < 2 or not candidates) and not video_blocked()
            if want_ai:
                if progress:
                    progress(i, total, f"Scene {i + 1}/{total}: trying WaveSpeed motion")
                if await generate_video_i2v(prompt, still_src, i2v, duration=dur):
                    candidates.append(("i2v", i2v))
                if not candidates and await generate_video_t2v(prompt, t2v, aspect=aspect, duration=dur):
                    candidates.append(("t2v", t2v))
            winner = await pick_best_clip(candidates)
            if winner:
                clip_kind, clip_path = winner
                chosen = motion_dir / f"{sid}_best.mp4"
                chosen.write_bytes(clip_path.read_bytes())
                clip_rel = f"motion/{sid}_best.mp4"
                motion_n += 1
            elif not last_err:
                last_err = ws_error() or pexels_error() or pixabay_error()

        outputs.append(
            {
                "id": sid,
                "path": rel,
                "clip": clip_rel,
                "clip_kind": clip_kind,
                "kind": scene.get("kind"),
                "on_screen": scene.get("on_screen"),
                "visual_prompt": prompt,
                "source": source,
                "duration": scene.get("duration"),
            }
        )
    return {
        "format": fmt,
        "width": size[0],
        "height": size[1],
        "scenes": outputs,
        "gemini_images": painted_n,
        "pexels_stills": pexels_stills,
        "pixabay_stills": pixabay_stills,
        "pexels_clips": pexels_clips,
        "pixabay_clips": pixabay_clips,
        "motion_clips": motion_n,
        "gemini_error": last_err,
    }
