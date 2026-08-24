from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.paths import ffmpeg_exe, font, project_dir
from app.services.tts import ffprobe_duration
from app.services.visuals import _wrap


def _esc_filter_path(path: Path) -> str:
    text = path.resolve().as_posix()
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _wrap_caption(text: str, width: int = 34) -> str:
    words = (text or "").split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = " ".join(current + [word])
        if len(trial) > width and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
        if len(lines) == 3:
            break
    if current and len(lines) < 3:
        lines.append(" ".join(current))
    return "\n".join(lines)


def _stamp_caption(image_path: Path, dest: Path, caption: str, is_short: bool) -> None:
    im = Image.open(image_path).convert("RGBA")
    w, h = im.size
    overlay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    size = 46 if is_short else 40
    face = ImageFont.truetype(str(font("Montserrat-Bold.ttf")), size)
    max_w = int(w * 0.86)
    lines = _wrap(draw, caption, face, max_w)[:4]
    if not lines:
        overlay.convert("RGB")
        im.convert("RGB").save(dest, quality=92)
        return
    line_h = size + 10
    block_h = line_h * len(lines) + 36
    y0 = int(h * (0.58 if is_short else 0.74))
    pad_x = int(w * 0.06)
    draw.rounded_rectangle(
        (pad_x - 16, y0 - 18, w - pad_x + 16, y0 + block_h),
        radius=18,
        fill=(8, 8, 12, 150),
    )
    y = y0
    for line in lines:
        tw = draw.textlength(line, font=face)
        x = (w - tw) / 2
        # outline
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2)):
            draw.text((x + dx, y + dy), line, font=face, fill=(10, 10, 14, 220))
        draw.text((x, y), line, font=face, fill=(244, 241, 236, 255))
        y += line_h
    out = Image.alpha_composite(im, overlay).convert("RGB")
    out.save(dest, quality=92)


async def _run_ffmpeg(args: list[str]) -> None:
    proc = await asyncio.create_subprocess_exec(
        ffmpeg_exe(),
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        tail = err.decode("utf-8", errors="ignore")[-1200:]
        raise RuntimeError(f"ffmpeg failed:\n{tail}")


async def _scene_clip(
    image: Path,
    dest: Path,
    duration: float,
    size: tuple[int, int],
    index: int,
    caption: str,
) -> None:
    duration = max(1.2, duration)
    w, h = size
    # overscan for pan
    sw, sh = int(w * 1.16) // 2 * 2, int(h * 1.16) // 2 * 2
    if index % 4 == 0:
        x_expr = "0"
        y_expr = f"(in_h-out_h)*t/{duration:.3f}"
    elif index % 4 == 1:
        x_expr = f"(in_w-out_w)*t/{duration:.3f}"
        y_expr = "0"
    elif index % 4 == 2:
        x_expr = f"(in_w-out_w)*(1-t/{duration:.3f})"
        y_expr = f"(in_h-out_h)*0.4"
    else:
        x_expr = f"(in_w-out_w)*0.5"
        y_expr = f"(in_h-out_h)*(1-t/{duration:.3f})"

    fade = min(0.28, duration / 6)
    fade_out_start = max(0.0, duration - fade)
    captioned = dest.with_suffix(".jpg")
    _stamp_caption(image, captioned, caption, is_short=h > w)

    vf = (
        f"scale={sw}:{sh}:force_original_aspect_ratio=increase,"
        f"crop={sw}:{sh},"
        f"crop={w}:{h}:x='{x_expr}':y='{y_expr}',"
        f"fade=t=in:st=0:d={fade:.2f},"
        f"fade=t=out:st={fade_out_start:.2f}:d={fade:.2f},"
        f"format=yuv420p"
    )
    await _run_ffmpeg(
        [
            "-y",
            "-loop",
            "1",
            "-framerate",
            "30",
            "-t",
            f"{duration:.3f}",
            "-i",
            str(captioned),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(dest),
        ]
    )


async def _from_video(
    source: Path,
    dest: Path,
    duration: float,
    size: tuple[int, int],
) -> None:
    duration = max(1.2, duration)
    w, h = size
    fade = min(0.28, duration / 6)
    fade_out = max(0.0, duration - fade)
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},"
        f"fade=t=in:st=0:d={fade:.2f},"
        f"fade=t=out:st={fade_out:.2f}:d={fade:.2f},"
        f"format=yuv420p"
    )
    await _run_ffmpeg(
        [
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(source),
            "-t",
            f"{duration:.3f}",
            "-vf",
            vf,
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(dest),
        ]
    )


async def _make_bgm(dest: Path, duration: float) -> None:
    duration = max(2.0, duration)
    await _run_ffmpeg(
        [
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anoisesrc=color=pink:r=44100:d={duration:.3f},lowpass=f=260,highpass=f=50,volume=0.07",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=98:sample_rate=44100:duration={duration:.3f},volume=0.025",
            "-filter_complex",
            "amix=inputs=2:duration=longest,alimiter=limit=0.15",
            str(dest),
        ]
    )


async def compose_video(project: dict[str, Any]) -> dict[str, Any]:
    folder = project_dir(project["id"])
    script = project.get("script") or {}
    visuals = project.get("visuals") or {}
    voiceover = project.get("voiceover") or {}
    scenes = script.get("scenes") or []
    visual_map = {item["id"]: item for item in (visuals.get("scenes") or [])}
    if not scenes:
        raise RuntimeError("No scenes to render")
    voice_path = folder / (voiceover.get("path") or "voice.wav")
    if not voice_path.exists():
        raise RuntimeError("Voiceover missing — generate voice first")

    fmt = project.get("format") or "long"
    size = (1080, 1920) if fmt == "short" else (1920, 1080)
    clips_dir = folder / "clips"
    clips_dir.mkdir(exist_ok=True)

    clip_paths: list[Path] = []
    for i, scene in enumerate(scenes):
        vis = visual_map.get(scene.get("id")) or {}
        image = folder / (vis.get("path") or f"scenes/{scene.get('id')}.jpg")
        if not image.exists():
            raise RuntimeError(f"Missing visual for {scene.get('id')}")
        dest = clips_dir / f"{scene.get('id') or i:02}.mp4"
        motion = vis.get("clip")
        motion_path = folder / motion if motion else None
        if motion_path and motion_path.exists() and motion_path.stat().st_size > 8000:
            await _from_video(motion_path, dest, float(scene.get("duration") or 3), size)
        else:
            await _scene_clip(image, dest, float(scene.get("duration") or 3), size, i, scene.get("text") or "")
        clip_paths.append(dest)

    list_file = clips_dir / "concat.txt"
    list_file.write_text("".join(f"file '{p.resolve().as_posix()}'\n" for p in clip_paths), encoding="utf-8")
    silent = folder / "picture.mp4"
    await _run_ffmpeg(
        [
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(silent),
        ]
    )

    audio_duration = await ffprobe_duration(voice_path)
    picture_duration = await ffprobe_duration(silent)
    duration = max(audio_duration, picture_duration)

    bgm = folder / "bgm.wav"
    await _make_bgm(bgm, duration + 0.4)

    mixed = folder / "mix.m4a"
    await _run_ffmpeg(
        [
            "-y",
            "-i",
            str(voice_path),
            "-i",
            str(bgm),
            "-filter_complex",
            "[0:a]highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11[v];"
            "[1:a]volume=0.55[b];"
            "[v][b]amix=inputs=2:duration=first:dropout_transition=2,alimiter=limit=0.95[a]",
            "-map",
            "[a]",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            str(mixed),
        ]
    )

    final = folder / "final.mp4"
    tmp_final = folder / "final.tmp.mp4"
    await _run_ffmpeg(
        [
            "-y",
            "-i",
            str(silent),
            "-i",
            str(mixed),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(tmp_final),
        ]
    )
    if tmp_final.exists():
        if final.exists():
            final.unlink()
        tmp_final.replace(final)
    final_duration = await ffprobe_duration(final)
    return {
        "path": "final.mp4",
        "duration": round(final_duration, 2),
        "width": size[0],
        "height": size[1],
        "fps": 30,
        "size_bytes": final.stat().st_size,
    }
