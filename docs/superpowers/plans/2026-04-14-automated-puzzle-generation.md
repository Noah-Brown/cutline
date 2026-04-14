# Automated Puzzle Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an end-to-end automated puzzle generator that ingests Lahman share-vote data, adds 9 stat-milestone categories, and produces 7 published daily puzzles (2026-04-15 through 2026-04-21) via date-seeded weighted sampling gated by All-Star recognizability, with guardrails that refuse to publish low-quality grids.

**Architecture:**
1. Extend `scripts/ingest_lahman.py` with share-vote loaders that insert non-winner `Award` rows tagged `notes="top_3"`/`"top_5"` — this populates the existing award-imposter query.
2. Extend `app/categories.py` with a stat-category factory and 9 new milestone entries; `REGISTRY` grows to 18 categories.
3. New `scripts/generate_puzzles.py` picks categories (rotating with a 14-day window), applies an All-Star gate (`≥1` appearance) to qualifier/imposter pools, samples 6 + 3 with date-seeded weighted RNG, and writes a published `Puzzle` + 9 `PuzzleEntry` rows.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.x async, SQLite (dev/test) + Postgres (prod), pytest + pytest-asyncio, Ruff.

**Spec:** `docs/superpowers/specs/2026-04-14-automated-puzzle-generation-design.md`

---

## File Structure

**Modify:**
- `backend/scripts/ingest_lahman.py` — add `_load_award_shares` and `_load_award_share_managers`; call both from `ingest()` after `_load_awards`.
- `backend/app/categories.py` — add `_stat_career_category`, `_stat_season_category`, `_stat_allstar_count_category` factories plus 9 new entries in `REGISTRY`.

**Create:**
- `backend/scripts/generate_puzzles.py` — the generator + CLI entry point.
- `backend/app/puzzle_generator.py` — the pure generator library (the CLI is a thin wrapper so tests can import the engine directly).
- `backend/tests/test_ingest_shares.py` — share-vote ingest tests.
- `backend/tests/test_categories_stat.py` — stat-category SQL tests.
- `backend/tests/test_puzzle_generator.py` — generator algorithm + guardrail tests.

---

## Task 1: Add share-vote ingest loaders

**Files:**
- Modify: `backend/scripts/ingest_lahman.py`
- Create: `backend/tests/test_ingest_shares.py`

The spec requires non-winner voting results loaded into the `Award` table with `notes="top_3"` or `notes="top_5"` so the existing `_award_near_misses` query finds imposters.

- [ ] **Step 1.1: Write the failing test**

Create `backend/tests/test_ingest_shares.py`:

```python
"""Tests for AwardsSharePlayers / AwardsShareManagers loaders."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Award, Player
from scripts.ingest_lahman import _load_award_shares


class _DictOpener:
    """Opener stub — returns iter(rows) when the given filename is requested."""

    def __init__(self, files: dict[str, list[dict]]):
        self._files = files

    def __call__(self, name):
        return iter(self._files.get(name, []))


@pytest.mark.asyncio
async def test_load_award_shares_inserts_top_3_and_top_5(db):
    # Seed two players + one existing winner row.
    winner = Player(bbref_id="winnerxx01", name_display="Winning Winner")
    runner = Player(bbref_id="runnerxx01", name_display="Runner Runner")
    lowvote = Player(bbref_id="lowvotxx01", name_display="Low Vote")
    db.add_all([winner, runner, lowvote])
    await db.flush()

    db.add(
        Award(
            player_id=winner.id, award_type="MVP", year=2020, league="NL", notes="winner"
        )
    )
    await db.commit()

    opener = _DictOpener(
        {
            "AwardsSharePlayers.csv": [
                # The winner — skip (already has a winner row)
                {
                    "awardID": "Most Valuable Player",
                    "yearID": "2020",
                    "lgID": "NL",
                    "playerID": "winnerxx01",
                    "pointsWon": "420",
                    "pointsMax": "420",
                    "votesFirst": "30",
                },
                # The runner-up at 0.55 share → top_3
                {
                    "awardID": "Most Valuable Player",
                    "yearID": "2020",
                    "lgID": "NL",
                    "playerID": "runnerxx01",
                    "pointsWon": "231",
                    "pointsMax": "420",
                    "votesFirst": "0",
                },
                # A low-vote player at 0.10 share → top_5
                {
                    "awardID": "Most Valuable Player",
                    "yearID": "2020",
                    "lgID": "NL",
                    "playerID": "lowvotxx01",
                    "pointsWon": "42",
                    "pointsMax": "420",
                    "votesFirst": "0",
                },
                # Zero-vote row → skipped
                {
                    "awardID": "Most Valuable Player",
                    "yearID": "2020",
                    "lgID": "NL",
                    "playerID": "lowvotxx01",
                    "pointsWon": "0",
                    "pointsMax": "420",
                    "votesFirst": "0",
                },
            ]
        }
    )
    id_map = {"winnerxx01": winner.id, "runnerxx01": runner.id, "lowvotxx01": lowvote.id}

    await _load_award_shares(db, opener, id_map)

    rows = (await db.execute(select(Award).order_by(Award.player_id))).scalars().all()
    by_player = {r.player_id: r for r in rows}

    assert by_player[winner.id].notes == "winner"
    assert by_player[runner.id].notes == "top_3"
    assert by_player[runner.id].award_type == "MVP"
    assert by_player[lowvote.id].notes == "top_5"


@pytest.mark.asyncio
async def test_load_award_shares_is_idempotent(db):
    player = Player(bbref_id="testpxx01", name_display="Test Player")
    db.add(player)
    await db.flush()

    rows = [
        {
            "awardID": "Cy Young Award",
            "yearID": "2018",
            "lgID": "AL",
            "playerID": "testpxx01",
            "pointsWon": "100",
            "pointsMax": "200",
            "votesFirst": "0",
        }
    ]
    id_map = {"testpxx01": player.id}

    await _load_award_shares(db, _DictOpener({"AwardsSharePlayers.csv": rows}), id_map)
    await _load_award_shares(db, _DictOpener({"AwardsSharePlayers.csv": rows}), id_map)

    all_rows = (await db.execute(select(Award))).scalars().all()
    assert len(all_rows) == 1
    assert all_rows[0].notes == "top_3"
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_ingest_shares.py -v`
Expected: FAIL with `ImportError: cannot import name '_load_award_shares' from 'scripts.ingest_lahman'`

- [ ] **Step 1.3: Implement `_load_award_shares` and call it from `ingest`**

In `backend/scripts/ingest_lahman.py`, add this function immediately after `_load_awards`:

```python
async def _load_award_shares(
    session: AsyncSession, opener: CsvOpener, id_map: dict[str, int]
) -> None:
    """Load non-winner voting-share data into Award rows tagged top_3 / top_5.

    The existing `_award_near_misses` imposter query pulls Award rows where
    `notes IS NOT NULL` and != winner. Tagging share-vote recipients with
    top_3/top_5 makes them available as imposter candidates automatically.
    """
    print("  award shares: AwardsSharePlayers.csv")
    count = 0
    for row in opener("AwardsSharePlayers.csv"):
        player_id = id_map.get(row.get("playerID", ""))
        if player_id is None:
            continue

        points_won = _int(row.get("pointsWon")) or 0
        points_max = _int(row.get("pointsMax")) or 0
        if points_won <= 0 or points_max <= 0:
            continue

        raw_name = row.get("awardID", "")
        award_type = AWARD_NAME_MAP.get(raw_name, raw_name)
        year = _int(row.get("yearID"))
        if year is None:
            continue
        league = row.get("lgID") or None
        if league in ("", "ML"):
            league = None

        existing = (
            await session.execute(
                select(Award).where(
                    Award.player_id == player_id,
                    Award.award_type == award_type,
                    Award.year == year,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            # Winner already recorded, or we already loaded this share row.
            continue

        share = points_won / points_max
        notes = "top_3" if share >= 0.40 else "top_5"

        session.add(
            Award(
                player_id=player_id,
                award_type=award_type,
                year=year,
                league=league,
                team=None,
                notes=notes,
            )
        )
        count += 1
        if count % 1000 == 0:
            await session.commit()

    await session.commit()
    print(f"  award shares: {count} inserted")


async def _load_award_share_managers(
    session: AsyncSession, opener: CsvOpener, id_map: dict[str, int]
) -> None:
    """Same as `_load_award_shares` but for AwardsShareManagers.csv.

    Managers live in the same People table and share the id_map; award_type
    always maps to 'Manager of the Year'.
    """
    print("  manager award shares: AwardsShareManagers.csv")
    count = 0
    for row in opener("AwardsShareManagers.csv"):
        player_id = id_map.get(row.get("playerID", ""))
        if player_id is None:
            continue

        points_won = _int(row.get("pointsWon")) or 0
        points_max = _int(row.get("pointsMax")) or 0
        if points_won <= 0 or points_max <= 0:
            continue

        year = _int(row.get("yearID"))
        if year is None:
            continue
        league = row.get("lgID") or None
        if league in ("", "ML"):
            league = None

        existing = (
            await session.execute(
                select(Award).where(
                    Award.player_id == player_id,
                    Award.award_type == "Manager of the Year",
                    Award.year == year,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue

        share = points_won / points_max
        notes = "top_3" if share >= 0.40 else "top_5"

        session.add(
            Award(
                player_id=player_id,
                award_type="Manager of the Year",
                year=year,
                league=league,
                team=None,
                notes=notes,
            )
        )
        count += 1
        if count % 500 == 0:
            await session.commit()

    await session.commit()
    print(f"  manager award shares: {count} inserted")
```

Then modify `ingest()` in the same file to call them after `_load_awards`:

```python
async def ingest(opener: CsvOpener) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        id_map = await _load_people(session, opener)
        await _load_awards(session, opener, id_map)
        await _load_award_shares(session, opener, id_map)
        await _load_award_share_managers(session, opener, id_map)
        await _load_allstar(session, opener, id_map)
        await _load_batting(session, opener, id_map)
        await _load_pitching(session, opener, id_map)
    print("Ingest complete.")
```

- [ ] **Step 1.4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_ingest_shares.py -v`
Expected: both tests PASS.

- [ ] **Step 1.5: Run the full test suite to verify no regressions**

Run: `cd backend && pytest -q`
Expected: all existing tests + 2 new tests pass.

- [ ] **Step 1.6: Commit**

```bash
git add backend/scripts/ingest_lahman.py backend/tests/test_ingest_shares.py
git commit -m "feat(ingest): load award share-vote data as top_3/top_5 near-misses"
```

---

## Task 2: Add career stat-milestone categories

**Files:**
- Modify: `backend/app/categories.py`
- Create: `backend/tests/test_categories_stat.py`

Add a `_stat_career_category` factory and register 5 career-total categories: `stat_500_hr`, `stat_3000_hits`, `stat_300_wins`, `stat_3000_k`, `stat_400_sb`.

- [ ] **Step 2.1: Write the failing test**

Create `backend/tests/test_categories_stat.py`:

```python
"""Tests for stat-milestone categories."""

from __future__ import annotations

import pytest

from app.categories import REGISTRY
from app.models import Player, SeasonStat


async def _add_player_with_hr(db, bbref: str, name: str, hr_totals: list[int]) -> Player:
    p = Player(bbref_id=bbref, name_display=name)
    db.add(p)
    await db.flush()
    for i, hr in enumerate(hr_totals):
        db.add(
            SeasonStat(player_id=p.id, year=2000 + i, team="NYY", home_runs=hr)
        )
    await db.commit()
    return p


@pytest.mark.asyncio
async def test_stat_500_hr_qualifier_pool(db):
    # Bonds-alike: 10 seasons * 60 HR = 600 career → qualifier
    above = await _add_player_with_hr(db, "bigslgxx01", "Big Slugger", [60] * 10)
    # Edge: exactly 500 → qualifier
    at = await _add_player_with_hr(db, "edgeslgxx01", "Edge Slugger", [50] * 10)
    # Just short: 480 → imposter
    near = await _add_player_with_hr(db, "nearslgxx01", "Near Slugger", [48] * 10)
    # Irrelevant: 100 HR → neither pool
    low = await _add_player_with_hr(db, "lowhrxx01", "Low HR", [10] * 10)

    category = REGISTRY["stat_500_hr"]
    qualifiers = await category.qualifier_fn(db)
    imposters = await category.imposter_fn(db)

    q_ids = {p.id for p in qualifiers}
    i_ids = {p.id for p in imposters}

    assert above.id in q_ids
    assert at.id in q_ids
    assert near.id in i_ids
    assert low.id not in q_ids and low.id not in i_ids


@pytest.mark.asyncio
async def test_stat_500_hr_qualifier_excluded_from_imposter(db):
    # A 500-HR player should never appear in the imposter pool.
    p = await _add_player_with_hr(db, "dualxx01", "Dual", [50] * 10)
    category = REGISTRY["stat_500_hr"]
    imposters = await category.imposter_fn(db)
    assert p.id not in {x.id for x in imposters}


@pytest.mark.asyncio
async def test_all_career_stat_categories_registered(db):
    for key in ("stat_500_hr", "stat_3000_hits", "stat_300_wins", "stat_3000_k", "stat_400_sb"):
        assert key in REGISTRY, f"{key} not in REGISTRY"
```

- [ ] **Step 2.2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_categories_stat.py -v`
Expected: FAIL — `KeyError: 'stat_500_hr'` (categories not yet registered).

- [ ] **Step 2.3: Implement `_stat_career_category` factory + 5 entries**

Add to `backend/app/categories.py` below `_award_category`:

```python
from sqlalchemy import func

from app.models import SeasonStat


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
            select(
                SeasonStat.player_id.label("pid"),
                func.coalesce(func.sum(stat_column), 0).label("total"),
            )
            .group_by(SeasonStat.player_id)
            .having(func.coalesce(func.sum(stat_column), 0) >= qualifier_threshold)
            .subquery()
        )
        stmt = select(Player).join(subq, Player.id == subq.c.pid)
        return list((await session.execute(stmt)).scalars().all())

    async def imposters(session: AsyncSession) -> list[Player]:
        lo, hi = imposter_range
        subq = (
            select(
                SeasonStat.player_id.label("pid"),
                func.coalesce(func.sum(stat_column), 0).label("total"),
            )
            .group_by(SeasonStat.player_id)
            .having(func.coalesce(func.sum(stat_column), 0).between(lo, hi))
            .subquery()
        )
        stmt = select(Player).join(subq, Player.id == subq.c.pid)
        return list((await session.execute(stmt)).scalars().all())

    return Category(key=key, display=display, qualifier_fn=qualifiers, imposter_fn=imposters)
```

Then extend `REGISTRY` with 5 career entries. Replace the existing `REGISTRY` block with:

```python
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
    )
}
```

- [ ] **Step 2.4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_categories_stat.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 2.5: Run the full test suite**

Run: `cd backend && pytest -q`
Expected: all tests pass.

- [ ] **Step 2.6: Commit**

```bash
git add backend/app/categories.py backend/tests/test_categories_stat.py
git commit -m "feat(categories): add 5 career-total stat milestone categories"
```

---

## Task 3: Add season + all-star count stat categories

**Files:**
- Modify: `backend/app/categories.py`
- Modify: `backend/tests/test_categories_stat.py`

Add 4 more category entries: `stat_50_hr_season`, `stat_350_avg_season`, `stat_40_40`, `stat_10_allstar`. These need two new factories — a per-season "any season above threshold" factory and an all-star count factory. The `stat_40_40` category is a one-off custom query.

- [ ] **Step 3.1: Write failing tests**

Append to `backend/tests/test_categories_stat.py`:

```python
from app.models import AllStarAppearance


@pytest.mark.asyncio
async def test_stat_50_hr_season_qualifier(db):
    # Best season 60 HR → qualifier
    hi = Player(bbref_id="hi50xx01", name_display="Fifty Plus")
    db.add(hi)
    await db.flush()
    db.add(SeasonStat(player_id=hi.id, year=2001, team="SFG", home_runs=60, games=162))

    # Best season 47 HR → imposter
    mid = Player(bbref_id="mid45xx01", name_display="Mid Forties")
    db.add(mid)
    await db.flush()
    db.add(SeasonStat(player_id=mid.id, year=2001, team="NYY", home_runs=47, games=162))

    # Best season 30 HR → neither
    low = Player(bbref_id="low30xx01", name_display="Thirty")
    db.add(low)
    await db.flush()
    db.add(SeasonStat(player_id=low.id, year=2001, team="BOS", home_runs=30, games=162))
    await db.commit()

    category = REGISTRY["stat_50_hr_season"]
    qualifiers = await category.qualifier_fn(db)
    imposters = await category.imposter_fn(db)
    assert hi.id in {p.id for p in qualifiers}
    assert mid.id in {p.id for p in imposters}
    assert low.id not in {p.id for p in qualifiers} | {p.id for p in imposters}


@pytest.mark.asyncio
async def test_stat_40_40_qualifier(db):
    # 40/40 season → qualifier
    dual = Player(bbref_id="dual4040", name_display="Forty Forty")
    db.add(dual)
    await db.flush()
    db.add(SeasonStat(player_id=dual.id, year=1998, team="SEA", home_runs=42, stolen_bases=46, games=162))

    # 38/38 — never 40/40 → imposter
    near = Player(bbref_id="near3838", name_display="Thirty Eight")
    db.add(near)
    await db.flush()
    db.add(SeasonStat(player_id=near.id, year=1998, team="OAK", home_runs=38, stolen_bases=38, games=162))
    await db.commit()

    category = REGISTRY["stat_40_40"]
    qualifiers = await category.qualifier_fn(db)
    imposters = await category.imposter_fn(db)
    assert dual.id in {p.id for p in qualifiers}
    assert near.id in {p.id for p in imposters}
    assert dual.id not in {p.id for p in imposters}


@pytest.mark.asyncio
async def test_stat_10_allstar_qualifier(db):
    hi = Player(bbref_id="as11xx01", name_display="All Eleven")
    low = Player(bbref_id="as08xx01", name_display="All Eight")
    nope = Player(bbref_id="as00xx01", name_display="No Stars")
    db.add_all([hi, low, nope])
    await db.flush()
    for y in range(2000, 2011):  # 11 all-star games
        db.add(AllStarAppearance(player_id=hi.id, year=y))
    for y in range(2000, 2008):  # 8 all-star games
        db.add(AllStarAppearance(player_id=low.id, year=y))
    await db.commit()

    category = REGISTRY["stat_10_allstar"]
    qualifiers = await category.qualifier_fn(db)
    imposters = await category.imposter_fn(db)
    assert hi.id in {p.id for p in qualifiers}
    assert low.id in {p.id for p in imposters}
    assert nope.id not in {p.id for p in qualifiers} | {p.id for p in imposters}
```

- [ ] **Step 3.2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_categories_stat.py -v`
Expected: 3 new tests FAIL with `KeyError` for unregistered categories.

- [ ] **Step 3.3: Add the three new factories + register entries**

Append to `backend/app/categories.py` above the `REGISTRY` block:

```python
from app.models import AllStarAppearance


def _stat_season_category(
    key: str,
    display: str,
    qualifier_predicate,
    imposter_predicate,
) -> Category:
    """Build a single-season-threshold stat category.

    predicate callables take no args and return a SQLAlchemy boolean expression
    over `SeasonStat`. Qualifier = any season satisfies qualifier_predicate.
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
                func.count().label("n"),
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
                func.count().label("n"),
            )
            .group_by(AllStarAppearance.player_id)
            .having(func.count().between(lo, hi))
            .subquery()
        )
        stmt = select(Player).join(subq, Player.id == subq.c.pid)
        return list((await session.execute(stmt)).scalars().all())

    return Category(key=key, display=display, qualifier_fn=qualifiers, imposter_fn=imposters)


def _stat_40_40_category() -> Category:
    """Hand-rolled 40/40 category (multi-column season predicate with exclusion)."""

    async def qualifiers(session: AsyncSession) -> list[Player]:
        stmt = (
            select(Player)
            .join(SeasonStat, SeasonStat.player_id == Player.id)
            .where(SeasonStat.home_runs >= 40, SeasonStat.stolen_bases >= 40)
            .distinct()
        )
        return list((await session.execute(stmt)).scalars().all())

    async def imposters(session: AsyncSession) -> list[Player]:
        qualifier_subq = (
            select(SeasonStat.player_id)
            .where(SeasonStat.home_runs >= 40, SeasonStat.stolen_bases >= 40)
            .distinct()
            .subquery()
        )
        imposter_subq = (
            select(SeasonStat.player_id)
            .where(SeasonStat.home_runs >= 35, SeasonStat.stolen_bases >= 35)
            .distinct()
            .subquery()
        )
        stmt = (
            select(Player)
            .join(imposter_subq, Player.id == imposter_subq.c.player_id)
            .where(~Player.id.in_(select(qualifier_subq.c.player_id)))
        )
        return list((await session.execute(stmt)).scalars().all())

    return Category(
        key="stat_40_40",
        display="Had a 40/40 season",
        qualifier_fn=qualifiers,
        imposter_fn=imposters,
    )
```

Then extend `REGISTRY` — add the 4 new entries to the tuple inside the dict comprehension:

```python
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
        _stat_40_40_category(),
        _stat_allstar_count_category("stat_10_allstar", "Made 10+ All-Star Games", 10, (7, 9)),
```

- [ ] **Step 3.4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_categories_stat.py -v`
Expected: all 6 tests in the file PASS.

- [ ] **Step 3.5: Run the full test suite**

Run: `cd backend && pytest -q`
Expected: all tests pass.

- [ ] **Step 3.6: Commit**

```bash
git add backend/app/categories.py backend/tests/test_categories_stat.py
git commit -m "feat(categories): add season + all-star count milestone categories"
```

---

## Task 4: Generator core — All-Star gate and pool validation

**Files:**
- Create: `backend/app/puzzle_generator.py`
- Create: `backend/tests/test_puzzle_generator.py`

This task builds the foundation: the All-Star gate that filters candidate pools, plus the `GeneratorError` and a stub `generate_for_date` that validates the first viable category's pool without yet sampling or writing.

- [ ] **Step 4.1: Write the failing test**

Create `backend/tests/test_puzzle_generator.py`:

```python
"""Tests for the puzzle generator engine."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.models import AllStarAppearance, Award, Player, Puzzle
from app.puzzle_generator import GeneratorError, allstar_gate, viable_category_pools


async def _mk_player(db, bbref: str, name: str, allstars: int = 0) -> Player:
    p = Player(bbref_id=bbref, name_display=name)
    db.add(p)
    await db.flush()
    for y in range(2000, 2000 + allstars):
        db.add(AllStarAppearance(player_id=p.id, year=y))
    await db.commit()
    return p


@pytest.mark.asyncio
async def test_allstar_gate_keeps_only_players_with_all_star_appearances(db):
    has_star = await _mk_player(db, "starxx01", "Has Star", allstars=1)
    no_star = await _mk_player(db, "nostxx01", "No Star", allstars=0)

    gated = await allstar_gate(db, [has_star, no_star])

    assert has_star in gated
    assert no_star not in gated


@pytest.mark.asyncio
async def test_viable_category_pools_returns_none_when_no_category_has_enough(db):
    # Empty DB — every category has 0 qualifiers / 0 imposters.
    result = await viable_category_pools(db, target_date=date(2026, 4, 15), rng_seed=1)
    assert result is None
```

- [ ] **Step 4.2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_puzzle_generator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.puzzle_generator'`.

- [ ] **Step 4.3: Implement the generator module skeleton**

Create `backend/app/puzzle_generator.py`:

```python
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
```

- [ ] **Step 4.4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_puzzle_generator.py -v`
Expected: 2 tests PASS.

- [ ] **Step 4.5: Run the full test suite**

Run: `cd backend && pytest -q`
Expected: all tests pass.

- [ ] **Step 4.6: Commit**

```bash
git add backend/app/puzzle_generator.py backend/tests/test_puzzle_generator.py
git commit -m "feat(generator): All-Star gate + viable-category-pool selector"
```

---

## Task 5: Generator — weighted sampling and grid assembly

**Files:**
- Modify: `backend/app/puzzle_generator.py`
- Modify: `backend/tests/test_puzzle_generator.py`

Add weighted sampling of 6 qualifiers + 3 imposters, grid-position shuffling, explanation rendering, and the `generate_for_date` function that writes a `Puzzle` + 9 `PuzzleEntry` rows.

- [ ] **Step 5.1: Write the failing test**

Append to `backend/tests/test_puzzle_generator.py`:

```python
from app.puzzle_generator import generate_for_date


async def _seed_viable_mvp_pool(db):
    """Seed 8 qualifiers + 4 imposters for NL MVP, all with All-Star games."""
    qualifiers_data = [
        ("bondsxx01", "Barry Bonds", [1990, 1992, 1993, 2001, 2002, 2003, 2004]),
        ("pujolxx01", "Albert Pujols", [2005, 2008, 2009]),
        ("harpxx01", "Bryce Harper", [2015, 2021]),
        ("goldxx01", "Paul Goldschmidt", [2022]),
        ("freexx01", "Freddie Freeman", [2020]),
        ("acunxx01", "Ronald Acuña Jr.", [2023]),
        ("roseyx01", "Pete Rose", [1973]),
        ("morngxx01", "Joe Morgan", [1975, 1976]),
    ]
    for bbref, name, mvp_years in qualifiers_data:
        p = Player(bbref_id=bbref, name_display=name)
        db.add(p)
        await db.flush()
        for y in mvp_years:
            db.add(
                Award(
                    player_id=p.id,
                    award_type="MVP",
                    year=y,
                    league="NL",
                    notes="winner",
                )
            )
        # Give each ≥3 All-Star appearances
        for y in range(2000, 2003):
            db.add(AllStarAppearance(player_id=p.id, year=y))

    imposters_data = [
        ("jeterxx01", "Derek Jeter", 2006),
        ("gwynnxx01", "Tony Gwynn", 1984),
        ("heltnxx01", "Todd Helton", 2000),
        ("mcgnnxx01", "Don Mattingly", 1986),
    ]
    for bbref, name, year in imposters_data:
        p = Player(bbref_id=bbref, name_display=name)
        db.add(p)
        await db.flush()
        db.add(
            Award(
                player_id=p.id,
                award_type="MVP",
                year=year,
                league="NL",
                notes="top_3",
            )
        )
        for y in range(2000, 2003):
            db.add(AllStarAppearance(player_id=p.id, year=y))

    await db.commit()


@pytest.mark.asyncio
async def test_generate_for_date_writes_puzzle_with_9_entries(db):
    await _seed_viable_mvp_pool(db)

    puzzle = await generate_for_date(db, date(2026, 4, 15))

    assert puzzle is not None
    assert puzzle.puzzle_date == date(2026, 4, 15)
    assert puzzle.published is True
    assert len(puzzle.entries) == 9

    qualifier_entries = [e for e in puzzle.entries if e.is_qualifier]
    imposter_entries = [e for e in puzzle.entries if not e.is_qualifier]
    assert len(qualifier_entries) == 6
    assert len(imposter_entries) == 3

    positions = sorted(e.grid_position for e in puzzle.entries)
    assert positions == list(range(9))

    # Imposter count matches the stored field
    assert puzzle.imposter_count == 3

    # Every entry has a non-empty explanation
    for e in puzzle.entries:
        assert e.explanation and e.explanation.strip()


@pytest.mark.asyncio
async def test_generate_for_date_is_idempotent(db):
    await _seed_viable_mvp_pool(db)

    p1 = await generate_for_date(db, date(2026, 4, 15))
    p2 = await generate_for_date(db, date(2026, 4, 15))

    assert p1 is not None
    assert p2 is None  # Second call sees the existing puzzle and returns None

    count = (
        await db.execute(select(func.count()).select_from(Puzzle))
    ).scalar()
    assert count == 1


@pytest.mark.asyncio
async def test_generate_for_date_same_seed_same_grid(db):
    await _seed_viable_mvp_pool(db)

    p1 = await generate_for_date(db, date(2026, 4, 15))
    assert p1 is not None
    p1_players = sorted(e.player_id for e in p1.entries)

    # Delete and regenerate for the same date — should produce the same grid.
    await db.delete(p1)
    await db.commit()

    p2 = await generate_for_date(db, date(2026, 4, 15))
    assert p2 is not None
    p2_players = sorted(e.player_id for e in p2.entries)
    assert p1_players == p2_players
```

- [ ] **Step 5.2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_puzzle_generator.py -v`
Expected: 3 new tests FAIL — `generate_for_date` not importable.

- [ ] **Step 5.3: Implement weighted sampling, grid writer, and explanation builder**

Append to `backend/app/puzzle_generator.py`:

```python
from app.models import Award, Puzzle, PuzzleEntry, SeasonStat


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
```

- [ ] **Step 5.4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_puzzle_generator.py -v`
Expected: all 5 tests in the file PASS.

- [ ] **Step 5.5: Run the full test suite**

Run: `cd backend && pytest -q`
Expected: all tests pass.

- [ ] **Step 5.6: Commit**

```bash
git add backend/app/puzzle_generator.py backend/tests/test_puzzle_generator.py
git commit -m "feat(generator): weighted sampling + grid assembly + explanations"
```

---

## Task 6: Generator — rotation + guardrail failure

**Files:**
- Modify: `backend/tests/test_puzzle_generator.py`

The pool-viability logic and 14-day rotation already live in `viable_category_pools` (Task 4). This task only adds coverage to lock the behaviors in.

- [ ] **Step 6.1: Write the failing tests**

Append to `backend/tests/test_puzzle_generator.py`:

```python
@pytest.mark.asyncio
async def test_generator_errors_when_no_category_viable(db):
    # DB has nothing — every category has 0 qualifiers.
    with pytest.raises(GeneratorError):
        await generate_for_date(db, date(2026, 4, 15))


@pytest.mark.asyncio
async def test_generator_skips_recently_used_category(db):
    await _seed_viable_mvp_pool(db)

    # Pre-seed a puzzle with category_type "award_mvp_nl" 3 days ago. Since
    # that's the only viable category in the DB, the generator should error
    # (rotation excludes it).
    db.add(
        Puzzle(
            puzzle_date=date(2026, 4, 12),
            category_text="Won NL MVP",
            category_type="award_mvp_nl",
            imposter_count=3,
            difficulty="medium",
            published=True,
        )
    )
    await db.commit()

    with pytest.raises(GeneratorError):
        await generate_for_date(db, date(2026, 4, 15))


@pytest.mark.asyncio
async def test_generator_allows_category_after_rotation_window(db):
    await _seed_viable_mvp_pool(db)

    # Puzzle 30 days ago — outside the 14-day rotation window, so award_mvp_nl
    # is eligible again.
    db.add(
        Puzzle(
            puzzle_date=date(2026, 3, 15),
            category_text="Won NL MVP",
            category_type="award_mvp_nl",
            imposter_count=3,
            difficulty="medium",
            published=True,
        )
    )
    await db.commit()

    puzzle = await generate_for_date(db, date(2026, 4, 15))
    assert puzzle is not None
    assert puzzle.category_type == "award_mvp_nl"
```

- [ ] **Step 6.2: Run tests to verify they pass (behavior is already implemented)**

Run: `cd backend && pytest tests/test_puzzle_generator.py -v`
Expected: all 8 tests in the file PASS. (These tests exercise existing code; if any fail, fix the generator in `backend/app/puzzle_generator.py`.)

- [ ] **Step 6.3: Commit**

```bash
git add backend/tests/test_puzzle_generator.py
git commit -m "test(generator): lock in rotation + guardrail behaviors"
```

---

## Task 7: CLI wrapper

**Files:**
- Create: `backend/scripts/generate_puzzles.py`

The CLI is a thin wrapper around `puzzle_generator.generate_for_date`. Supports `--date`, `--start + --days`, `--days` (defaults to starting tomorrow), and `--dry-run`.

- [ ] **Step 7.1: Write the failing test**

Append to `backend/tests/test_puzzle_generator.py`:

```python
from scripts.generate_puzzles import generate_range


@pytest.mark.asyncio
async def test_generate_range_writes_puzzles_for_each_date(db):
    await _seed_viable_mvp_pool(db)
    # Seed enough other categories via additional pools? Not necessary — rotation
    # inside the 14-day window will force errors. For this test we only cover
    # a single day.
    written = await generate_range(db, date(2026, 4, 15), days=1, dry_run=False)
    assert len(written) == 1
    assert written[0].puzzle_date == date(2026, 4, 15)


@pytest.mark.asyncio
async def test_generate_range_dry_run_writes_nothing(db):
    await _seed_viable_mvp_pool(db)

    written = await generate_range(db, date(2026, 4, 15), days=1, dry_run=True)
    assert len(written) == 1  # the generator returned a Puzzle object

    count = (await db.execute(select(func.count()).select_from(Puzzle))).scalar()
    assert count == 0  # but nothing was committed
```

- [ ] **Step 7.2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_puzzle_generator.py -v -k generate_range`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.generate_puzzles'`.

- [ ] **Step 7.3: Implement the CLI + `generate_range`**

Create `backend/scripts/generate_puzzles.py`:

```python
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

from app.database import SessionLocal, engine, Base
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
            puzzle = await generate_for_date(session, target)
        except GeneratorError as exc:
            print(f"[{target}] ERROR: {exc}")
            raise
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
        start = args.start or (date.today() + timedelta(days=1))
        days = args.days or 1

    async def _run() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with SessionLocal() as session:
            await generate_range(session, start, days, args.dry_run)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
```

- [ ] **Step 7.4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_puzzle_generator.py -v`
Expected: all tests in the file PASS.

- [ ] **Step 7.5: Ruff lint**

Run: `cd backend && ruff check .`
Expected: no errors.

- [ ] **Step 7.6: Commit**

```bash
git add backend/scripts/generate_puzzles.py backend/tests/test_puzzle_generator.py
git commit -m "feat(generator): CLI wrapper with --date / --start / --days / --dry-run"
```

---

## Task 8: End-to-end ingest + generate for the 7-day window

This task is operational, not coded. Ingest Lahman on the local dev DB and generate the 7 target puzzles.

- [ ] **Step 8.1: Re-run ingest with the new share-vote loaders**

Run:

```bash
cd backend
source .venv/bin/activate
python -m scripts.ingest_lahman --zip /mnt/c/Users/noahb/Downloads/lahman_1871-2025_csv.zip
```

Expected: ingest completes, prints counts for people, awards, award shares, manager award shares, all-star, batting, pitching. The share lines should show non-zero inserted counts.

- [ ] **Step 8.2: Dry-run the 7 target puzzles**

Run:

```bash
cd backend
python -m scripts.generate_puzzles --start 2026-04-15 --days 7 --dry-run
```

Expected: 7 dated sections print, each with a category + 9 players (6 ✓ / 3 ✗). No new Puzzle rows land in the DB — confirm with:

```bash
python -c "
import asyncio, sqlite3
c = sqlite3.connect('cutline.db')
print(list(c.execute('SELECT puzzle_date, category_type FROM puzzles ORDER BY puzzle_date')))
"
```

Expected: the same pre-existing rows (2026-04-13, 2026-04-14) — no new dates.

- [ ] **Step 8.3: Sanity-check output**

Skim the dry-run output. Red flags:
- Any player you don't recognize at all in a qualifier slot. (All-Star gate should prevent this, but verify.)
- An imposter that's actually a qualifier (e.g., Alex Rodriguez listed as a "short of 500 HR" imposter).
- Repeat categories within the 7 days.

If any flag triggers, diagnose and fix before Step 8.4.

- [ ] **Step 8.4: Generate for real**

Run:

```bash
cd backend
python -m scripts.generate_puzzles --start 2026-04-15 --days 7
```

Expected: 7 new `Puzzle` rows, all `published=True`, 9 `PuzzleEntry` rows each. Verify:

```bash
python -c "
import sqlite3
c = sqlite3.connect('cutline.db')
for row in c.execute('SELECT puzzle_date, category_type, category_text, published FROM puzzles ORDER BY puzzle_date'):
    print(row)
"
```

Expected output includes rows for 2026-04-15 through 2026-04-21, all `published=1`.

- [ ] **Step 8.5: Smoke-test via API**

Start the backend:

```bash
cd backend && uvicorn app.main:app --reload &
```

Then:

```bash
curl -s http://localhost:8000/api/puzzle/2026-04-15 | python -m json.tool | head -30
```

Expected: a JSON puzzle with `category_text`, `entries` array of 9, each entry with `name_display`. Kill the server when done.

- [ ] **Step 8.6: Commit the generated state**

*Do not commit the SQLite DB.* The DB lives outside git (it's either `cutline.db` in the working directory or a Postgres prod instance). There's nothing code-wise to commit from this task.

If you want a reproducible "generate the week" helper, create `backend/scripts/seed_next_week.sh` (optional, skip if the user hasn't asked for it).

---

## Task 9: Documentation touch-up

**Files:**
- Modify: `backend/CLAUDE.md` (if the project has a backend-scoped file) — skip if only the root `CLAUDE.md` exists.
- Modify: root `CLAUDE.md` → add a bullet under Commands / Data ingestion for `generate_puzzles`.

- [ ] **Step 9.1: Add CLI to root `CLAUDE.md`**

In the existing "Data ingestion" section in `CLAUDE.md`, append a line after the Lahman ingest docs:

```
Once Lahman is ingested, `python -m scripts.generate_puzzles --days 7` automatically produces published puzzles for the next 7 dates (skipping any dates that already have a puzzle). Use `--dry-run` to preview without writing.
```

- [ ] **Step 9.2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document automated puzzle generation CLI"
```

---

## Self-Review

**Spec coverage:**
- Ingest additions → Task 1 ✓
- Stat categories (9 new) → Tasks 2 + 3 ✓
- Generator algorithm (seeded RNG, weighted sampling, grid assembly) → Tasks 4 + 5 ✓
- Guardrails (pool size, 14-day rotation) → Tasks 4 + 6 ✓
- CLI → Task 7 ✓
- Testing → every task has tests ✓
- Rollout → Task 8 ✓

**Placeholder scan:** No TBDs, no "implement later", every step shows actual code or actual commands.

**Type consistency:**
- `AllStarAppearance` is the model name (table: `allstar_appearances`) — used consistently.
- `CandidatePools.allstar_counts: dict[int, int]` — used consistently in generator.
- `_date_seed(target_date)` returns int, used as seed in both `viable_category_pools` call and `random.Random(seed)`.
- `generate_for_date` returns `Puzzle | None` (None when idempotent skip); `generate_range` returns `list[Puzzle]`. Consistent.
- Category keys used in `_award_for_category_key` match the keys registered in `REGISTRY`.
