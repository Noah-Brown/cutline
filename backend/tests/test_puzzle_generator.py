"""Tests for the puzzle generator engine."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.models import AllStarAppearance, Award, Player, Puzzle
from app.puzzle_generator import GeneratorError, allstar_gate, viable_category_pools
from app.puzzle_generator import generate_for_date


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

    from sqlalchemy import func
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
