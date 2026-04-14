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

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AllStarAppearance, Award, Player, SeasonStat


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


def _stat_career_category(
    key: str,
    display: str,
    stat_column,
    qualifier_threshold: int,
    imposter_range: tuple[int, int],
) -> Category:
    """Build a career-total stat-milestone category.

    Qualifier: SUM(stat_column) >= qualifier_threshold
    Imposter:  SUM(stat_column) BETWEEN imposter_range[0] AND imposter_range[1]
    """

    async def qualifiers(session: AsyncSession) -> list[Player]:
        subq = (
            select(SeasonStat.player_id.label("pid"))
            .group_by(SeasonStat.player_id)
            .having(func.coalesce(func.sum(stat_column), 0) >= qualifier_threshold)
            .subquery()
        )
        stmt = select(Player).join(subq, Player.id == subq.c.pid)
        return list((await session.execute(stmt)).scalars().all())

    async def imposters(session: AsyncSession) -> list[Player]:
        lo, hi = imposter_range
        subq = (
            select(SeasonStat.player_id.label("pid"))
            .group_by(SeasonStat.player_id)
            .having(func.coalesce(func.sum(stat_column), 0).between(lo, hi))
            .subquery()
        )
        stmt = select(Player).join(subq, Player.id == subq.c.pid)
        return list((await session.execute(stmt)).scalars().all())

    return Category(key=key, display=display, qualifier_fn=qualifiers, imposter_fn=imposters)


def _stat_season_category(
    key: str,
    display: str,
    qualifier_predicate,
    imposter_predicate,
) -> Category:
    """Build a single-season-threshold stat category.

    predicate callables take no args and return a SQLAlchemy boolean expression
    over ``SeasonStat``. Qualifier = any season satisfies qualifier_predicate.
    Imposter = some season satisfies imposter_predicate AND no season satisfies
    qualifier_predicate.
    """

    async def qualifiers(session: AsyncSession) -> list[Player]:
        stmt = (
            select(Player)
            .join(SeasonStat, SeasonStat.player_id == Player.id)
            .where(qualifier_predicate())
            .distinct()
        )
        return list((await session.execute(stmt)).scalars().all())

    async def imposters(session: AsyncSession) -> list[Player]:
        # Players with at least one imposter-band season
        imposter_subq = (
            select(SeasonStat.player_id)
            .where(imposter_predicate())
            .distinct()
            .subquery()
        )
        # Players with any qualifier-season (to exclude)
        qualifier_subq = (
            select(SeasonStat.player_id)
            .where(qualifier_predicate())
            .distinct()
            .subquery()
        )
        stmt = (
            select(Player)
            .join(imposter_subq, Player.id == imposter_subq.c.player_id)
            .where(~Player.id.in_(select(qualifier_subq.c.player_id)))
        )
        return list((await session.execute(stmt)).scalars().all())

    return Category(key=key, display=display, qualifier_fn=qualifiers, imposter_fn=imposters)


def _stat_allstar_count_category(
    key: str,
    display: str,
    qualifier_threshold: int,
    imposter_range: tuple[int, int],
) -> Category:
    """Category keyed on COUNT(AllStarAppearance)."""

    async def qualifiers(session: AsyncSession) -> list[Player]:
        subq = (
            select(
                AllStarAppearance.player_id.label("pid"),
            )
            .group_by(AllStarAppearance.player_id)
            .having(func.count() >= qualifier_threshold)
            .subquery()
        )
        stmt = select(Player).join(subq, Player.id == subq.c.pid)
        return list((await session.execute(stmt)).scalars().all())

    async def imposters(session: AsyncSession) -> list[Player]:
        lo, hi = imposter_range
        subq = (
            select(
                AllStarAppearance.player_id.label("pid"),
            )
            .group_by(AllStarAppearance.player_id)
            .having(func.count().between(lo, hi))
            .subquery()
        )
        stmt = select(Player).join(subq, Player.id == subq.c.pid)
        return list((await session.execute(stmt)).scalars().all())

    return Category(key=key, display=display, qualifier_fn=qualifiers, imposter_fn=imposters)


REGISTRY: dict[str, Category] = {
    c.key: c
    for c in (
        # Award categories
        _award_category("award_mvp_nl", "Won NL MVP", "MVP", "NL"),
        _award_category("award_mvp_al", "Won AL MVP", "MVP", "AL"),
        _award_category("award_cy_young_nl", "Won NL Cy Young", "Cy Young", "NL"),
        _award_category("award_cy_young_al", "Won AL Cy Young", "Cy Young", "AL"),
        _award_category("award_roy_nl", "Won NL Rookie of the Year", "Rookie of the Year", "NL"),
        _award_category("award_roy_al", "Won AL Rookie of the Year", "Rookie of the Year", "AL"),
        _award_category("award_ws_mvp", "Won World Series MVP", "World Series MVP", None),
        _award_category("award_manager_nl", "Won NL Manager of the Year", "Manager of the Year", "NL"),
        _award_category("award_manager_al", "Won AL Manager of the Year", "Manager of the Year", "AL"),
        # Career stat-milestone categories
        _stat_career_category("stat_500_hr",    "Hit 500+ career HR",          SeasonStat.home_runs,    500, (400, 499)),
        _stat_career_category("stat_3000_hits", "3,000+ career hits",          SeasonStat.hits,         3000, (2500, 2999)),
        _stat_career_category("stat_300_wins",  "300+ career wins",            SeasonStat.wins,         300, (240, 299)),
        _stat_career_category("stat_3000_k",    "3,000+ career strikeouts",    SeasonStat.strikeouts,   3000, (2500, 2999)),
        _stat_career_category("stat_400_sb",    "400+ career stolen bases",    SeasonStat.stolen_bases, 400, (300, 399)),
        # Season + all-star count categories
        _stat_season_category(
            "stat_50_hr_season", "Hit 50+ HR in a season",
            lambda: SeasonStat.home_runs >= 50,
            lambda: SeasonStat.home_runs.between(45, 49),
        ),
        _stat_season_category(
            "stat_350_avg_season", "Hit .350+ in a qualified season",
            lambda: (SeasonStat.batting_avg >= 0.350) & (SeasonStat.games >= 100),
            lambda: (SeasonStat.batting_avg.between(0.330, 0.349)) & (SeasonStat.games >= 100),
        ),
        _stat_season_category(
            "stat_40_40", "Had a 40/40 season",
            lambda: (SeasonStat.home_runs >= 40) & (SeasonStat.stolen_bases >= 40),
            lambda: (SeasonStat.home_runs >= 35) & (SeasonStat.stolen_bases >= 35),
        ),
        _stat_allstar_count_category("stat_10_allstar", "Made 10+ All-Star Games", 10, (7, 9)),
    )
}


def get_category(key: str) -> Category | None:
    return REGISTRY.get(key)


def list_categories() -> list[dict[str, str]]:
    return [
        {"key": c.key, "display": c.display, "difficulty_hint": c.difficulty_hint}
        for c in REGISTRY.values()
    ]
