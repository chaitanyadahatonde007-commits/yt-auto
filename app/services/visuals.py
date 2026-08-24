from __future__ import annotations

import hashlib
import math
import random
from pathlib import Path
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


def render_visuals(project: dict[str, Any], scenes: list[dict[str, Any]]) -> dict[str, Any]:
    fmt = project.get("format") or "long"
    size = (1080, 1920) if fmt == "short" else (1920, 1080)
    folder = project_dir(project["id"]) / "scenes"
    folder.mkdir(parents=True, exist_ok=True)
    outputs = []
    for i, scene in enumerate(scenes):
        frame = render_scene_frame(project, scene, i, len(scenes), size)
        rel = f"scenes/{scene.get('id') or f'sc{i+1:02d}'}.jpg"
        dest = project_dir(project["id"]) / rel
        frame.save(dest, quality=92, optimize=True)
        outputs.append(
            {
                "id": scene.get("id"),
                "path": rel,
                "kind": scene.get("kind"),
                "on_screen": scene.get("on_screen"),
                "duration": scene.get("duration"),
            }
        )
    return {"format": fmt, "width": size[0], "height": size[1], "scenes": outputs}
