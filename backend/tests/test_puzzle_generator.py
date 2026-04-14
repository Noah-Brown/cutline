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
