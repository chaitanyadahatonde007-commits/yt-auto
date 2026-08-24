from __future__ import annotations

import hashlib
import random
import re
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from app.paths import font, project_dir
from app.services.visuals import MOOD_ACCENT, _fit_cover, _grain, _load_font, _plate_path, _vignette, _wrap


def _punchy_lines(project: dict[str, Any]) -> list[str]:
    topic = project.get("topic") or ""
    title = (project.get("script") or {}).get("title") or project.get("title") or topic or "WATCH THIS"
    source = topic if 2 <= len(re.findall(r"[A-Za-z0-9']+", topic)) <= 9 else title
    words = re.findall(r"[A-Za-z0-9']+", source)
    if not words:
        return ["WATCH THIS"]
    if len(words) <= 3:
        return [" ".join(words).upper()]
    mid = max(2, min(len(words) - 1, (len(words) + 1) // 2))
    for i in range(2, len(words) - 1):
        if words[i - 1].lower() in {"the", "of", "and", "vs", "a", "near", "for", "to"}:
            mid = i
            break
    return [" ".join(words[:mid]).upper(), " ".join(words[mid:]).upper()]


def render_thumbnail_variant(project: dict[str, Any], variant: int) -> Image.Image:
    size = (1280, 720)
    mood = project.get("visual_mood") or "ember"
    accent = MOOD_ACCENT.get(mood, (255, 72, 48))
    rng = random.Random(int(hashlib.sha256(f"{project['id']}:thumb:{variant}".encode()).hexdigest()[:12], 16))
    plate = Image.open(_plate_path(mood, variant + 3)).convert("RGB")
    canvas = _fit_cover(plate, size).convert("RGBA")

    layouts = ("left-stack", "center-blast", "split-bar")
    layout = layouts[variant % 3]

    wash = Image.new("RGBA", size, (6, 6, 10, 120))
    canvas = Image.alpha_composite(canvas, wash)

    # colored panel
    panel = Image.new("RGBA", size, (0, 0, 0, 0))
    pd = ImageDraw.Draw(panel)
    if layout == "left-stack":
        pd.polygon([(0, 0), (760, 0), (640, 720), (0, 720)], fill=(8, 8, 12, 188))
        pd.polygon([(640, 0), (690, 0), (570, 720), (520, 720)], fill=accent + (230,))
    elif layout == "center-blast":
        pd.rectangle((0, 430, 1280, 720), fill=(8, 8, 12, 200))
        pd.rectangle((0, 418, 1280, 434), fill=accent + (255,))
    else:
        pd.rectangle((70, 80, 1210, 640), fill=(8, 8, 12, 170))
        pd.rectangle((70, 80, 92, 640), fill=accent + (255,))
    canvas = Image.alpha_composite(canvas, panel)

    draw = ImageDraw.Draw(canvas)
    lines = _punchy_lines(project)
    display = _load_font("BebasNeue.ttf", 118 if layout != "center-blast" else 132)
    kicker_f = _load_font("Montserrat-Bold.ttf", 28)
    small = _load_font("Inter-Bold.ttf", 22)

    kicker = {
        0: "THE REAL MECHANISM",
        1: "WATCH BEFORE YOU ARGUE",
        2: "NOT THE USUAL TAKE",
    }[variant % 3]

    if layout == "left-stack":
        draw.text((72, 86), kicker, font=kicker_f, fill=accent + (255,))
        y = 170
        for line in lines[:3]:
            for wrapped in _wrap(draw, line, display, 620)[:2]:
                draw.text((72, y), wrapped, font=display, fill=(250, 246, 236, 255))
                y += 118
        draw.text((72, 620), "CHANNELFORGE", font=small, fill=(220, 216, 208, 200))
    elif layout == "center-blast":
        # huge one-two punch at bottom
        tw = draw.textlength(kicker, font=kicker_f)
        draw.text(((1280 - tw) / 2, 448), kicker, font=kicker_f, fill=accent + (255,))
        y = 500
        for line in lines[:2]:
            wrapped = _wrap(draw, line, display, 1180)
            for wline in wrapped[:1]:
                lw = draw.textlength(wline, font=display)
                draw.text(((1280 - lw) / 2, y), wline, font=display, fill=(255, 252, 245, 255))
                y += 118
    else:
        draw.text((130, 130), kicker, font=kicker_f, fill=accent + (255,))
        y = 210
        for line in lines[:3]:
            for wrapped in _wrap(draw, line, display, 980)[:2]:
                draw.text((130, y), wrapped, font=display, fill=(250, 246, 236, 255))
                y += 112
        # fake "big number" sticker
        num = str((rng.randint(3, 9)))
        nf = _load_font("BebasNeue.ttf", 180)
        draw.ellipse((980, 430, 1190, 640), fill=accent + (240,))
        nw = draw.textlength(num, font=nf)
        draw.text((1085 - nw / 2, 448), num, font=nf, fill=(12, 10, 10, 255))

    canvas = Image.alpha_composite(canvas, _vignette(size, 0.45))
    canvas = Image.alpha_composite(canvas, _grain(size, rng, 18))
    rgb = canvas.convert("RGB")
    rgb = ImageEnhance.Contrast(rgb).enhance(1.14)
    rgb = ImageEnhance.Color(rgb).enhance(1.08)
    rgb = ImageEnhance.Sharpness(rgb).enhance(1.15)
    return rgb


def render_thumbnails(project: dict[str, Any]) -> dict[str, Any]:
    folder = project_dir(project["id"])
    variants = []
    for i, name in enumerate(("thumb_a.jpg", "thumb_b.jpg", "thumb_c.jpg")):
        im = render_thumbnail_variant(project, i)
        im.save(folder / name, quality=93, optimize=True)
        variants.append(name)
    selected = project.get("thumbnail", {}).get("selected") if project.get("thumbnail") else None
    if selected not in variants:
        selected = variants[0]
    return {"variants": variants, "selected": selected}
