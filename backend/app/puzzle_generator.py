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
from app.models import AllStarAppearance, Award, Player, Puzzle, PuzzleEntry, SeasonStat


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


def _date_seed(target_date: date) -> int:
    return int(target_date.strftime("%Y%m%d"))


def _weighted_sample(
    items: list[Player], k: int, weights: list[int], rng: random.Random
) -> list[Player]:
    """Sample `k` distinct items with given integer weights, without replacement.

    Implementation: Efraimidis-Spirakis — assign each item a key
    `u ** (1 / w)` for u ∈ (0, 1), take the top-k by key.
    """
    if k > len(items):
        raise ValueError(f"cannot sample {k} from {len(items)} items")
    scored = []
    for item, w in zip(items, weights):
        w_effective = max(w, 1)  # All-Star-gated pool still gets a positive weight
        u = rng.random()
        # Avoid math.log(0); u is in [0,1) from random.random(). Clamp.
        if u <= 0:
            u = 1e-12
        key = u ** (1.0 / w_effective)
        scored.append((key, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:k]]


async def _puzzle_exists(session: AsyncSession, target_date: date) -> bool:
    stmt = select(Puzzle.id).where(Puzzle.puzzle_date == target_date)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def _explanation_for(session: AsyncSession, category: Category, player: Player, is_qualifier: bool) -> str:
    """Render a short explanation string from the underlying data rows."""
    key = category.key
    if key.startswith("award_"):
        # Look up the most relevant Award row (winner if qualifier, near-miss if not).
        award_type, league = _award_for_category_key(key)
        stmt = select(Award).where(
            Award.player_id == player.id,
            Award.award_type == award_type,
        )
        if league is not None:
            stmt = stmt.where(Award.league == league)
        rows = (await session.execute(stmt.order_by(Award.year))).scalars().all()
        if not rows:
            return f"{player.name_display}: related to {category.display}."
        if is_qualifier:
            winners = [r for r in rows if r.notes == "winner"]
            years = ", ".join(str(r.year) for r in winners) or "—"
            return f"{category.display}: {years}."
        near = [r for r in rows if r.notes and r.notes != "winner"]
        if near:
            years = ", ".join(str(r.year) for r in near[:3])
            return f"Finished near the top in {years} but never won."
        return "Notable vote-getter; never won."

    if key.startswith("stat_"):
        return _stat_explanation(await _aggregate_stats(session, player.id), key, is_qualifier)

    return f"{player.name_display}: related to {category.display}."


def _award_for_category_key(key: str) -> tuple[str, str | None]:
    """Inverse of the `_award_category` registration — category key → (award_type, league)."""
    mapping = {
        "award_mvp_nl": ("MVP", "NL"),
        "award_mvp_al": ("MVP", "AL"),
        "award_cy_young_nl": ("Cy Young", "NL"),
        "award_cy_young_al": ("Cy Young", "AL"),
        "award_roy_nl": ("Rookie of the Year", "NL"),
        "award_roy_al": ("Rookie of the Year", "AL"),
        "award_ws_mvp": ("World Series MVP", None),
        "award_manager_nl": ("Manager of the Year", "NL"),
        "award_manager_al": ("Manager of the Year", "AL"),
    }
    return mapping[key]


@dataclass
class _CareerAggregate:
    hr: int
    hits: int
    sb: int
    wins: int
    strikeouts: int
    best_hr_season: int
    best_avg_season: float
    best_40_40_year: int | None
    allstar_count: int


async def _aggregate_stats(session: AsyncSession, player_id: int) -> _CareerAggregate:
    stmt = select(SeasonStat).where(SeasonStat.player_id == player_id)
    seasons = (await session.execute(stmt)).scalars().all()
    hr = sum(s.home_runs or 0 for s in seasons)
    hits = sum(s.hits or 0 for s in seasons)
    sb = sum(s.stolen_bases or 0 for s in seasons)
    wins = sum(s.wins or 0 for s in seasons)
    strikeouts = sum(s.strikeouts or 0 for s in seasons)
    best_hr = max((s.home_runs or 0 for s in seasons), default=0)
    best_avg = max((float(s.batting_avg) if s.batting_avg else 0.0 for s in seasons), default=0.0)
    best_40_40_year = None
    for s in seasons:
        if (s.home_runs or 0) >= 40 and (s.stolen_bases or 0) >= 40:
            best_40_40_year = s.year
            break

    as_count = (
        await session.execute(
            select(func.count())
            .select_from(AllStarAppearance)
            .where(AllStarAppearance.player_id == player_id)
        )
    ).scalar() or 0

    return _CareerAggregate(
        hr=hr, hits=hits, sb=sb, wins=wins, strikeouts=strikeouts,
        best_hr_season=best_hr, best_avg_season=best_avg,
        best_40_40_year=best_40_40_year, allstar_count=as_count,
    )


def _stat_explanation(agg: _CareerAggregate, category_key: str, is_qualifier: bool) -> str:
    templates = {
        "stat_500_hr":      (f"Career {agg.hr} home runs.",         f"Career {agg.hr} HR — short of 500."),
        "stat_3000_hits":   (f"Career {agg.hits} hits.",            f"Career {agg.hits} hits — short of 3,000."),
        "stat_300_wins":    (f"Career {agg.wins} wins.",            f"Career {agg.wins} wins — short of 300."),
        "stat_3000_k":      (f"Career {agg.strikeouts} strikeouts.", f"Career {agg.strikeouts} K — short of 3,000."),
        "stat_400_sb":      (f"Career {agg.sb} stolen bases.",      f"Career {agg.sb} SB — short of 400."),
        "stat_50_hr_season":(f"Best season: {agg.best_hr_season} HR.", f"Best season: {agg.best_hr_season} HR — never 50."),
        "stat_350_avg_season":(f"Best season average: .{int(round(agg.best_avg_season*1000)):03d}.",
                                f"Best season: .{int(round(agg.best_avg_season*1000)):03d} — never .350."),
        "stat_40_40":       (f"40/40 season in {agg.best_40_40_year}." if agg.best_40_40_year else "40/40 season.",
                                "Came close to 40/40 but never reached both in the same season."),
        "stat_10_allstar":  (f"{agg.allstar_count}× All-Star.", f"{agg.allstar_count}× All-Star — short of 10."),
    }
    qualifier_text, imposter_text = templates.get(category_key, ("Qualifier.", "Near-miss."))
    return qualifier_text if is_qualifier else imposter_text


async def generate_for_date(session: AsyncSession, target_date: date) -> Puzzle | None:
    """Generate and persist a puzzle for `target_date`. Returns None if one already exists.

    Raises `GeneratorError` if no category has a viable gated pool.
    """
    if await _puzzle_exists(session, target_date):
        return None

    seed = _date_seed(target_date)
    pools = await viable_category_pools(session, target_date, rng_seed=seed)
    if pools is None:
        raise GeneratorError(f"No viable category for {target_date}")

    rng = random.Random(seed)
    q_weights = [pools.allstar_counts.get(p.id, 1) for p in pools.qualifiers]
    i_weights = [pools.allstar_counts.get(p.id, 1) for p in pools.imposters]
    picks_q = _weighted_sample(pools.qualifiers, MIN_QUALIFIERS, q_weights, rng)
    picks_i = _weighted_sample(pools.imposters, MIN_IMPOSTERS, i_weights, rng)

    grid_players = picks_q + picks_i
    rng.shuffle(grid_players)
    qualifier_ids = {p.id for p in picks_q}

    puzzle = Puzzle(
        puzzle_date=target_date,
        category_text=pools.category.display,
        category_type=pools.category.key,
        imposter_count=MIN_IMPOSTERS,
        difficulty="medium",
        published=True,
    )
    session.add(puzzle)
    await session.flush()

    for position, player in enumerate(grid_players):
        is_q = player.id in qualifier_ids
        explanation = await _explanation_for(session, pools.category, player, is_q)
        session.add(
            PuzzleEntry(
                puzzle_id=puzzle.id,
                player_id=player.id,
                grid_position=position,
                is_qualifier=is_q,
                explanation=explanation,
            )
        )

    await session.commit()
    await session.refresh(puzzle, attribute_names=["entries"])
    return puzzle
