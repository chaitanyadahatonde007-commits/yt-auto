from __future__ import annotations

from typing import Any, Callable

from app.paths import project_dir
from app.services.composer import compose_video
from app.services.research import gather_research
from app.services.script_engine import normalize_script, write_script
from app.services.thumbnail import render_thumbnails
from app.services.tts import retimed_scenes, synthesize
from app.services.visuals import render_visuals
from app.services.youtube_pub import upload_video
from app.store import get_project, save_project, update_job

Progress = Callable[[float, str, str], None]


def _progress(job_id: str | None) -> Progress:
    def emit(pct: float, step: str, message: str) -> None:
        if job_id:
            update_job(job_id, status="running", progress=round(pct, 3), step=step, message=message)

    return emit


async def step_research(project: dict[str, Any]) -> dict[str, Any]:
    research = await gather_research(project.get("topic") or "", project.get("notes") or "")
    project["research"] = research
    project["status"] = "researched"
    return save_project(project)


async def step_script(project: dict[str, Any]) -> dict[str, Any]:
    script = await write_script(project, project.get("research"))
    project["script"] = script
    project["title"] = script.get("title") or project.get("title")
    project["gemini_usage"] = {
        **(project.get("gemini_usage") or {}),
        "script": script.get("engine") == "gemini",
        "script_model": script.get("model"),
        "script_error": script.get("llm_error"),
    }
    project["status"] = "scripted"
    return save_project(project)


async def step_voice(project: dict[str, Any]) -> dict[str, Any]:
    script = project.get("script")
    if not script:
        raise RuntimeError("Write a script first")
    voiceover = await synthesize(project, script["full_text"], project.get("voice"))
    script["scenes"] = retimed_scenes(script, voiceover)
    script["estimated_seconds"] = voiceover["duration"]
    project["script"] = script
    project["voiceover"] = voiceover
    project["status"] = "voiced"
    return save_project(project)


async def step_visuals(project: dict[str, Any], emit: Progress | None = None) -> dict[str, Any]:
    script = project.get("script")
    if not script:
        raise RuntimeError("Write a script first")

    def on_prog(done: int, total: int, message: str) -> None:
        if emit:
            frac = 0.52 + 0.12 * (done / max(total, 1))
            emit(frac, "visuals", message)

    project["visuals"] = await render_visuals(project, script["scenes"], progress=on_prog)
    usage = dict(project.get("gemini_usage") or {})
    usage["scene_images"] = (project["visuals"] or {}).get("gemini_images") or 0
    usage["motion_clips"] = (project["visuals"] or {}).get("motion_clips") or 0
    usage["scene_error"] = (project["visuals"] or {}).get("gemini_error")
    project["gemini_usage"] = usage
    project["status"] = "designed"
    return save_project(project)


async def step_thumbnail(project: dict[str, Any]) -> dict[str, Any]:
    project["thumbnail"] = await render_thumbnails(project)
    usage = dict(project.get("gemini_usage") or {})
    usage["thumbnail"] = (project["thumbnail"] or {}).get("source") == "gemini"
    usage["thumbnail_error"] = (project["thumbnail"] or {}).get("gemini_error")
    project["gemini_usage"] = usage
    if project.get("status") in {None, "draft", "researched", "scripted", "voiced", "designed"}:
        project["status"] = project.get("status") or "designed"
    return save_project(project)


async def step_render(project: dict[str, Any], emit: Progress | None = None) -> dict[str, Any]:
    if not project.get("visuals"):
        if emit:
            emit(0.2, "visuals", "Designing frames before the master render")
        project = await step_visuals(project, emit=emit)
    if not project.get("voiceover"):
        if emit:
            emit(0.45, "voice", "Recording voice before the master render")
        project = await step_voice(project)
    if emit:
        emit(0.7, "render", "Assembling picture, captions, and mix")
    project["render"] = await compose_video(project)
    project["status"] = "rendered"
    return save_project(project)


async def step_publish(project: dict[str, Any], privacy: str | None = None, publish_at: str | None = None) -> dict[str, Any]:
    if not project.get("render"):
        raise RuntimeError("Render the video first")
    result = upload_video(project, privacy=privacy, publish_at=publish_at)
    project["youtube"] = result
    project["status"] = "scheduled" if publish_at else "published"
    return save_project(project)


async def run_auto(project_id: str, job_id: str | None = None, publish: bool = False) -> dict[str, Any]:
    emit = _progress(job_id)
    project = get_project(project_id)
    if not project:
        raise RuntimeError("Project not found")
    try:
        emit(0.04, "research", "Pulling a briefing on the topic")
        project = await step_research(project)
        emit(0.16, "script", "Writing narration and a shot list")
        project = await step_script(project)
        emit(0.34, "voice", "Recording the studio voice")
        project = await step_voice(project)
        emit(0.52, "visuals", "Pulling stock motion, then a short AI take if needed")
        project = await step_visuals(project, emit=emit)
        emit(0.66, "thumbnail", "Picking the strongest thumbnail")
        project = await step_thumbnail(project)
        emit(0.74, "render", "Assembling picture, captions, and mix")
        project = await step_render(project)
        if publish:
            emit(0.92, "publish", "Uploading to YouTube")
            project = await step_publish(project)
        emit(1.0, "done", "Cut is ready")
        if job_id:
            update_job(job_id, status="done", progress=1.0, step="done", message="Cut is ready")
        return project
    except Exception as exc:
        if job_id:
            update_job(job_id, status="error", error=str(exc), message=str(exc))
        raise


async def run_step(project_id: str, step: str, job_id: str | None = None, **kwargs: Any) -> dict[str, Any]:
    emit = _progress(job_id)
    project = get_project(project_id)
    if not project:
        raise RuntimeError("Project not found")
    try:
        emit(0.05, step, f"Starting {step}")
        if step == "research":
            project = await step_research(project)
        elif step == "script":
            project = await step_script(project)
        elif step == "voice":
            project = await step_voice(project)
        elif step == "visuals":
            project = await step_visuals(project, emit=emit)
        elif step == "thumbnail":
            project = await step_thumbnail(project)
        elif step == "render":
            project = await step_render(project, emit=emit)
        elif step == "publish":
            project = await step_publish(
                project,
                privacy=kwargs.get("privacy"),
                publish_at=kwargs.get("publish_at"),
            )
        else:
            raise RuntimeError(f"Unknown step {step}")
        emit(1.0, step, f"{step} complete")
        if job_id:
            update_job(job_id, status="done", progress=1.0, step=step, message=f"{step} complete")
        return project
    except Exception as exc:
        if job_id:
            update_job(job_id, status="error", error=str(exc), message=str(exc))
        raise


def apply_script_edit(project: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    current = project.get("script") or {"scenes": []}
    if "full_text" in payload and payload["full_text"] and not payload.get("scenes"):
        from app.services.script_engine import scenes_from_text

        current["scenes"] = scenes_from_text(payload["full_text"])
        current["full_text"] = payload["full_text"]
        current["engine"] = "manual"
    else:
        current.update({k: v for k, v in payload.items() if v is not None})
    project["script"] = normalize_script(current, project)
    if payload.get("title"):
        project["title"] = payload["title"]
    project["status"] = "scripted"
    # voice/visuals out of date
    project["voiceover"] = None
    project["visuals"] = None
    project["render"] = None
    return save_project(project)
