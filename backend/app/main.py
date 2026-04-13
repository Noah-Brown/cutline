"""FastAPI entrypoint for Cutline."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "game": settings.game_name}

    return app


app = create_app()
