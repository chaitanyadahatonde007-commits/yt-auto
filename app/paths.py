from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "app"
STATIC_DIR = APP_DIR / "static"
ASSETS_DIR = ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
PLATES_DIR = ASSETS_DIR / "plates"
BRAND_DIR = ASSETS_DIR / "brand"
VENDOR_DIR = ROOT / "vendor"
ESPEAK_DIR = VENDOR_DIR / "espeak-ng"
DATA_DIR = Path(os.environ.get("YT_AUTO_DATA", ROOT / "data"))
PROJECTS_DIR = DATA_DIR / "projects"
SETTINGS_PATH = DATA_DIR / "settings.json"
DB_PATH = DATA_DIR / "studio.db"
YOUTUBE_TOKEN_PATH = DATA_DIR / "youtube_token.json"


def ensure_dirs() -> None:
    for path in (DATA_DIR, PROJECTS_DIR, ASSETS_DIR, FONTS_DIR, PLATES_DIR):
        path.mkdir(parents=True, exist_ok=True)


def ffmpeg_exe() -> str:
    env = os.environ.get("FFMPEG_PATH")
    if env and Path(env).exists():
        return env
    local = ROOT / "bin" / "ffmpeg"
    if local.exists():
        return str(local)
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("ffmpeg not found. Install ffmpeg or imageio-ffmpeg.") from exc


def font(name: str) -> Path:
    candidate = FONTS_DIR / name
    if candidate.exists():
        return candidate
    fallbacks = [
        FONTS_DIR / "Inter-Bold.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for item in fallbacks:
        if item.exists():
            return item
    raise FileNotFoundError(f"Font not found: {name}")


def project_dir(project_id: str) -> Path:
    path = PROJECTS_DIR / project_id
    path.mkdir(parents=True, exist_ok=True)
    return path
