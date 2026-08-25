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
    last_autopilot_run,
    last_successful_autopilot,
    latest_job,
    list_autopilot_runs,
    recover_stale_autopilot,
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
        youtube_ok = bool(connected(quick=True).get("connected"))
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
    job = None
    try:
        pid = (runs[0].get("project_id") if runs else None) or (last or {}).get("project_id")
        if pid:
            job = latest_job(pid)
    except Exception:
        job = None
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
        "job": job,
        "why_idle": _why_idle(settings, today, busy),
        "note": "4 funny Hinglish shorts a day. Leave py -3 run.py open. Videos auto-schedule at 9:00, 13:00, 18:30, 21:00 IST.",
    }


def _why_idle(settings: dict[str, Any], today: int, busy: bool) -> str:
    if not settings.get("autopilot_enabled"):
        return "Autopilot is off. Click Start autopilot."
    if busy:
        return "A cut is already running."
    cap = int(settings.get("autopilot_daily_cap") or 4)
    if today >= cap:
        return f"Daily cap reached ({today}/{cap})."
    last_any = last_autopilot_run()
    if last_any and last_any.get("status") == "error":
        try:
            created = datetime.fromisoformat(str(last_any["created_at"]).replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            left = 3 * 60 - (datetime.now(timezone.utc) - created).total_seconds()
            if left > 0:
                return f"Last cut failed. Retry in {int(left // 60) + 1} min. {last_any.get('error') or ''}".strip()
        except Exception:
            pass
    last = last_successful_autopilot()
    if last:
        try:
            created = datetime.fromisoformat(last["created_at"].replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            left = 20 * 60 - (datetime.now(timezone.utc) - created).total_seconds()
            if left > 0:
                return f"Next cut in {int(left // 60) + 1} min."
        except Exception:
            pass
    return "Ready. Next cut starts now."


def _due(settings: dict[str, Any]) -> bool:
    if not settings.get("autopilot_enabled"):
        return False
    if autopilot_busy():
        return False
    if autopilot_count_today() >= int(settings.get("autopilot_daily_cap") or 4):
        return False
    last_any = last_autopilot_run()
    if last_any and last_any.get("status") == "error":
        try:
            created = datetime.fromisoformat(str(last_any["created_at"]).replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - created < timedelta(minutes=3):
                return False
        except Exception:
            pass
    last = last_successful_autopilot()
    if not last:
        return True
    try:
        created = datetime.fromisoformat(last["created_at"].replace("Z", "+00:00"))
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
    except Exception:
        return True
    return datetime.now(timezone.utc) - created >= timedelta(minutes=20)


async def run_cycle(force: bool = False) -> dict[str, Any]:
    settings = load_settings()
    if force:
        recover_stale_autopilot(max_age_sec=30)
    if not force and not _due(settings):
        return {"skipped": True, "reason": _why_idle(settings, autopilot_count_today(), autopilot_busy())}
    if _LOCK.locked():
        return {"skipped": True, "reason": "already running"}
    async with _LOCK:
        return await _run_locked(settings)


async def _run_locked(settings: dict[str, Any]) -> dict[str, Any]:
    run = add_autopilot_run({"status": "running", "topic": "discovering…", "message": "Reading what is famous right now"})
    try:
        from app.services.trends import pick_topic_now

        picked = pick_topic_now()
        print("Autopilot topic:", picked["topic"])
        update_autopilot_run(run["id"], topic=picked["topic"], source=picked.get("source"), message="Generating the cut")
        fmt = settings.get("autopilot_format") or "short"
        lang = settings.get("content_language") or "hinglish"
        project = create_project(
            {
                "topic": picked["topic"],
                "notes": (picked.get("notes") or "")
                + " Funny Hinglish. Golu and Pihu act every line.",
                "format": fmt,
                "style": settings.get("autopilot_style") or "entertainment",
                "language": lang,
                "target_seconds": 38 if fmt == "short" else 120,
                "voice": settings.get("default_voice") or "edge:hi-IN-MadhurNeural",
                "visual_mood": settings.get("default_mood") or "magenta",
            }
        )
        update_autopilot_run(run["id"], project_id=project["id"])
        job = create_job("autopilot", project["id"])
        publish_mode = settings.get("autopilot_publish") or "schedule"
        project = await run_auto(project["id"], job["id"], publish=False)

        scheduled_for = None
        yt_result = None
        yt_ok = False
        try:
            yt_ok = bool((await asyncio.wait_for(asyncio.to_thread(connected), timeout=20)).get("connected"))
        except Exception as exc:
            print("Autopilot YouTube status:", exc)
            yt_ok = False
        if publish_mode in {"private", "unlisted", "public", "schedule"} and yt_ok:
            try:
                if publish_mode == "schedule":
                    when = next_slot()
                    scheduled_for = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    yt_result = await asyncio.to_thread(
                        upload_video, project, "private", scheduled_for
                    )
                    status = "scheduled"
                    message = f"Queued on YouTube for {when.strftime('%d %b %I:%M %p')} IST"
                else:
                    yt_result = await asyncio.to_thread(upload_video, project, publish_mode, None)
                    status = "published"
                    message = f"Uploaded as {publish_mode}"
                project["youtube"] = yt_result
                from app.store import save_project

                save_project(project)
            except Exception as exc:
                print("Autopilot YouTube upload failed:", exc)
                status = "ready"
                message = f"Video ready. YouTube upload failed: {exc}"
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
    print("Autopilot scheduler live")
    warned_off = False
    await asyncio.sleep(2)
    while True:
        try:
            if not _LOCK.locked():
                recover_stale_autopilot(max_age_sec=1800)
            settings = load_settings()
            if settings.get("autopilot_enabled") and _due(settings) and not _LOCK.locked():
                print("Autopilot launching a cut")
                asyncio.create_task(_safe_cycle())
                warned_off = False
            elif not settings.get("autopilot_enabled") and not warned_off:
                print("Autopilot is off. Click Start autopilot.")
                warned_off = True
        except Exception as exc:
            print("Autopilot tick:", exc)
        await asyncio.sleep(20)


async def _safe_cycle() -> None:
    try:
        result = await run_cycle(force=False)
        print("Autopilot cycle:", result.get("topic") or result)
    except Exception as exc:
        print("Autopilot cycle failed:", exc)
