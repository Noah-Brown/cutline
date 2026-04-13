"""Public puzzle routes: today, submit, stats, archive, streak."""

from __future__ import annotations

from datetime import date, timezone, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_session
from app.models import Player, Puzzle, PuzzleEntry, Submission
from app.schemas import (
    PlayerResult,
    PuzzlePlayer,
    PuzzleResponse,
    PuzzleStats,
    StreakResponse,
    SubmitRequest,
    SubmitResponse,
)
from app.scoring import render_share_text, score_submission

router = APIRouter(prefix="/api/puzzle", tags=["puzzle"])


def _today_et() -> date:
    """Return the current date in US Eastern Time.

    The design spec specifies midnight-ET releases. We approximate ET as
    UTC-4 (EDT); in production use zoneinfo('America/New_York') to handle DST
    correctly. zoneinfo is stdlib but the tzdata availability varies per OS,
    and this service-level detail isn't worth a hard runtime dep for the MVP.
    """
    from datetime import timedelta

    return (datetime.now(timezone.utc) - timedelta(hours=4)).date()


async def _load_puzzle_with_entries(session: AsyncSession, puzzle_id: int) -> Puzzle | None:
    stmt = (
        select(Puzzle)
        .where(Puzzle.id == puzzle_id)
        .options(selectinload(Puzzle.entries).selectinload(PuzzleEntry.player))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def _puzzle_number(session: AsyncSession, puzzle: Puzzle) -> int:
    """1-indexed number based on chronological published order."""
    stmt = (
        select(func.count(Puzzle.id))
        .where(Puzzle.published.is_(True))
        .where(Puzzle.puzzle_date <= puzzle.puzzle_date)
    )
    result = await session.execute(stmt)
    return result.scalar_one() or 1


def _to_puzzle_response(puzzle: Puzzle, puzzle_number: int) -> PuzzleResponse:
    return PuzzleResponse(
        puzzle_id=puzzle.id,
        puzzle_number=puzzle_number,
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


@router.get("/today", response_model=PuzzleResponse)
async def get_today(session: AsyncSession = Depends(get_session)) -> PuzzleResponse:
    target = _today_et()
    stmt = (
        select(Puzzle)
        .where(Puzzle.puzzle_date == target)
        .where(Puzzle.published.is_(True))
        .options(selectinload(Puzzle.entries).selectinload(PuzzleEntry.player))
    )
    result = await session.execute(stmt)
    puzzle = result.scalar_one_or_none()

    if puzzle is None:
        # Fallback: serve the most recent published puzzle (useful for demos
        # where the daily-cron hasn't been wired up yet).
        stmt = (
            select(Puzzle)
            .where(Puzzle.published.is_(True))
            .order_by(Puzzle.puzzle_date.desc())
            .limit(1)
            .options(selectinload(Puzzle.entries).selectinload(PuzzleEntry.player))
        )
        result = await session.execute(stmt)
        puzzle = result.scalar_one_or_none()

    if puzzle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No puzzle available")

    number = await _puzzle_number(session, puzzle)
    return _to_puzzle_response(puzzle, number)


@router.get("/stats", response_model=PuzzleStats)
async def get_stats(
    puzzle_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> PuzzleStats:
    if puzzle_id is None:
        # Default: today's puzzle
        target = _today_et()
        stmt = select(Puzzle).where(Puzzle.puzzle_date == target)
        puzzle = (await session.execute(stmt)).scalar_one_or_none()
        if puzzle is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No puzzle for today")
        puzzle_id = puzzle.id

    count_stmt = select(func.count(Submission.id)).where(Submission.puzzle_id == puzzle_id)
    avg_stmt = select(func.avg(Submission.score)).where(Submission.puzzle_id == puzzle_id)
    perfect_stmt = (
        select(func.count(Submission.id))
        .where(Submission.puzzle_id == puzzle_id)
        .where(Submission.perfect.is_(True))
    )
    submissions = (await session.execute(count_stmt)).scalar_one() or 0
    avg = (await session.execute(avg_stmt)).scalar_one()
    perfect = (await session.execute(perfect_stmt)).scalar_one() or 0

    return PuzzleStats(
        puzzle_id=puzzle_id,
        submissions=submissions,
        avg_score=float(avg) if avg is not None else None,
        perfect_count=perfect,
    )


@router.get("/streak", response_model=StreakResponse)
async def get_streak(
    session_id: str = Query(min_length=1, max_length=100),
    session: AsyncSession = Depends(get_session),
) -> StreakResponse:
    stmt = (
        select(Submission, Puzzle.puzzle_date)
        .join(Puzzle, Puzzle.id == Submission.puzzle_id)
        .where(Submission.session_id == session_id)
        .order_by(Puzzle.puzzle_date.asc())
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        return StreakResponse(
            session_id=session_id,
            current_streak=0,
            longest_streak=0,
            last_played_date=None,
        )

    dates = [row[1] for row in rows]
    longest = 1
    current_run = 1
    for prev, curr in zip(dates, dates[1:]):
        if (curr - prev).days == 1:
            current_run += 1
            longest = max(longest, current_run)
        else:
            current_run = 1

    today = _today_et()
    last = dates[-1]
    gap = (today - last).days
    # Current streak = run that is still "alive" (last play was today or yesterday)
    if gap > 1:
        current_streak = 0
    else:
        current_streak = current_run

    return StreakResponse(
        session_id=session_id,
        current_streak=current_streak,
        longest_streak=longest,
        last_played_date=last,
    )


@router.post("/submit", response_model=SubmitResponse)
async def submit(
    body: SubmitRequest,
    session: AsyncSession = Depends(get_session),
) -> SubmitResponse:
    settings = get_settings()

    puzzle = await _load_puzzle_with_entries(session, body.puzzle_id)
    if puzzle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Puzzle not found")
    if not puzzle.published:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Puzzle not published")

    # Enforce one submission per (puzzle, session)
    existing_stmt = (
        select(Submission)
        .where(Submission.puzzle_id == body.puzzle_id)
        .where(Submission.session_id == body.session_id)
    )
    existing = (await session.execute(existing_stmt)).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Already submitted for this puzzle/session",
        )

    entries_tuple = [(e.grid_position, e.is_qualifier) for e in puzzle.entries]
    result = score_submission(entries_tuple, set(body.selections))

    submission = Submission(
        puzzle_id=puzzle.id,
        session_id=body.session_id,
        selections=body.selections,
        score=result.score,
        max_score=result.max_score,
        perfect=result.perfect,
    )
    session.add(submission)
    await session.commit()

    # Build the results payload keyed by grid_position
    entry_by_pos = {e.grid_position: e for e in puzzle.entries}
    results: list[PlayerResult] = []
    for outcome in result.outcomes:
        entry = entry_by_pos[outcome.grid_position]
        results.append(
            PlayerResult(
                grid_position=outcome.grid_position,
                player_id=entry.player_id,
                name=entry.player.name_display,
                is_qualifier=entry.is_qualifier,
                was_selected=outcome.was_selected,
                result=outcome.result.value,
                explanation=entry.explanation,
            )
        )

    puzzle_number = await _puzzle_number(session, puzzle)
    share_text = render_share_text(
        game_name=settings.game_name,
        puzzle_number=puzzle_number,
        category_text=puzzle.category_text,
        outcomes=result.outcomes,
        score=result.score,
        max_score=result.max_score,
    )

    return SubmitResponse(
        puzzle_id=puzzle.id,
        score=result.score,
        max_score=result.max_score,
        perfect=result.perfect,
        results=results,
        share_text=share_text,
    )


@router.get("/{puzzle_date}", response_model=PuzzleResponse)
async def get_archive(
    puzzle_date: date,
    session: AsyncSession = Depends(get_session),
) -> PuzzleResponse:
    stmt = (
        select(Puzzle)
        .where(Puzzle.puzzle_date == puzzle_date)
        .where(Puzzle.published.is_(True))
        .options(selectinload(Puzzle.entries).selectinload(PuzzleEntry.player))
    )
    puzzle = (await session.execute(stmt)).scalar_one_or_none()
    if puzzle is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No puzzle on that date")
    number = await _puzzle_number(session, puzzle)
    return _to_puzzle_response(puzzle, number)
