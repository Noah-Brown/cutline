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
