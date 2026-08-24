from __future__ import annotations

import os

os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api import router
from app.paths import ASSETS_DIR, STATIC_DIR, ensure_dirs
from app.store import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    import asyncio

    task = None
    try:
        from app.services.autopilot import scheduler_loop

        task = asyncio.create_task(scheduler_loop())
    except Exception as exc:
        print("Autopilot scheduler not started:", exc)
    try:
        yield
    finally:
        if task:
            task.cancel()


ensure_dirs()
init_db()

app = FastAPI(title="ChannelForge", version=__version__, docs_url="/api/docs", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/favicon.png")
async def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.png")
