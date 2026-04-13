"""FastAPI entrypoint for Cutline."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routers import admin as admin_router
from app.routers import puzzle as puzzle_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Cutline API",
        description="Daily MLB grid trivia game.",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(puzzle_router.router)
    app.include_router(admin_router.router)

    # Static mount for uploaded player photos.
    upload_dir = Path(settings.photo_upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        settings.photo_url_prefix,
        StaticFiles(directory=upload_dir),
        name="photos",
    )

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "game": settings.game_name}

    return app


app = create_app()
