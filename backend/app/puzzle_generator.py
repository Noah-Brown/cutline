"""Pure generator engine for daily puzzles.

The CLI in `scripts/generate_puzzles.py` is a thin wrapper; tests drive this
module directly.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.categories import REGISTRY, Category
from app.models import AllStarAppearance, Player, Puzzle


MIN_QUALIFIERS = 6
MIN_IMPOSTERS = 3
ROTATION_WINDOW_DAYS = 14


class GeneratorError(RuntimeError):
    """Raised when no category can produce a valid grid for a given date."""


@dataclass
class CandidatePools:
    category: Category
    qualifiers: list[Player]
    imposters: list[Player]
    allstar_counts: dict[int, int]  # player_id → AS appearance count


async def _allstar_counts_for(session: AsyncSession, player_ids: list[int]) -> dict[int, int]:
    if not player_ids:
        return {}
    stmt = (
        select(AllStarAppearance.player_id, func.count())
        .where(AllStarAppearance.player_id.in_(player_ids))
        .group_by(AllStarAppearance.player_id)
    )
    rows = (await session.execute(stmt)).all()
    return {pid: n for pid, n in rows}


async def allstar_gate(session: AsyncSession, players: list[Player]) -> list[Player]:
    """Filter a player list to those with at least one AllStarAppearance."""
    counts = await _allstar_counts_for(session, [p.id for p in players])
    return [p for p in players if counts.get(p.id, 0) >= 1]


async def _recent_category_keys(session: AsyncSession, target_date: date, window_days: int) -> set[str]:
    cutoff = target_date - timedelta(days=window_days)
    stmt = select(Puzzle.category_type).where(Puzzle.puzzle_date >= cutoff, Puzzle.puzzle_date < target_date)
    rows = (await session.execute(stmt)).scalars().all()
    return set(rows)


async def viable_category_pools(
    session: AsyncSession, target_date: date, rng_seed: int
) -> CandidatePools | None:
    """Find the first category whose gated pools meet MIN_QUALIFIERS / MIN_IMPOSTERS.

    Returns None if no registered category has a viable pool for this date.
    """
    rng = random.Random(rng_seed)
    recent = await _recent_category_keys(session, target_date, ROTATION_WINDOW_DAYS)
    keys = [k for k in REGISTRY if k not in recent]
    rng.shuffle(keys)

    for key in keys:
        category = REGISTRY[key]
        qualifiers = await allstar_gate(session, await category.qualifier_fn(session))
        imposters = await allstar_gate(session, await category.imposter_fn(session))
        q_ids = {p.id for p in qualifiers}
        imposters = [p for p in imposters if p.id not in q_ids]

        if len(qualifiers) < MIN_QUALIFIERS or len(imposters) < MIN_IMPOSTERS:
            continue

        all_ids = [p.id for p in qualifiers] + [p.id for p in imposters]
        as_counts = await _allstar_counts_for(session, all_ids)
        return CandidatePools(
            category=category,
            qualifiers=qualifiers,
            imposters=imposters,
            allstar_counts=as_counts,
        )

    return None
