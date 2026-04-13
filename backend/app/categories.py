"""Category registry — maps category types to qualifier and imposter pools.

Each category describes:
  - A display string (rendered in the puzzle banner)
  - A qualifier query: SELECT DISTINCT player_id FROM ... WHERE ... qualifies
  - An imposter heuristic query: candidate "plausible" near-misses

The puzzle-generation pipeline pulls qualifier and imposter candidates from
these, then a human curator selects the 5–7 qualifiers and 2–4 imposters that
actually ship in the puzzle.

For v1 we register the common award categories. Stat-milestone and
intersection categories live behind the same interface and can be added as
the data pipeline matures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Award, Player


@dataclass(frozen=True)
class Category:
    key: str
    display: str
    qualifier_fn: Callable[[AsyncSession], "object"]
    imposter_fn: Callable[[AsyncSession], "object"]
    difficulty_hint: str = "medium"


async def _award_qualifiers(session: AsyncSession, award_type: str, league: str | None) -> list[Player]:
    stmt = (
        select(Player)
        .join(Award, Award.player_id == Player.id)
        .where(Award.award_type == award_type)
    )
    if league is not None:
        stmt = stmt.where(Award.league == league)
    stmt = stmt.distinct()
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def _award_near_misses(session: AsyncSession, award_type: str, league: str | None) -> list[Player]:
    """Pull players whose Award row for this type has notes like 'runner-up'.

    Lahman's base data only contains winners, so this relies on supplemental
    voting-result data being loaded with ``notes IN ('runner_up', 'top_3', ...)``.
    The query is intentionally permissive so curators can tag near-misses however
    they prefer.
    """
    stmt = (
        select(Player)
        .join(Award, Award.player_id == Player.id)
        .where(Award.award_type == award_type)
        .where(Award.notes.is_not(None))
    )
    if league is not None:
        stmt = stmt.where(Award.league == league)
    stmt = stmt.distinct()
    result = await session.execute(stmt)
    return list(result.scalars().all())


def _award_category(key: str, display: str, award_type: str, league: str | None) -> Category:
    async def qualifiers(s: AsyncSession) -> list[Player]:
        return await _award_qualifiers(s, award_type, league)

    async def imposters(s: AsyncSession) -> list[Player]:
        return await _award_near_misses(s, award_type, league)

    return Category(key=key, display=display, qualifier_fn=qualifiers, imposter_fn=imposters)


REGISTRY: dict[str, Category] = {
    c.key: c
    for c in (
        _award_category("award_mvp_nl", "Won NL MVP", "MVP", "NL"),
        _award_category("award_mvp_al", "Won AL MVP", "MVP", "AL"),
        _award_category("award_cy_young_nl", "Won NL Cy Young", "Cy Young", "NL"),
        _award_category("award_cy_young_al", "Won AL Cy Young", "Cy Young", "AL"),
        _award_category("award_roy_nl", "Won NL Rookie of the Year", "Rookie of the Year", "NL"),
        _award_category("award_roy_al", "Won AL Rookie of the Year", "Rookie of the Year", "AL"),
        _award_category("award_ws_mvp", "Won World Series MVP", "World Series MVP", None),
        _award_category("award_manager_nl", "Won NL Manager of the Year", "Manager of the Year", "NL"),
        _award_category("award_manager_al", "Won AL Manager of the Year", "Manager of the Year", "AL"),
    )
}


def get_category(key: str) -> Category | None:
    return REGISTRY.get(key)


def list_categories() -> list[dict[str, str]]:
    return [
        {"key": c.key, "display": c.display, "difficulty_hint": c.difficulty_hint}
        for c in REGISTRY.values()
    ]
