from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.paths import font

CAST = (
    {
        "id": "golu",
        "name": "Golu",
        "role": "overconfident dost",
        "tag": "GOLU",
        "subtitle": "USUALLY WRONG",
        "color": (255, 196, 32),
        "color_dark": (120, 72, 8),
        "voice": "hi-IN-MadhurNeural",
        "rate": "+11%",
        "pitch": "+4Hz",
        "look": (
            "A consistent 3D Pixar-style cartoon Indian young man named Golu, "
            "round face, messy black hair, bright yellow hoodie, big expressive eyes, "
            "always a little too sure of himself, same character every shot"
        ),
    },
    {
        "id": "pihu",
        "name": "Pihu",
        "role": "sharp roast queen",
        "tag": "PIHU",
        "subtitle": "HAS THE TWIST",
        "color": (255, 79, 154),
        "color_dark": (92, 16, 48),
        "voice": "hi-IN-SwaraNeural",
        "rate": "+5%",
        "pitch": "-2Hz",
        "look": (
            "A consistent 3D Pixar-style cartoon Indian young woman named Pihu, "
            "sharp jaw, short wavy black hair, magenta jacket, unimpressed smirk, "
            "the one who actually knows the twist, same character every shot"
        ),
    },
)


def by_name(name: str | None) -> dict[str, Any]:
    key = (name or "").strip().lower()
    for member in CAST:
        if member["name"].lower() == key or member["id"] == key:
            return member
    return CAST[0]


def pick_character(index: int) -> dict[str, Any]:
    return CAST[index % len(CAST)]


def spoken_line(text: str) -> str:
    line = re.sub(r"^(Golu|Pihu)\s*[:\-–]\s*", "", text or "", flags=re.I).strip()
    line = re.sub(r"\s+", " ", line)
    return line


def speaker_of(scene: dict[str, Any], index: int = 0) -> dict[str, Any]:
    named = (scene.get("character") or "").strip()
    if named:
        return by_name(named)
    guess = spoken_line(scene.get("text") or "")
    low = (scene.get("text") or "").lstrip().lower()
    if low.startswith("golu"):
        return by_name("Golu")
    if low.startswith("pihu"):
        return by_name("Pihu")
    if re.match(r"^golu\b", guess, re.I):
        return by_name("Golu")
    return pick_character(index)


def acting_prompt(scene: dict[str, Any], project: dict[str, Any], index: int = 0) -> str:
    member = speaker_of(scene, index)
    line = spoken_line(scene.get("text") or scene.get("on_screen") or "")[:180]
    topic = project.get("topic") or "this story"
    extra = (scene.get("visual_prompt") or "").strip()
    action = extra or f"acting this comedy beat: {line}"
    return (
        f"{member['look']}, {action}. "
        f"Story is about {topic}. Full body or mid-shot in frame, "
        f"exaggerated cartoon performance, cinematic comedy lighting, "
        f"rich background that matches the joke, no text, no letters, no watermark, no logo."
    )


def portrait_prompt(member: dict[str, Any]) -> str:
    return (
        f"{member['look']}, hero character portrait, mid-shot, looking at camera, "
        f"clean studio comedy lighting, detailed face, same design every time, "
        f"no text, no letters, no watermark, no logo."
    )


def cast_note() -> str:
    return (
        "Two cartoon hosts act every line. Golu is loud and usually wrong first. "
        "Pihu roasts him and drops the twist. Alternate speakers. "
        "Mark each scene with character Golu or Pihu. "
        "Do not write the names inside the spoken sentence unless they are talking to each other."
    )


def _face(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(font(name)), size)


def draw_mascot(name: str, size: tuple[int, int] = (720, 960)) -> Image.Image:
    """Brand fallback so Golu/Pihu are on screen even when AI stills fail."""
    member = by_name(name)
    w, h = size
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    accent = member["color"] + (255,)
    skin = (236, 188, 146, 255) if member["id"] == "golu" else (224, 170, 132, 255)
    hair = (22, 16, 14, 255)
    # body / hoodie
    d.rounded_rectangle((int(w * 0.16), int(h * 0.46), int(w * 0.84), int(h * 1.05)), radius=90, fill=accent)
    # head
    hx0, hy0, hx1, hy1 = int(w * 0.20), int(h * 0.08), int(w * 0.80), int(h * 0.62)
    d.ellipse((hx0, hy0, hx1, hy1), fill=skin)
    # hair
    if member["id"] == "golu":
        d.ellipse((hx0 - 10, hy0 - 30, hx1 + 10, hy0 + int(h * 0.22)), fill=hair)
        d.ellipse((hx0 + 20, hy0 + 10, hx0 + int(w * 0.22), hy0 + int(h * 0.18)), fill=hair)
        d.ellipse((hx1 - int(w * 0.22), hy0 + 6, hx1 - 10, hy0 + int(h * 0.20)), fill=hair)
    else:
        d.rounded_rectangle((hx0 + 30, hy0 - 8, hx1 - 30, hy0 + int(h * 0.16)), radius=40, fill=hair)
        d.pieslice((hx0 - 8, hy0 + 20, hx0 + int(w * 0.22), hy1 - 40), 90, 270, fill=hair)
        d.pieslice((hx1 - int(w * 0.22), hy0 + 20, hx1 + 8, hy1 - 40), 270, 90, fill=hair)
    # eyes
    eye_y = int(h * 0.32)
    lw = int(w * 0.07)
    if member["id"] == "golu":
        d.ellipse((int(w * 0.32), eye_y, int(w * 0.32) + lw, eye_y + lw), fill=(18, 14, 12, 255))
        d.ellipse((int(w * 0.58), eye_y, int(w * 0.58) + lw, eye_y + lw), fill=(18, 14, 12, 255))
        d.ellipse((int(w * 0.34), eye_y + 6, int(w * 0.34) + 10, eye_y + 16), fill=(255, 255, 255, 255))
        d.arc((int(w * 0.40), int(h * 0.44), int(w * 0.60), int(h * 0.54)), 20, 160, fill=(140, 60, 50, 255), width=6)
    else:
        d.rounded_rectangle((int(w * 0.30), eye_y + 8, int(w * 0.42), eye_y + 18), radius=4, fill=(18, 14, 12, 255))
        d.rounded_rectangle((int(w * 0.56), eye_y + 8, int(w * 0.68), eye_y + 18), fill=(18, 14, 12, 255), radius=4)
        d.arc((int(w * 0.42), int(h * 0.44), int(w * 0.58), int(h * 0.52)), 200, 340, fill=(140, 60, 50, 255), width=5)
    return im


def make_host_card(photo: Image.Image | None, character: str, dest: Path, height: int = 760) -> Path:
    member = by_name(character)
    width = int(height * 0.72)
    card = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((8, 8, width - 8, height - 8), radius=36, fill=(12, 10, 16, 235))
    d.rounded_rectangle((8, 8, width - 8, 18), radius=8, fill=member["color"] + (255,))
    inner = (28, 28, width - 28, height - 120)
    if photo is not None:
        from PIL import ImageOps

        fw, fh = inner[2] - inner[0], inner[3] - inner[1]
        face = ImageOps.fit(photo.convert("RGB"), (fw, fh), method=Image.Resampling.LANCZOS)
        card.paste(face, (inner[0], inner[1]))
    else:
        mascot = draw_mascot(member["name"], (inner[2] - inner[0], inner[3] - inner[1]))
        card.paste(mascot, (inner[0], inner[1]), mascot)
    bar_top = height - 108
    d.rounded_rectangle((20, bar_top, width - 20, height - 20), radius=22, fill=member["color"] + (255,))
    tag_f = _face("Montserrat-ExtraBold.ttf", 42)
    sub_f = _face("Montserrat-SemiBold.ttf", 18)
    tw = d.textlength(member["tag"], font=tag_f)
    d.text(((width - tw) / 2, bar_top + 14), member["tag"], font=tag_f, fill=member["color_dark"] + (255,))
    sw = d.textlength(member["subtitle"], font=sub_f)
    d.text(((width - sw) / 2, bar_top + 62), member["subtitle"], font=sub_f, fill=member["color_dark"] + (220,))
    dest.parent.mkdir(parents=True, exist_ok=True)
    card.save(dest)
    return dest


def make_graphics_overlay(
    size: tuple[int, int],
    scene: dict[str, Any],
    project: dict[str, Any],
    dest: Path,
    index: int,
    total: int,
) -> Path:
    w, h = size
    is_short = h > w
    member = speaker_of(scene, index)
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    accent = member["color"] + (255,)
    dark = (8, 8, 12, 200)

    # top chrome
    d.rounded_rectangle((28, 28, int(w * 0.42), 88), radius=22, fill=dark)
    d.ellipse((40, 42, 72, 74), fill=accent)
    chip_f = _face("Montserrat-Bold.ttf", 22)
    d.text((86, 46), f"SCENE {index + 1:02d}/{total:02d}", font=chip_f, fill=(244, 240, 232, 255))

    kind = scene.get("kind") or "narration"
    kicker = {
        "title": "COLD OPEN",
        "stat": "HOLD THIS",
        "outro": "YOUR MOVE",
        "narration": member["tag"],
    }.get(kind, member["tag"])
    kw = d.textlength(kicker, font=chip_f) + 36
    d.rounded_rectangle((w - 28 - kw, 28, w - 28, 88), radius=22, fill=accent)
    d.text((w - 10 - kw, 46), kicker, font=chip_f, fill=member["color_dark"] + (255,))

    # bottom designed caption stack
    punch = (scene.get("on_screen") or project.get("topic") or "").upper()
    punch_f = _face("BebasNeue.ttf", 72 if is_short else 64)
    cap_f = _face("Montserrat-Bold.ttf", 34 if is_short else 30)
    punch_lines = _wrap_simple(d, punch, punch_f, int(w * 0.86))[:2]
    spoken = spoken_line(scene.get("text") or "")
    cap_lines = _wrap_simple(d, spoken, cap_f, int(w * 0.84))[:3]

    block_h = 36 + len(punch_lines) * 78 + len(cap_lines) * 42 + 48
    y0 = h - block_h - (48 if is_short else 36)
    d.rounded_rectangle((20, y0, w - 20, h - 20), radius=28, fill=(8, 8, 14, 188))
    d.rectangle((20, y0, 20 + 14, h - 20), fill=accent)

    y = y0 + 22
    for line in punch_lines:
        tw = d.textlength(line, font=punch_f)
        d.text(((w - tw) / 2, y), line, font=punch_f, fill=(255, 248, 236, 255))
        y += 76
    y += 4
    for line in cap_lines:
        tw = d.textlength(line, font=cap_f)
        d.text(((w - tw) / 2, y), line, font=cap_f, fill=(236, 230, 220, 235))
        y += 40

    dest.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(dest)
    return dest


def _wrap_simple(draw: ImageDraw.ImageDraw, text: str, face: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if draw.textlength(trial, font=face) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def apply_soft_shadow(im: Image.Image) -> Image.Image:
    return im.filter(ImageFilter.GaussianBlur(0.4))
