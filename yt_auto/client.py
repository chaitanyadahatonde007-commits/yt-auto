"""Thin wrapper around YouTube Data API v3 (API key + optional OAuth)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from googleapiclient.discovery import build

load_dotenv()

SCOPES_UPLOAD = ["https://www.googleapis.com/auth/youtube.upload"]
SCOPES_FULL = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def get_api_key() -> str:
    key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "Missing YOUTUBE_API_KEY.\n"
            "1. Open https://console.cloud.google.com/\n"
            "2. Create a project → APIs & Services → Library → enable YouTube Data API v3\n"
            "3. Credentials → Create credentials → API key\n"
            "4. Copy .env.example to .env and paste the key."
        )
    return key


def youtube_service(*, oauth: bool = False, scopes: list[str] | None = None):
    if oauth:
        return _oauth_service(scopes or SCOPES_FULL)
    return build("youtube", "v3", developerKey=get_api_key())


def _oauth_service(scopes: list[str]):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    secrets = os.getenv("GOOGLE_OAUTH_CLIENT_SECRETS", "").strip()
    if not secrets or not Path(secrets).is_file():
        raise SystemExit(
            "OAuth needs a Desktop client JSON from Google Cloud Console.\n"
            "Set GOOGLE_OAUTH_CLIENT_SECRETS=/path/to/client_secret.json"
        )
    token_path = Path(".oauth-token.json")
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(secrets, scopes)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds)


def search_videos(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    yt = youtube_service()
    res = (
        yt.search()
        .list(part="snippet", q=query, type="video", maxResults=max_results)
        .execute()
    )
    out = []
    for item in res.get("items", []):
        vid = item["id"]["videoId"]
        sn = item["snippet"]
        out.append(
            {
                "id": vid,
                "title": sn.get("title"),
                "channel": sn.get("channelTitle"),
                "published": sn.get("publishedAt"),
                "url": f"https://www.youtube.com/watch?v={vid}",
            }
        )
    return out


def video_details(video_ids: list[str]) -> list[dict[str, Any]]:
    yt = youtube_service()
    res = (
        yt.videos()
        .list(part="snippet,statistics,contentDetails", id=",".join(video_ids))
        .execute()
    )
    out = []
    for item in res.get("items", []):
        sn, st, cd = item["snippet"], item.get("statistics", {}), item.get("contentDetails", {})
        out.append(
            {
                "id": item["id"],
                "title": sn.get("title"),
                "channel": sn.get("channelTitle"),
                "duration": cd.get("duration"),
                "views": st.get("viewCount"),
                "likes": st.get("likeCount"),
                "comments": st.get("commentCount"),
                "url": f"https://www.youtube.com/watch?v={item['id']}",
            }
        )
    return out


def channel_details(channel_id: str | None = None, for_username: str | None = None) -> dict[str, Any]:
    yt = youtube_service()
    kwargs: dict[str, Any] = {"part": "snippet,statistics,contentDetails"}
    if channel_id:
        kwargs["id"] = channel_id
    elif for_username:
        kwargs["forHandle"] = for_username.lstrip("@")
    else:
        raise ValueError("Need channel_id or for_username")
    res = yt.channels().list(**kwargs).execute()
    items = res.get("items") or []
    if not items:
        return {}
    item = items[0]
    sn, st = item["snippet"], item.get("statistics", {})
    return {
        "id": item["id"],
        "title": sn.get("title"),
        "handle": sn.get("customUrl"),
        "subs": st.get("subscriberCount"),
        "videos": st.get("videoCount"),
        "views": st.get("viewCount"),
        "url": f"https://www.youtube.com/channel/{item['id']}",
    }
