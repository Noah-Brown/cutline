"""Ingest the Chadwick Bureau (Lahman) baseball database into Cutline's schema.

Expected layout (clone https://github.com/chadwickbureau/baseballdatabank):
    <path>/People.csv
    <path>/AwardsPlayers.csv
    <path>/Batting.csv
    <path>/Pitching.csv
    <path>/AllstarFull.csv
    <path>/Appearances.csv

Usage:
    python -m scripts.ingest_lahman --path /path/to/baseballdatabank/core

The ingest is designed to be idempotent: re-running it skips rows already
loaded via their natural keys.

NOTE: Lahman records award *winners* only. To support the imposter-pool
queries (near-miss candidates), load supplemental voting-result data
(e.g. Baseball Reference top-3 finishers) into the `awards` table with
``notes IN ('runner_up', 'top_3', 'top_5')``. The category registry uses
those notes to identify trap candidates.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal, engine, Base
from app.models import (
    AllStarAppearance,
    Award,
    Player,
    PlayerTeam,
    SeasonStat,
)


# Map Lahman's verbose award names to our internal award_type values.
AWARD_NAME_MAP: dict[str, str] = {
    "Most Valuable Player": "MVP",
    "Cy Young Award": "Cy Young",
    "Rookie of the Year": "Rookie of the Year",
    "Gold Glove": "Gold Glove",
    "Silver Slugger": "Silver Slugger",
    "World Series MVP": "World Series MVP",
    "ALCS MVP": "ALCS MVP",
    "NLCS MVP": "NLCS MVP",
    "All-Star Game MVP": "All-Star Game MVP",
    "Rolaids Relief Man Award": "Reliever of the Year",
    "Reliever of the Year Award": "Reliever of the Year",
    "Hank Aaron Award": "Hank Aaron Award",
    "BBWAA Manager of the Year": "Manager of the Year",
    "TSN Manager of the Year": "Manager of the Year",
}


def _rows(path: Path) -> Iterable[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        yield from csv.DictReader(f)


def _int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


async def _load_people(session: AsyncSession, src: Path) -> dict[str, int]:
    """Load People.csv → players. Returns bbref_id → player_id."""
    print(f"  people: {src}")
    id_map: dict[str, int] = {}
    count = 0
    for row in _rows(src):
        bbref_id = row.get("bbrefID") or row.get("playerID")
        if not bbref_id:
            continue

        existing = (
            await session.execute(select(Player).where(Player.bbref_id == bbref_id))
        ).scalar_one_or_none()

        first = row.get("nameFirst") or ""
        last = row.get("nameLast") or ""
        display = f"{first} {last}".strip() or bbref_id

        if existing is None:
            final_year = _int(row.get("finalGame", "")[:4] if row.get("finalGame") else None)
            debut_year = _int(row.get("debut", "")[:4] if row.get("debut") else None)
            player = Player(
                bbref_id=bbref_id,
                name_display=display,
                name_first=first or None,
                name_last=last or None,
                debut_year=debut_year,
                final_year=final_year,
                is_active=final_year is None,
            )
            session.add(player)
            await session.flush()
            id_map[bbref_id] = player.id
        else:
            id_map[bbref_id] = existing.id

        count += 1
        if count % 2000 == 0:
            await session.commit()
            print(f"    ...{count} people")

    await session.commit()
    print(f"  people: {count} rows processed")
    return id_map


async def _load_awards(session: AsyncSession, src: Path, id_map: dict[str, int]) -> None:
    print(f"  awards: {src}")
    count = 0
    for row in _rows(src):
        player_id = id_map.get(row["playerID"])
        if player_id is None:
            continue
        raw_name = row["awardID"]
        award_type = AWARD_NAME_MAP.get(raw_name, raw_name)
        year = _int(row["yearID"])
        if year is None:
            continue
        league = row.get("lgID") or None
        if league in ("", "ML"):
            league = None

        existing = (
            await session.execute(
                select(Award.id).where(
                    Award.player_id == player_id,
                    Award.award_type == award_type,
                    Award.year == year,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue

        session.add(
            Award(
                player_id=player_id,
                award_type=award_type,
                year=year,
                league=league,
                team=None,
                notes="winner",
            )
        )
        count += 1
        if count % 1000 == 0:
            await session.commit()
    await session.commit()
    print(f"  awards: {count} inserted")


async def _load_allstar(session: AsyncSession, src: Path, id_map: dict[str, int]) -> None:
    print(f"  all-star: {src}")
    count = 0
    for row in _rows(src):
        player_id = id_map.get(row["playerID"])
        if player_id is None:
            continue
        year = _int(row["yearID"])
        if year is None:
            continue

        existing = (
            await session.execute(
                select(AllStarAppearance.id).where(
                    AllStarAppearance.player_id == player_id,
                    AllStarAppearance.year == year,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue

        session.add(
            AllStarAppearance(
                player_id=player_id,
                year=year,
                team=row.get("teamID") or None,
                league=row.get("lgID") or None,
            )
        )
        count += 1
        if count % 1000 == 0:
            await session.commit()
    await session.commit()
    print(f"  all-star: {count} inserted")


async def _load_batting(session: AsyncSession, src: Path, id_map: dict[str, int]) -> None:
    print(f"  batting: {src}")
    count = 0
    for row in _rows(src):
        player_id = id_map.get(row["playerID"])
        if player_id is None:
            continue
        year = _int(row["yearID"])
        if year is None:
            continue
        team = row.get("teamID") or None

        existing = (
            await session.execute(
                select(SeasonStat.id).where(
                    SeasonStat.player_id == player_id,
                    SeasonStat.year == year,
                    SeasonStat.team == team,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue

        ab = _int(row.get("AB")) or 0
        hits = _int(row.get("H")) or 0
        avg = round(hits / ab, 3) if ab else None

        session.add(
            SeasonStat(
                player_id=player_id,
                year=year,
                team=team,
                league=row.get("lgID") or None,
                games=_int(row.get("G")),
                batting_avg=avg,
                home_runs=_int(row.get("HR")),
                rbi=_int(row.get("RBI")),
                hits=hits or None,
                stolen_bases=_int(row.get("SB")),
            )
        )

        # Mirror team history row
        if team:
            session.add(
                PlayerTeam(
                    player_id=player_id,
                    year=year,
                    team=team,
                    league=row.get("lgID") or None,
                )
            )

        count += 1
        if count % 2000 == 0:
            await session.commit()
    await session.commit()
    print(f"  batting: {count} inserted")


async def _load_pitching(session: AsyncSession, src: Path, id_map: dict[str, int]) -> None:
    """Update existing season_stats rows (from batting) with pitching numbers."""
    print(f"  pitching: {src}")
    updated = 0
    for row in _rows(src):
        player_id = id_map.get(row["playerID"])
        if player_id is None:
            continue
        year = _int(row["yearID"])
        if year is None:
            continue
        team = row.get("teamID") or None

        season = (
            await session.execute(
                select(SeasonStat).where(
                    SeasonStat.player_id == player_id,
                    SeasonStat.year == year,
                    SeasonStat.team == team,
                )
            )
        ).scalar_one_or_none()

        if season is None:
            season = SeasonStat(player_id=player_id, year=year, team=team)
            session.add(season)
            await session.flush()

        season.wins = _int(row.get("W"))
        season.losses = _int(row.get("L"))
        season.strikeouts = _int(row.get("SO"))
        season.saves = _int(row.get("SV"))
        era_raw = row.get("ERA")
        season.era = float(era_raw) if era_raw not in (None, "") else None
        ipouts = _int(row.get("IPouts"))
        if ipouts is not None:
            season.innings_pitched = round(ipouts / 3, 1)

        updated += 1
        if updated % 2000 == 0:
            await session.commit()
    await session.commit()
    print(f"  pitching: {updated} updated")


async def ingest(path: Path) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        id_map = await _load_people(session, path / "People.csv")
        await _load_awards(session, path / "AwardsPlayers.csv", id_map)
        await _load_allstar(session, path / "AllstarFull.csv", id_map)
        await _load_batting(session, path / "Batting.csv", id_map)
        await _load_pitching(session, path / "Pitching.csv", id_map)
    print("Ingest complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Lahman CSVs into Cutline.")
    parser.add_argument(
        "--path",
        type=Path,
        required=True,
        help="Path to the baseballdatabank/core directory",
    )
    args = parser.parse_args()
    if not args.path.is_dir():
        raise SystemExit(f"Not a directory: {args.path}")
    asyncio.run(ingest(args.path))


if __name__ == "__main__":
    main()
