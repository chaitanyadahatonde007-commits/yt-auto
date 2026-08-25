from __future__ import annotations

import asyncio
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
    host: Image.Image | None = None,
) -> Image.Image:
    from app.services.characters import make_graphics_overlay, speaker_of

    mood = project.get("visual_mood") or "magenta"
    rng = _seed(project["id"], scene.get("id") or str(index))
    painted = photo is not None
    base = (photo or Image.open(_plate_path(mood, index))).convert("RGB")
    frame = _fit_cover(base, (int(size[0] * 1.14), int(size[1] * 1.14)))
    max_x = frame.width - size[0]
    max_y = frame.height - size[1]
    ox = rng.randint(0, max(0, max_x))
    oy = rng.randint(0, max(0, max_y))
    canvas = frame.crop((ox, oy, ox + size[0], oy + size[1])).convert("RGBA")

    wash = 36 if painted or host is not None else 88
    canvas = Image.alpha_composite(canvas, Image.new("RGBA", size, (6, 6, 10, wash)))

    if host is not None:
        member = speaker_of(scene, index)
        card_h = int(size[1] * (0.46 if size[1] > size[0] else 0.58))
        card = host.convert("RGBA")
        card.thumbnail((int(size[0] * 0.78), card_h), Image.Resampling.LANCZOS)
        hx = (size[0] - card.width) // 2
        hy = int(size[1] * 0.16)
        canvas.paste(card, (hx, hy), card if card.mode == "RGBA" else None)
        bar = Image.new("RGBA", size, (0, 0, 0, 0))
        bd = ImageDraw.Draw(bar)
        bd.rectangle((0, 0, 16, size[1]), fill=member["color"] + (230,))
        canvas = Image.alpha_composite(canvas, bar)

    buf_dir = project_dir(project["id"]) / "overlays"
    overlay_path = buf_dir / f"_preview_{index}.png"
    make_graphics_overlay(size, scene, project, overlay_path, index, total)
    overlay = Image.open(overlay_path).convert("RGBA")
    canvas = Image.alpha_composite(canvas, overlay)
    canvas = Image.alpha_composite(canvas, _vignette(size, 0.48))
    canvas = Image.alpha_composite(canvas, _grain(size, rng, 16))
    rgb = canvas.convert("RGB")
    rgb = ImageEnhance.Contrast(rgb).enhance(1.1)
    rgb = ImageEnhance.Color(rgb).enhance(1.08)
    return rgb


async def _safe_still(coro, timeout: float) -> bool:
    try:
        return bool(await asyncio.wait_for(coro, timeout=timeout))
    except Exception:
        return False


async def _ensure_portraits(project: dict[str, Any], root: Path) -> dict[str, Path]:
    from app.services.characters import CAST, draw_mascot, portrait_prompt
    from app.services.gemini_images import generate_still

    folder = root / "cast"
    folder.mkdir(exist_ok=True)
    out: dict[str, Path] = {}
    for member in CAST:
        dest = folder / f"{member['id']}.jpg"
        fallback = folder / f"{member['id']}_mascot.png"
        if not fallback.exists():
            draw_mascot(member["name"]).save(fallback)
        if not dest.exists():
            ok = await _safe_still(generate_still(portrait_prompt(member), dest, aspect="9:16"), 22)
            if not ok or not dest.exists():
                Image.open(fallback).convert("RGB").save(dest, quality=90)
        out[member["name"]] = dest
        out[member["id"]] = dest
    return out


async def render_visuals(
    project: dict[str, Any],
    scenes: list[dict[str, Any]],
    progress: Callable[[int, int, str], None] | None = None,
) -> dict[str, Any]:
    from app.services.characters import make_graphics_overlay, make_host_card, speaker_of
    from app.services.gemini_images import generate_still, last_image_error, visual_prompt_for
    from app.services.pexels import fetch_still as pexels_still, fetch_video as pexels_video, last_error as pexels_error
    from app.services.pixabay import fetch_still as pixabay_still, fetch_video as pixabay_video, last_error as pixabay_error
    from app.services.wavespeed import (
        generate_video_i2v,
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
    overlay_dir = root / "overlays"
    overlay_dir.mkdir(exist_ok=True)
    portraits = await _ensure_portraits(project, root)
    outputs = []
    painted_n = 0
    pexels_stills = 0
    pixabay_stills = 0
    pexels_clips = 0
    pixabay_clips = 0
    motion_n = 0
    i2v_n = 0
    last_err = None
    used_pexels: set[int] = set()
    used_pixabay: set[int] = set()
    total = max(1, len(scenes))
    for i, scene in enumerate(scenes):
        if progress:
            progress(i, total, f"Scene {i + 1}/{total}: character, motion, graphics")
        sid = scene.get("id") or f"sc{i+1:02d}"
        member = speaker_of(scene, i)
        prompt = visual_prompt_for(scene, project, index=i)
        hint = " ".join(
            part
            for part in (
                member["name"],
                scene.get("on_screen") or "",
                project.get("topic") or "",
                "people talking comedy street india",
            )
            if part
        )
        photo = None
        source = "plate"
        raw = folder / f"{sid}_raw.jpg"
        still_budget = 4 if fmt == "short" else 8
        if i < still_budget:
            ok = await _safe_still(generate_still(prompt, raw, aspect=aspect), 22)
            if ok and raw.exists():
                photo = Image.open(raw)
                source = "ai"
                painted_n += 1
            elif await _safe_still(pexels_still(prompt, raw, aspect=aspect, hint=hint, index=i), 12) and raw.exists():
                photo = Image.open(raw)
                source = "pexels"
                pexels_stills += 1
            elif await _safe_still(pixabay_still(prompt, raw, aspect=aspect, hint=hint, index=i), 12) and raw.exists():
                photo = Image.open(raw)
                source = "pixabay"
                pixabay_stills += 1
            else:
                last_err = last_image_error() or pexels_error() or pixabay_error()

        portrait = None
        port_path = portraits.get(member["name"])
        if port_path and port_path.exists():
            portrait = Image.open(port_path)
        host_rel = f"overlays/{sid}_host.png"
        make_host_card(photo or portrait, member["name"], root / host_rel, height=760 if fmt == "short" else 640)
        overlay_rel = f"overlays/{sid}_gfx.png"
        make_graphics_overlay(size, scene, project, root / overlay_rel, i, len(scenes))

        frame = render_scene_frame(
            project,
            scene,
            i,
            len(scenes),
            size,
            photo=photo,
            host=Image.open(root / host_rel),
        )
        rel = f"scenes/{sid}.jpg"
        dest = root / rel
        frame.save(dest, quality=90, optimize=True)

        clip_rel = None
        clip_kind = None
        if i < (5 if fmt == "short" else 8):
            candidates: list[tuple[str, Path]] = []
            pex = motion_dir / f"{sid}_pexels.mp4"
            pix = motion_dir / f"{sid}_pixabay.mp4"
            if await _safe_still(pexels_video(prompt, pex, aspect=aspect, hint=hint, used=used_pexels, index=i), 16):
                candidates.append(("pexels", pex))
                pexels_clips += 1
            elif await _safe_still(pixabay_video(prompt, pix, aspect=aspect, hint=hint, used=used_pixabay, index=i), 16):
                candidates.append(("pixabay", pix))
                pixabay_clips += 1
            # Character motion: first two scenes only, hard timeout so Autopilot still finishes.
            if i < 2 and not video_blocked():
                still_src = raw if raw.exists() else dest
                i2v = motion_dir / f"{sid}_i2v.mp4"
                if await _safe_still(generate_video_i2v(prompt, still_src, i2v, duration=5), 40):
                    candidates.append(("i2v", i2v))
                    i2v_n += 1
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
                "host": host_rel,
                "overlay": overlay_rel,
                "character": member["name"],
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
        "character_clips": i2v_n,
        "gemini_error": last_err,
    }
