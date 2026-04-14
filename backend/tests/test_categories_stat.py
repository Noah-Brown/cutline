"""Tests for stat-milestone categories."""

from __future__ import annotations

import pytest

from app.categories import REGISTRY
from app.models import AllStarAppearance, Player, SeasonStat


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


async def _add_player_with_hits(db, bbref: str, name: str, hit_totals: list[int]) -> Player:
    p = Player(bbref_id=bbref, name_display=name)
    db.add(p)
    await db.flush()
    for i, h in enumerate(hit_totals):
        db.add(
            SeasonStat(player_id=p.id, year=2000 + i, team="NYY", hits=h)
        )
    await db.commit()
    return p


@pytest.mark.asyncio
async def test_stat_3000_hits_boundaries(db):
    # 3,200 career hits (16 × 200) → qualifier
    above = await _add_player_with_hits(db, "hit3200x01", "Over Three K", [200] * 16)
    # Exactly 3,000 → qualifier
    at = await _add_player_with_hits(db, "hit3000x01", "Exact Three K", [200] * 15)
    # 2,700 (13.5 × 200 ≈ 2,700) → imposter (in 2500-2999 band)
    near = await _add_player_with_hits(db, "hit2700x01", "Near Three K", [180] * 15)
    # 1,500 hits → neither
    low = await _add_player_with_hits(db, "hit1500x01", "Low Hits", [100] * 15)

    category = REGISTRY["stat_3000_hits"]
    qualifiers = await category.qualifier_fn(db)
    imposters = await category.imposter_fn(db)

    q_ids = {p.id for p in qualifiers}
    i_ids = {p.id for p in imposters}

    assert above.id in q_ids
    assert at.id in q_ids
    assert near.id in i_ids
    assert low.id not in q_ids and low.id not in i_ids


@pytest.mark.asyncio
async def test_all_career_stat_categories_registered(db):
    for key in ("stat_500_hr", "stat_3000_hits", "stat_300_wins", "stat_3000_k", "stat_400_sb"):
        assert key in REGISTRY, f"{key} not in REGISTRY"


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
