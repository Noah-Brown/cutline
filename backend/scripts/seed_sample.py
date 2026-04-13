"""Seed a single hand-curated puzzle so the game is playable out of the box.

Usage:
    python -m scripts.seed_sample

Creates:
  - A set of real MLB players (with supplemental award entries)
  - One published puzzle dated today: "Won NL MVP"
    * 6 qualifiers (real NL MVP winners)
    * 3 imposters (plausible traps)

This mirrors what a curator would produce via the admin API.
"""

from __future__ import annotations

import asyncio
from datetime import date, timezone, datetime, timedelta

from sqlalchemy import select

from app.database import SessionLocal, engine, Base
from app.models import Award, Player, Puzzle, PuzzleEntry


SAMPLE_PLAYERS: list[dict] = [
    # NL MVP winners (qualifiers)
    {"bbref_id": "bondsba01", "name_display": "Barry Bonds", "debut_year": 1986, "final_year": 2007, "primary_position": "OF",
     "mvp_years": [("1990", "NL"), ("1992", "NL"), ("1993", "NL"), ("2001", "NL"), ("2002", "NL"), ("2003", "NL"), ("2004", "NL")]},
    {"bbref_id": "pujolal01", "name_display": "Albert Pujols", "debut_year": 2001, "final_year": 2022, "primary_position": "1B",
     "mvp_years": [("2005", "NL"), ("2008", "NL"), ("2009", "NL")]},
    {"bbref_id": "harpebr03", "name_display": "Bryce Harper", "debut_year": 2012, "final_year": None, "primary_position": "OF",
     "mvp_years": [("2015", "NL"), ("2021", "NL")]},
    {"bbref_id": "goldspa01", "name_display": "Paul Goldschmidt", "debut_year": 2011, "final_year": None, "primary_position": "1B",
     "mvp_years": [("2022", "NL")]},
    {"bbref_id": "freemfr01", "name_display": "Freddie Freeman", "debut_year": 2010, "final_year": None, "primary_position": "1B",
     "mvp_years": [("2020", "NL")]},
    {"bbref_id": "acunaro01", "name_display": "Ronald Acuña Jr.", "debut_year": 2018, "final_year": None, "primary_position": "OF",
     "mvp_years": [("2023", "NL")]},
    # Imposters (near-misses / wrong-league / halo)
    {"bbref_id": "jeterde01", "name_display": "Derek Jeter", "debut_year": 1995, "final_year": 2014, "primary_position": "SS",
     "near_misses": [("MVP", "2006", "AL", "runner_up")]},
    {"bbref_id": "gwynnto01", "name_display": "Tony Gwynn", "debut_year": 1982, "final_year": 2001, "primary_position": "OF",
     "near_misses": [("MVP", "1984", "NL", "top_5")]},
    {"bbref_id": "helkoto01", "name_display": "Todd Helton", "debut_year": 1997, "final_year": 2013, "primary_position": "1B",
     "near_misses": [("MVP", "2000", "NL", "top_5")]},
]


PUZZLE_ENTRIES = [
    # grid_position, bbref_id, is_qualifier, explanation
    (0, "bondsba01", True, "Won NL MVP 7× (1990, 1992, 1993, 2001–2004)."),
    (1, "pujolal01", True, "Won NL MVP three times with the Cardinals (2005, 2008, 2009)."),
    (2, "jeterde01", False, "AL player — finished 2nd in AL MVP voting in 2006. Never won."),
    (3, "harpebr03", True, "Unanimous NL MVP in 2015; won again in 2021 with Philadelphia."),
    (4, "goldspa01", True, "Won NL MVP in 2022 with St. Louis."),
    (5, "gwynnto01", False, "8× batting champion; his best MVP finish was 3rd in 1984 — never won."),
    (6, "freemfr01", True, "Won NL MVP in the shortened 2020 season with Atlanta."),
    (7, "helkoto01", False, "Career .316 hitter and 2000 batting champ; finished 5th in MVP voting that year. Never won."),
    (8, "acunaro01", True, "Unanimous NL MVP in 2023 on his 40/70 season."),
]


async def seed() -> None:
    # Make sure tables exist (covers the case where alembic wasn't run).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        # Upsert players
        by_bbref: dict[str, Player] = {}
        for p in SAMPLE_PLAYERS:
            existing = (
                await session.execute(select(Player).where(Player.bbref_id == p["bbref_id"]))
            ).scalar_one_or_none()
            if existing is None:
                existing = Player(
                    bbref_id=p["bbref_id"],
                    name_display=p["name_display"],
                    debut_year=p["debut_year"],
                    final_year=p["final_year"],
                    primary_position=p.get("primary_position"),
                    is_active=p.get("final_year") is None,
                )
                session.add(existing)
                await session.flush()
            by_bbref[p["bbref_id"]] = existing

            # Winning awards
            for year, league in p.get("mvp_years", []):
                exists = (
                    await session.execute(
                        select(Award).where(
                            Award.player_id == existing.id,
                            Award.award_type == "MVP",
                            Award.year == int(year),
                        )
                    )
                ).scalar_one_or_none()
                if exists is None:
                    session.add(
                        Award(
                            player_id=existing.id,
                            award_type="MVP",
                            year=int(year),
                            league=league,
                            notes="winner",
                        )
                    )

            # Near-misses (supplemental data for imposter generation)
            for award_type, year, league, tag in p.get("near_misses", []):
                exists = (
                    await session.execute(
                        select(Award).where(
                            Award.player_id == existing.id,
                            Award.award_type == award_type,
                            Award.year == int(year),
                        )
                    )
                ).scalar_one_or_none()
                if exists is None:
                    session.add(
                        Award(
                            player_id=existing.id,
                            award_type=award_type,
                            year=int(year),
                            league=league,
                            notes=tag,
                        )
                    )

        await session.flush()

        # Create today's puzzle (idempotent)
        today = (datetime.now(timezone.utc) - timedelta(hours=4)).date()
        existing_puzzle = (
            await session.execute(select(Puzzle).where(Puzzle.puzzle_date == today))
        ).scalar_one_or_none()
        if existing_puzzle is not None:
            print(f"Puzzle for {today} already exists (id={existing_puzzle.id}); skipping.")
            await session.commit()
            return

        imposter_count = sum(1 for _, _, q, _ in PUZZLE_ENTRIES if not q)
        puzzle = Puzzle(
            puzzle_date=today,
            category_text="Won NL MVP",
            category_type="award_mvp_nl",
            imposter_count=imposter_count,
            difficulty="medium",
            published=True,
        )
        session.add(puzzle)
        await session.flush()

        for grid_position, bbref_id, is_qualifier, explanation in PUZZLE_ENTRIES:
            player = by_bbref[bbref_id]
            session.add(
                PuzzleEntry(
                    puzzle_id=puzzle.id,
                    player_id=player.id,
                    grid_position=grid_position,
                    is_qualifier=is_qualifier,
                    explanation=explanation,
                )
            )

        await session.commit()
        print(f"Seeded puzzle id={puzzle.id} date={today} — 'Won NL MVP'")


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
