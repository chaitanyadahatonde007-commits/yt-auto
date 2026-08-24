from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

# This OAuth client was already used with extra YouTube scopes.
# Google then returns those extras and oauthlib throws "Scope has changed".
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"

from app.config import load_settings
from app.paths import YOUTUBE_TOKEN_PATH, project_dir

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube",
]


def _client_config() -> dict[str, Any]:
    settings = load_settings()
    if not settings.get("google_client_id") or not settings.get("google_client_secret"):
        raise RuntimeError(
            "Add a Google OAuth client ID and secret in Settings. "
            "Create a Desktop or Web client in Google Cloud with YouTube Data API v3 enabled."
        )
    return {
        "web": {
            "client_id": settings["google_client_id"],
            "client_secret": settings["google_client_secret"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost:8000/api/youtube/callback"],
        }
    }


def _redirect_uri(public_base: str | None = None) -> str:
    settings = load_settings()
    base = (public_base or settings.get("public_base_url") or "http://localhost:8000").rstrip("/")
    return f"{base}/api/youtube/callback"


def auth_url(public_base: str | None = None) -> str:
    settings = load_settings()
    if not settings.get("google_client_id"):
        raise RuntimeError("Google client ID missing")
    params = {
        "client_id": settings["google_client_id"],
        "redirect_uri": _redirect_uri(public_base),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)


def load_credentials():
    if not YOUTUBE_TOKEN_PATH.exists():
        return None
    from google.oauth2.credentials import Credentials

    data = json.loads(YOUTUBE_TOKEN_PATH.read_text(encoding="utf-8"))
    creds = Credentials.from_authorized_user_info(data, SCOPES)
    return creds


def save_credentials(creds) -> None:
    YOUTUBE_TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")


def connected() -> dict[str, Any]:
    creds = load_credentials()
    if not creds:
        return {"connected": False}
    try:
        from googleapiclient.discovery import build

        if creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request

            creds.refresh(Request())
            save_credentials(creds)
        youtube = build("youtube", "v3", credentials=creds)
        res = youtube.channels().list(part="snippet,statistics", mine=True).execute()
        items = res.get("items") or []
        if not items:
            return {"connected": True, "channel": None}
        ch = items[0]
        snippet = ch.get("snippet") or {}
        stats = ch.get("statistics") or {}
        thumbs = snippet.get("thumbnails") or {}
        return {
            "connected": True,
            "channel": {
                "id": ch.get("id"),
                "title": snippet.get("title"),
                "thumbnail": (thumbs.get("default") or thumbs.get("medium") or {}).get("url"),
                "subscribers": stats.get("subscriberCount"),
                "videos": stats.get("videoCount"),
            },
        }
    except Exception as exc:
        return {"connected": False, "error": str(exc)}


def exchange_code(code: str, public_base: str | None = None) -> dict[str, Any]:
    from google_auth_oauthlib.flow import Flow

    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=_redirect_uri(public_base))
    flow.fetch_token(code=code)
    save_credentials(flow.credentials)
    return connected()


def disconnect() -> None:
    if YOUTUBE_TOKEN_PATH.exists():
        YOUTUBE_TOKEN_PATH.unlink()


def upload_video(project: dict[str, Any], privacy: str | None = None) -> dict[str, Any]:
    creds = load_credentials()
    if not creds:
        raise RuntimeError("YouTube is not connected. Open Channel and finish Google sign-in.")
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        save_credentials(creds)

    folder = project_dir(project["id"])
    render = project.get("render") or {}
    video_path = folder / (render.get("path") or "final.mp4")
    if not video_path.exists():
        raise RuntimeError("Render the video before publishing.")

    script = project.get("script") or {}
    settings = load_settings()
    privacy = privacy or (project.get("youtube") or {}).get("privacy") or settings.get("default_privacy") or "private"
    if privacy not in {"private", "unlisted", "public"}:
        privacy = "private"

    youtube = build("youtube", "v3", credentials=creds)
    body = {
        "snippet": {
            "title": (script.get("title") or project.get("title") or "ChannelForge video")[:100],
            "description": script.get("description") or project.get("topic") or "",
            "tags": (script.get("tags") or [])[:15],
            "categoryId": settings.get("youtube_category_id") or "27",
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": bool(settings.get("made_for_kids")),
        },
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()
    video_id = response["id"]

    thumb = project.get("thumbnail") or {}
    selected = thumb.get("selected")
    if selected and (folder / selected).exists():
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(folder / selected), mimetype="image/jpeg"),
            ).execute()
        except Exception:
            pass

    url = f"https://www.youtube.com/watch?v={video_id}"
    return {
        "video_id": video_id,
        "url": url,
        "privacy": privacy,
        "title": body["snippet"]["title"],
    }
