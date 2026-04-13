"""Admin routes: puzzle CRUD, preview, category registry, player search.

Auth is a simple bearer token (``Settings.admin_token``) for the MVP. Replace
with real auth when user accounts land.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.categories import get_category, list_categories
from app.config import get_settings
from app.database import get_session
from app.models import Player, Puzzle, PuzzleEntry
from app.schemas import (
    CategoryInfo,
    CreatePuzzleRequest,
    PlayerSearchHit,
    PuzzlePlayer,
    PuzzleResponse,
    QualifierPoolResponse,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def require_admin(authorization: str | None = Header(default=None)) -> None:
    settings = get_settings()
    expected = f"Bearer {settings.admin_token}"
    if authorization != expected:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid admin token")


@router.get("/categories", response_model=list[CategoryInfo])
async def admin_list_categories(_: None = Depends(require_admin)) -> list[CategoryInfo]:
    return [CategoryInfo(**c) for c in list_categories()]


@router.get("/pool/{category_key}", response_model=QualifierPoolResponse)
async def admin_pool(
    category_key: str,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin),
) -> QualifierPoolResponse:
    category = get_category(category_key)
    if category is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown category")
    qualifiers = await category.qualifier_fn(session)
    imposters = await category.imposter_fn(session)
    return QualifierPoolResponse(
        category_key=category_key,
        qualifiers=[_hit(p) for p in qualifiers],
        imposter_candidates=[_hit(p) for p in imposters],
    )


@router.get("/players/search", response_model=list[PlayerSearchHit])
async def admin_player_search(
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin),
) -> list[PlayerSearchHit]:
    like = f"%{q}%"
    stmt = (
        select(Player)
        .where(
            or_(
                Player.name_display.ilike(like),
                Player.bbref_id.ilike(like),
            )
        )
        .order_by(Player.name_display)
        .limit(limit)
    )
    players = (await session.execute(stmt)).scalars().all()
    return [_hit(p) for p in players]


@router.post("/puzzle", response_model=PuzzleResponse, status_code=status.HTTP_201_CREATED)
async def admin_create_puzzle(
    body: CreatePuzzleRequest,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin),
) -> PuzzleResponse:
    imposter_count = sum(1 for e in body.entries if not e.is_qualifier)

    # Reject duplicate dates — each date holds one puzzle.
    existing = (
        await session.execute(select(Puzzle).where(Puzzle.puzzle_date == body.puzzle_date))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Puzzle already exists for {body.puzzle_date}"
        )

    puzzle = Puzzle(
        puzzle_date=body.puzzle_date,
        category_text=body.category_text,
        category_type=body.category_type,
        imposter_count=imposter_count,
        difficulty=body.difficulty,
        published=body.published,
    )
    session.add(puzzle)
    await session.flush()

    for entry in body.entries:
        # Verify the player exists before wiring up the entry.
        player = await session.get(Player, entry.player_id)
        if player is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"player_id {entry.player_id} does not exist",
            )
        session.add(
            PuzzleEntry(
                puzzle_id=puzzle.id,
                player_id=entry.player_id,
                grid_position=entry.grid_position,
                is_qualifier=entry.is_qualifier,
                explanation=entry.explanation,
            )
        )

    await session.commit()

    reloaded = (
        await session.execute(
            select(Puzzle)
            .where(Puzzle.id == puzzle.id)
            .options(selectinload(Puzzle.entries).selectinload(PuzzleEntry.player))
        )
    ).scalar_one()

    return PuzzleResponse(
        puzzle_id=reloaded.id,
        puzzle_number=0,  # not yet established until the puzzle is published
        date=reloaded.puzzle_date,
        category=reloaded.category_text,
        players=[
            PuzzlePlayer(
                grid_position=e.grid_position,
                name=e.player.name_display,
                player_id=e.player_id,
            )
            for e in reloaded.entries
        ],
    )


@router.get("/puzzle/preview", response_model=PuzzleResponse)
async def admin_preview(
    puzzle_id: int = Query(...),
    session: AsyncSession = Depends(get_session),
    _: None = Depends(require_admin),
) -> PuzzleResponse:
    stmt = (
        select(Puzzle)
        .where(Puzzle.id == puzzle_id)
        .options(selectinload(Puzzle.entries).selectinload(PuzzleEntry.player))
    )
    puzzle = (await session.execute(stmt)).scalar_one_or_none()
    if puzzle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Puzzle not found")

    return PuzzleResponse(
        puzzle_id=puzzle.id,
        puzzle_number=0,
        date=puzzle.puzzle_date,
        category=puzzle.category_text,
        players=[
            PuzzlePlayer(
                grid_position=e.grid_position,
                name=e.player.name_display,
                player_id=e.player_id,
            )
            for e in puzzle.entries
        ],
    )


def _hit(p: Player) -> PlayerSearchHit:
    return PlayerSearchHit(
        player_id=p.id,
        name=p.name_display,
        debut_year=p.debut_year,
        final_year=p.final_year,
        primary_position=p.primary_position,
    )
