"""Generate daily Cutline puzzles automatically.

Usage:
    python -m scripts.generate_puzzles --days 7
    python -m scripts.generate_puzzles --start 2026-04-15 --days 7
    python -m scripts.generate_puzzles --date 2026-04-15
    python -m scripts.generate_puzzles --days 7 --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base, SessionLocal, engine
from app.models import Puzzle
from app.puzzle_generator import GeneratorError, generate_for_date


async def generate_range(
    session: AsyncSession,
    start: date,
    days: int,
    dry_run: bool,
) -> list[Puzzle]:
    """Generate puzzles for `days` consecutive dates starting from `start`.

    When `dry_run` is True the function still builds each puzzle (to exercise
    the algorithm) but rolls back the transaction so nothing is persisted.
    """
    written: list[Puzzle] = []
    for i in range(days):
        target = start + timedelta(days=i)
        try:
            puzzle = await generate_for_date(session, target, commit=not dry_run)
        except GeneratorError as exc:
            print(f"[{target}] ERROR: {exc}")
            break
        if puzzle is None:
            print(f"[{target}] skipped (puzzle already exists)")
            continue
        written.append(puzzle)
        print(f"[{target}] {puzzle.category_type} — {puzzle.category_text}")
        for entry in sorted(puzzle.entries, key=lambda e: e.grid_position):
            mark = "✓" if entry.is_qualifier else "✗"
            print(f"    {entry.grid_position} {mark} {entry.player.name_display}")
        if dry_run:
            await session.rollback()
    return written


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Cutline puzzles automatically.")
    parser.add_argument("--date", type=_parse_date, help="Generate a single puzzle for this date.")
    parser.add_argument("--start", type=_parse_date, help="Generate a range starting on this date.")
    parser.add_argument("--days", type=int, default=None, help="Number of consecutive days to generate.")
    parser.add_argument("--dry-run", action="store_true", help="Print grids without persisting.")
    args = parser.parse_args()

    if args.date is not None:
        start = args.date
        days = 1
    else:
        start = args.start or date.today()
        days = args.days or 1

    async def _run() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with SessionLocal() as session:
            await generate_range(session, start, days, args.dry_run)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
