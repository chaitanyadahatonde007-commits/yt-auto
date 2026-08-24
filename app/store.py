from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.paths import DB_PATH, PROJECTS_DIR, ensure_dirs, project_dir

_LOCK = threading.Lock()


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str = "cf") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    ensure_dirs()
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                topic TEXT NOT NULL,
                format TEXT NOT NULL,
                style TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                data_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                kind TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0,
                step TEXT,
                message TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS autopilot (
                id TEXT PRIMARY KEY,
                topic TEXT NOT NULL,
                source TEXT,
                status TEXT NOT NULL,
                project_id TEXT,
                scheduled_for TEXT,
                message TEXT,
                error TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _row_to_project(row: sqlite3.Row) -> dict[str, Any]:
    data = json.loads(row["data_json"])
    data.update(
        {
            "id": row["id"],
            "title": row["title"],
            "topic": row["topic"],
            "format": row["format"],
            "style": row["style"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    )
    return data


def blank_project(payload: dict[str, Any]) -> dict[str, Any]:
    now = utcnow()
    topic = (payload.get("topic") or "Untitled idea").strip()
    fmt = payload.get("format") or "long"
    style = payload.get("style") or "entertainment"
    target = int(payload.get("target_seconds") or (45 if fmt == "short" else 180))
    return {
        "id": new_id("cf"),
        "title": payload.get("title") or topic.title(),
        "topic": topic,
        "notes": payload.get("notes") or "",
        "format": fmt,
        "style": style or "entertainment",
        "target_seconds": target,
        "voice": payload.get("voice") or "local:en-us",
        "visual_mood": payload.get("visual_mood") or "magenta",
        "status": "draft",
        "created_at": now,
        "updated_at": now,
        "research": None,
        "script": None,
        "voiceover": None,
        "visuals": None,
        "thumbnail": None,
        "render": None,
        "youtube": None,
    }


def create_project(payload: dict[str, Any]) -> dict[str, Any]:
    project = blank_project(payload)
    project_dir(project["id"])
    with _LOCK, connect() as conn:
        conn.execute(
            """
            INSERT INTO projects (id, title, topic, format, style, status, created_at, updated_at, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project["id"],
                project["title"],
                project["topic"],
                project["format"],
                project["style"],
                project["status"],
                project["created_at"],
                project["updated_at"],
                json.dumps(project),
            ),
        )
        conn.commit()
    return project


def list_projects() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC"
        ).fetchall()
    return [_row_to_project(r) for r in rows]


def get_project(project_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    return _row_to_project(row) if row else None


def save_project(project: dict[str, Any]) -> dict[str, Any]:
    project["updated_at"] = utcnow()
    with _LOCK, connect() as conn:
        conn.execute(
            """
            UPDATE projects
            SET title = ?, topic = ?, format = ?, style = ?, status = ?, updated_at = ?, data_json = ?
            WHERE id = ?
            """,
            (
                project.get("title") or project.get("topic") or "Untitled",
                project.get("topic") or "",
                project.get("format") or "long",
                project.get("style") or "entertainment",
                project.get("status") or "draft",
                project["updated_at"],
                json.dumps(project),
                project["id"],
            ),
        )
        conn.commit()
    path = project_dir(project["id"]) / "project.json"
    path.write_text(json.dumps(project, indent=2), encoding="utf-8")
    return project


def delete_project(project_id: str) -> bool:
    existing = get_project(project_id)
    if not existing:
        return False
    with _LOCK, connect() as conn:
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.execute("DELETE FROM jobs WHERE project_id = ?", (project_id,))
        conn.commit()
    folder = PROJECTS_DIR / project_id
    if folder.exists():
        import shutil

        shutil.rmtree(folder, ignore_errors=True)
    return True


def create_job(kind: str, project_id: str | None = None) -> dict[str, Any]:
    now = utcnow()
    job = {
        "id": new_id("job"),
        "project_id": project_id,
        "kind": kind,
        "status": "queued",
        "progress": 0.0,
        "step": None,
        "message": "Queued",
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    with _LOCK, connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, project_id, kind, status, progress, step, message, error, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job["id"],
                job["project_id"],
                job["kind"],
                job["status"],
                job["progress"],
                job["step"],
                job["message"],
                job["error"],
                job["created_at"],
                job["updated_at"],
            ),
        )
        conn.commit()
    return job


def update_job(job_id: str, **fields: Any) -> dict[str, Any] | None:
    job = get_job(job_id)
    if not job:
        return None
    job.update(fields)
    job["updated_at"] = utcnow()
    with _LOCK, connect() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = ?, progress = ?, step = ?, message = ?, error = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                job["status"],
                float(job["progress"] or 0),
                job.get("step"),
                job.get("message"),
                job.get("error"),
                job["updated_at"],
                job_id,
            ),
        )
        conn.commit()
    return job


def get_job(job_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        return None
    return dict(row)


def project_job_busy(project_id: str) -> bool:
    job = latest_job(project_id)
    if not job or job.get("status") not in {"queued", "running"}:
        return False
    try:
        updated = datetime.fromisoformat(str(job.get("updated_at") or "").replace("Z", "+00:00"))
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - updated).total_seconds()
    except Exception:
        age = 0
    if age > 2400:
        update_job(job["id"], status="error", error="Timed out", message="Job took too long and was stopped")
        return False
    return True


def latest_job(project_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM jobs WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()
    return dict(row) if row else None


def media_url(project_id: str, rel: str | Path | None) -> str | None:
    if not rel:
        return None
    return f"/media/{project_id}/{Path(rel).as_posix().lstrip('/')}"


def add_autopilot_run(payload: dict[str, Any]) -> dict[str, Any]:
    row = {
        "id": new_id("ap"),
        "topic": payload.get("topic") or "",
        "source": payload.get("source") or "",
        "status": payload.get("status") or "queued",
        "project_id": payload.get("project_id"),
        "scheduled_for": payload.get("scheduled_for"),
        "message": payload.get("message") or "",
        "error": payload.get("error"),
        "created_at": utcnow(),
    }
    with _LOCK, connect() as conn:
        conn.execute(
            """
            INSERT INTO autopilot (id, topic, source, status, project_id, scheduled_for, message, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["id"],
                row["topic"],
                row["source"],
                row["status"],
                row["project_id"],
                row["scheduled_for"],
                row["message"],
                row["error"],
                row["created_at"],
            ),
        )
        conn.commit()
    return row


def update_autopilot_run(run_id: str, **fields: Any) -> dict[str, Any] | None:
    run = get_autopilot_run(run_id)
    if not run:
        return None
    run.update(fields)
    with _LOCK, connect() as conn:
        conn.execute(
            """
            UPDATE autopilot
            SET topic = ?, source = ?, status = ?, project_id = ?, scheduled_for = ?, message = ?, error = ?
            WHERE id = ?
            """,
            (
                run.get("topic"),
                run.get("source"),
                run.get("status"),
                run.get("project_id"),
                run.get("scheduled_for"),
                run.get("message"),
                run.get("error"),
                run_id,
            ),
        )
        conn.commit()
    return run


def get_autopilot_run(run_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM autopilot WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def list_autopilot_runs(limit: int = 30) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM autopilot ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def autopilot_used_topics() -> set[str]:
    with connect() as conn:
        rows = conn.execute("SELECT topic FROM autopilot").fetchall()
    topics = { (r["topic"] or "").strip().lower() for r in rows }
    with connect() as conn:
        rows = conn.execute("SELECT topic FROM projects").fetchall()
    topics.update((r["topic"] or "").strip().lower() for r in rows)
    return {t for t in topics if t}


def autopilot_count_today() -> int:
    day = utcnow()[:10]
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM autopilot WHERE created_at LIKE ? AND status NOT IN ('error','skipped')",
            (f"{day}%",),
        ).fetchone()
    return int(row["n"] if row else 0)


def last_successful_autopilot() -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM autopilot WHERE status IN ('ready','published','scheduled') ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def autopilot_busy() -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM autopilot WHERE status IN ('queued','running')"
        ).fetchone()
    return int(row["n"] if row else 0) > 0
