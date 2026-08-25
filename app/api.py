from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse

from app.config import load_settings, public_settings, save_settings
from app.paths import project_dir
from app.services import youtube_pub
from app.services.pipeline import apply_script_edit, run_auto, run_step
from app.services.tts import list_voices
from app.store import (
    create_job,
    create_project,
    delete_project,
    get_job,
    get_project,
    latest_job,
    list_projects,
    media_url,
    project_job_busy,
    save_project,
)

router = APIRouter()


def _present(project: dict[str, Any]) -> dict[str, Any]:
    pid = project["id"]
    out = dict(project)
    vo = out.get("voiceover")
    if vo and vo.get("path"):
        vo = dict(vo)
        vo["url"] = media_url(pid, vo["path"])
        out["voiceover"] = vo
    vis = out.get("visuals")
    if vis and vis.get("scenes"):
        vis = dict(vis)
        vis["scenes"] = [
            {**s, "url": media_url(pid, s.get("path"))} for s in vis["scenes"]
        ]
        out["visuals"] = vis
    thumb = out.get("thumbnail")
    if thumb and thumb.get("variants"):
        thumb = dict(thumb)
        thumb["urls"] = [media_url(pid, name) for name in thumb["variants"]]
        if thumb.get("selected"):
            thumb["selected_url"] = media_url(pid, thumb["selected"])
        out["thumbnail"] = thumb
    render = out.get("render")
    if render and render.get("path"):
        render = dict(render)
        render["url"] = media_url(pid, render["path"])
        out["render"] = render
    return out


def _require(project_id: str) -> dict[str, Any]:
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


def _ensure_idle(project_id: str) -> None:
    if project_job_busy(project_id):
        raise HTTPException(409, "This cut is already running. Wait for the current job to finish.")


def _launch(background: BackgroundTasks, coro) -> None:
    async def _runner() -> None:
        try:
            await coro
        except Exception as exc:
            print("background job failed:", exc)

    background.add_task(_runner)


@router.get("/api/health")
async def health() -> dict[str, Any]:
    from app.paths import ESPEAK_DIR, ffmpeg_exe

    return {
        "ok": True,
        "name": "ChannelForge",
        "ffmpeg": bool(ffmpeg_exe()),
        "local_voice": (ESPEAK_DIR / "espeak-ng.wasm").exists(),
        "llm": public_settings()["has_openai"]
        or public_settings()["has_anthropic"]
        or public_settings()["has_gemini"],
        "gemini": public_settings()["has_gemini"],
        "gemini_does": public_settings().get("gemini_does") or [],
    }


@router.get("/api/voices")
async def voices() -> dict[str, Any]:
    return {"voices": list_voices()}


@router.get("/api/settings")
async def get_settings() -> dict[str, Any]:
    return public_settings()


@router.put("/api/settings")
async def put_settings(payload: dict[str, Any]) -> dict[str, Any]:
    save_settings(payload)
    return public_settings()


@router.get("/api/projects")
async def projects() -> dict[str, Any]:
    items = [_present(p) for p in list_projects()]
    return {"projects": items}


@router.post("/api/projects")
async def new_project(payload: dict[str, Any], background: BackgroundTasks) -> dict[str, Any]:
    if not (payload.get("topic") or "").strip():
        raise HTTPException(400, "Topic is required")
    project = create_project(payload)
    job = None
    if payload.get("auto"):
        job = create_job("auto", project["id"])
        _launch(background, run_auto(project["id"], job["id"], publish=bool(payload.get("publish"))))
    return {"project": _present(project), "job": job}


@router.get("/api/projects/{project_id}")
async def read_project(project_id: str) -> dict[str, Any]:
    project = _require(project_id)
    return {"project": _present(project), "job": latest_job(project_id)}


@router.patch("/api/projects/{project_id}")
async def patch_project(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    project = _require(project_id)
    allowed = {
        "title",
        "topic",
        "notes",
        "format",
        "style",
        "target_seconds",
        "voice",
        "visual_mood",
        "language",
        "status",
    }
    for key in allowed:
        if key in payload and payload[key] is not None:
            project[key] = payload[key]
    if "thumbnail" in payload and isinstance(payload["thumbnail"], dict):
        current = project.get("thumbnail") or {}
        current.update(payload["thumbnail"])
        project["thumbnail"] = current
    return {"project": _present(save_project(project))}


@router.delete("/api/projects/{project_id}")
async def drop_project(project_id: str) -> dict[str, Any]:
    if not delete_project(project_id):
        raise HTTPException(404, "Project not found")
    return {"ok": True}


@router.put("/api/projects/{project_id}/script")
async def edit_script(project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    project = _require(project_id)
    return {"project": _present(apply_script_edit(project, payload))}


@router.post("/api/projects/{project_id}/auto")
async def auto_project(project_id: str, background: BackgroundTasks, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    _require(project_id)
    _ensure_idle(project_id)
    job = create_job("auto", project_id)
    publish = bool((payload or {}).get("publish"))
    _launch(background, run_auto(project_id, job["id"], publish=publish))
    return {"job": job}


@router.post("/api/projects/{project_id}/{step}")
async def run_project_step(
    project_id: str,
    step: str,
    background: BackgroundTasks,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if step not in {"research", "script", "voice", "visuals", "thumbnail", "render", "publish"}:
        raise HTTPException(404, "Unknown step")
    _require(project_id)
    _ensure_idle(project_id)
    job = create_job(step, project_id)
    _launch(background, run_step(project_id, step, job["id"], **(payload or {})))
    return {"job": job}


@router.get("/api/jobs/{job_id}")
async def read_job(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    project = get_project(job["project_id"]) if job.get("project_id") else None
    return {"job": job, "project": _present(project) if project else None}


@router.get("/api/youtube/status")
async def youtube_status() -> dict[str, Any]:
    return youtube_pub.connected()


@router.get("/api/youtube/auth-url")
async def youtube_auth_url(request: Request) -> dict[str, Any]:
    settings = load_settings()
    base = settings.get("public_base_url") or str(request.base_url).rstrip("/")
    try:
        return {"url": youtube_pub.auth_url(base)}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/api/youtube/callback")
async def youtube_callback(request: Request, code: str | None = None, error: str | None = None) -> HTMLResponse:
    if error:
        return HTMLResponse(f"<h1>YouTube auth failed</h1><p>{error}</p>", status_code=400)
    if not code:
        return HTMLResponse("<h1>Missing code</h1>", status_code=400)
    settings = load_settings()
    base = settings.get("public_base_url") or str(request.base_url).rstrip("/")
    try:
        youtube_pub.exchange_code(code, base)
    except Exception as exc:
        return HTMLResponse(f"<h1>Could not finish sign-in</h1><p>{exc}</p>", status_code=400)
    return HTMLResponse(
        "<html><body style='background:#08080c;color:#f4f1ec;font-family:sans-serif;padding:48px'>"
        "<h1>Channel connected.</h1><p>You can close this tab and return to ChannelForge.</p>"
        "<script>setTimeout(()=>window.close(), 800)</script></body></html>"
    )


@router.post("/api/youtube/disconnect")
async def youtube_disconnect() -> dict[str, Any]:
    youtube_pub.disconnect()
    return {"ok": True}


@router.get("/api/trends")
async def trends() -> dict[str, Any]:
    try:
        from app.services.trends import local_topics

        return {"trends": local_topics()}
    except Exception as exc:
        return {"trends": [], "error": str(exc)}


@router.get("/api/autopilot")
async def autopilot_status() -> dict[str, Any]:
    from app.store import init_db

    init_db()
    from app.services.autopilot import status_payload

    return status_payload()


@router.put("/api/autopilot")
async def autopilot_update(payload: dict[str, Any], background: BackgroundTasks) -> dict[str, Any]:
    from app.services.autopilot import run_cycle, status_payload
    from app.store import recover_stale_autopilot

    allowed = {
        "autopilot_enabled",
        "autopilot_interval_hours",
        "autopilot_daily_cap",
        "autopilot_format",
        "autopilot_style",
        "autopilot_region",
        "autopilot_publish",
        "content_language",
    }
    turning_on = bool(payload.get("autopilot_enabled"))
    save_settings({k: payload[k] for k in allowed if k in payload})
    if turning_on:
        recover_stale_autopilot(max_age_sec=30)
        _launch(background, run_cycle(force=True))
    return status_payload()


@router.post("/api/autopilot/run-now")
async def autopilot_run_now(background: BackgroundTasks) -> dict[str, Any]:
    from app.services.autopilot import run_cycle, status_payload
    from app.store import recover_stale_autopilot

    recover_stale_autopilot(max_age_sec=30)
    _launch(background, run_cycle(force=True))
    return {"ok": True, "autopilot": status_payload()}


@router.get("/media/{project_id}/{rest:path}")
async def media(project_id: str, rest: str) -> FileResponse:
    folder = project_dir(project_id).resolve()
    target = (folder / rest).resolve()
    if folder not in target.parents and target != folder:
        raise HTTPException(400, "Invalid path")
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(target)
