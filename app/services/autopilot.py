from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

# Fixed IST. Do not use ZoneInfo — Windows Python has no tzdata by default.
IST = timezone(timedelta(hours=5, minutes=30))

from app.config import load_settings
from app.services.pipeline import run_auto
from app.services.trends import pick_topic
from app.services.youtube_pub import connected, upload_video
from app.store import (
    add_autopilot_run,
    autopilot_busy,
    autopilot_count_today,
    create_job,
    create_project,
    last_successful_autopilot,
    list_autopilot_runs,
    update_autopilot_run,
)

# Peak India entertainment windows (IST).
SLOTS = ((9, 0), (13, 0), (18, 30), (21, 0))
_LOCK = asyncio.Lock()


def _slot_key(when: datetime) -> str:
    local = when.astimezone(IST)
    return local.strftime("%Y-%m-%d %H:%M")


def used_slot_keys() -> set[str]:
    used: set[str] = set()
    try:
        for run in list_autopilot_runs(40):
            stamp = run.get("scheduled_for")
            if not stamp or run.get("status") not in {"scheduled", "published", "ready", "running"}:
                continue
            try:
                when = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=timezone.utc)
                used.add(_slot_key(when))
            except Exception:
                continue
    except Exception:
        return used
    return used


def next_slot(after: datetime | None = None) -> datetime:
    now = after or datetime.now(IST)
    taken = used_slot_keys()
    for day in range(0, 5):
        base = (now + timedelta(days=day)).replace(second=0, microsecond=0)
        for hour, minute in SLOTS:
            candidate = base.replace(hour=hour, minute=minute)
            if candidate <= now + timedelta(minutes=20):
                continue
            if _slot_key(candidate) in taken:
                continue
            return candidate
    return now + timedelta(hours=3)


def status_payload() -> dict[str, Any]:
    settings = load_settings()
    youtube_ok = False
    try:
        youtube_ok = bool(connected().get("connected"))
    except Exception:
        youtube_ok = False
    try:
        last = last_successful_autopilot()
        runs = list_autopilot_runs(20)
        today = autopilot_count_today()
        busy = autopilot_busy()
    except Exception:
        last, runs, today, busy = None, [], 0, False
    try:
        nxt = next_slot().isoformat()
    except Exception:
        nxt = ""
    return {
        "enabled": bool(settings.get("autopilot_enabled")),
        "interval_hours": int(settings.get("autopilot_interval_hours") or 6),
        "daily_cap": int(settings.get("autopilot_daily_cap") or 4),
        "format": settings.get("autopilot_format") or "short",
        "style": settings.get("autopilot_style") or "entertainment",
        "language": settings.get("content_language") or "hinglish",
        "region": settings.get("autopilot_region") or "IN",
        "publish": settings.get("autopilot_publish") or "schedule",
        "slots": ["9:00", "13:00", "18:30", "21:00"],
        "today": today,
        "busy": busy,
        "youtube": youtube_ok,
        "last": last,
        "next_slot": nxt,
        "runs": runs,
        "note": "4 funny Hinglish shorts a day. Leave py -3 run.py open. Videos auto-schedule at 9:00, 13:00, 18:30, 21:00 IST.",
    }


def _due(settings: dict[str, Any]) -> bool:
    if not settings.get("autopilot_enabled"):
        return False
    if autopilot_busy():
        return False
    if autopilot_count_today() >= int(settings.get("autopilot_daily_cap") or 4):
        return False
    last = last_successful_autopilot()
    if not last:
        return True
    # Catch up to 4/day. 75 minutes between cuts so WaveSpeed can breathe.
    try:
        created = datetime.fromisoformat(last["created_at"].replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
    except Exception:
        return True
    wait = max(75, int(float(settings.get("autopilot_interval_hours") or 2) * 30))
    return datetime.now(timezone.utc) - created >= timedelta(minutes=wait)


async def run_cycle(force: bool = False) -> dict[str, Any]:
    settings = load_settings()
    if not force and not _due(settings):
        return {"skipped": True, "reason": "not due"}
    async with _LOCK:
        return await _run_locked(settings)


async def _run_locked(settings: dict[str, Any]) -> dict[str, Any]:
    run = add_autopilot_run({"status": "running", "topic": "discovering…", "message": "Reading what is famous right now"})
    try:
        picked = await pick_topic(settings.get("autopilot_region") or "IN")
        update_autopilot_run(run["id"], topic=picked["topic"], source=picked.get("source"), message="Generating the cut")
        fmt = settings.get("autopilot_format") or "short"
        project = create_project(
            {
                "topic": picked["topic"],
                "notes": picked.get("notes") or "",
                "format": fmt,
                "style": settings.get("autopilot_style") or "explainer",
                "target_seconds": 40 if fmt == "short" else 150,
                "voice": settings.get("default_voice") or "local:en-us",
                "visual_mood": settings.get("default_mood") or "ember",
            }
        )
        update_autopilot_run(run["id"], project_id=project["id"])
        job = create_job("autopilot", project["id"])
        publish_mode = settings.get("autopilot_publish") or "schedule"
        project = await run_auto(project["id"], job["id"], publish=False)

        scheduled_for = None
        yt_result = None
        if publish_mode in {"private", "unlisted", "public", "schedule"} and connected().get("connected"):
            if publish_mode == "schedule":
                when = next_slot()
                scheduled_for = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                yt_result = upload_video(project, privacy="private", publish_at=scheduled_for)
                status = "scheduled"
                message = f"Queued on YouTube for {when.strftime('%d %b %I:%M %p')} IST"
            else:
                yt_result = upload_video(project, privacy=publish_mode)
                status = "published"
                message = f"Uploaded as {publish_mode}"
            project["youtube"] = yt_result
            from app.store import save_project

            save_project(project)
        else:
            status = "ready"
            message = "Video ready. Connect YouTube to auto-upload, or publish from the studio."

        update_autopilot_run(
            run["id"],
            status=status,
            scheduled_for=scheduled_for,
            message=message,
            project_id=project["id"],
            topic=picked["topic"],
            source=picked.get("source"),
        )
        return {"run": get_fresh(run["id"]), "project_id": project["id"], "topic": picked["topic"]}
    except Exception as exc:
        update_autopilot_run(run["id"], status="error", error=str(exc), message=str(exc))
        raise


def get_fresh(run_id: str) -> dict[str, Any] | None:
    from app.store import get_autopilot_run

    return get_autopilot_run(run_id)


async def scheduler_loop() -> None:
    await asyncio.sleep(8)
    while True:
        try:
            settings = load_settings()
            if settings.get("autopilot_enabled") and _due(settings):
                await run_cycle(force=False)
        except Exception:
            pass
        await asyncio.sleep(60)
