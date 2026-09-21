"""FastAPI application wiring."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api import router
from .config import settings
from .db import create_all
from .pregame import router as pregame_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_all()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Taiwanese Baseball Player Watch",
        description=(
            "Event monitoring for selected Taiwanese hitters: detects newly "
            "completed plate appearances, evaluates watch rules, raises alerts."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    app.include_router(pregame_router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    frontend_dir = settings.frontend_dir
    if frontend_dir.is_dir():
        app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(frontend_dir / "index.html")

    return app


app = create_app()
