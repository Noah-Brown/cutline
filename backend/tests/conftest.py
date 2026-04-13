"""Shared pytest fixtures: in-memory SQLite engine, app with dep overrides."""

from __future__ import annotations

import os

# Force a fresh file-based SQLite DB per test process (in-memory async is flaky).
os.environ.setdefault(
    "DATABASE_URL", "sqlite+aiosqlite:///./_cutline_test.db"
)

import asyncio
from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_session
from app.main import create_app
from app.models import Award, Player, Puzzle, PuzzleEntry


TEST_DB_URL = os.environ["DATABASE_URL"]


@pytest_asyncio.fixture(scope="function")
async def engine():
    eng = create_async_engine(TEST_DB_URL, future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest_asyncio.fixture
async def db(session_factory) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_puzzle(session_factory) -> dict:
    """Insert a tiny playable puzzle; return useful ids for tests."""
    async with session_factory() as session:
        players = [
            Player(bbref_id="p1", name_display="Barry Bonds"),
            Player(bbref_id="p2", name_display="Albert Pujols"),
            Player(bbref_id="p3", name_display="Derek Jeter"),
            Player(bbref_id="p4", name_display="Bryce Harper"),
            Player(bbref_id="p5", name_display="Paul Goldschmidt"),
            Player(bbref_id="p6", name_display="Tony Gwynn"),
            Player(bbref_id="p7", name_display="Freddie Freeman"),
            Player(bbref_id="p8", name_display="Todd Helton"),
            Player(bbref_id="p9", name_display="Ronald Acuña Jr."),
        ]
        session.add_all(players)
        await session.flush()

        today = date.today()
        puzzle = Puzzle(
            puzzle_date=today,
            category_text="Won NL MVP",
            category_type="award_mvp_nl",
            imposter_count=3,
            difficulty="medium",
            published=True,
        )
        session.add(puzzle)
        await session.flush()

        layout = [
            (0, players[0], True,  "Won NL MVP 7 times."),
            (1, players[1], True,  "Three-time NL MVP with the Cardinals."),
            (2, players[2], False, "AL player — 2nd in 2006 AL MVP voting. Never won."),
            (3, players[3], True,  "Unanimous NL MVP in 2015; again in 2021."),
            (4, players[4], True,  "Won NL MVP in 2022."),
            (5, players[5], False, "8× batting champ; best MVP finish 3rd (1984)."),
            (6, players[6], True,  "Won NL MVP in 2020."),
            (7, players[7], False, "5th in 2000 MVP voting. Never won."),
            (8, players[8], True,  "Unanimous NL MVP in 2023."),
        ]
        for pos, player, is_q, expl in layout:
            session.add(
                PuzzleEntry(
                    puzzle_id=puzzle.id,
                    player_id=player.id,
                    grid_position=pos,
                    is_qualifier=is_q,
                    explanation=expl,
                )
            )
        await session.commit()

        return {
            "puzzle_id": puzzle.id,
            "puzzle_date": today,
            "qualifier_positions": {0, 1, 3, 4, 6, 8},
            "imposter_positions": {2, 5, 7},
        }


@pytest_asyncio.fixture
async def client(engine, session_factory) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_get_session():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
