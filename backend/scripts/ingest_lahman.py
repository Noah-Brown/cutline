"""Ingest the Chadwick Bureau (Lahman) baseball database into Cutline's schema.

Supports either a directory of CSVs or a zip archive:
    python -m scripts.ingest_lahman --path /path/to/baseballdatabank/core
    python -m scripts.ingest_lahman --zip  /path/to/baseballdatabank-YYYY.zip

Expected filenames (inside a 'core' folder, or anywhere in the zip):
    People.csv, AwardsPlayers.csv, Batting.csv, Pitching.csv,
    AllstarFull.csv, Appearances.csv

The ingest is idempotent: natural keys prevent duplicate rows on re-run.

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
import io
import zipfile
from pathlib import Path
from typing import Callable, Iterable

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


CsvOpener = Callable[[str], Iterable[dict]]


def _rows_from_dir(root: Path) -> CsvOpener:
    """Return an opener that reads CSVs from a filesystem directory."""

    def _open(name: str) -> Iterable[dict]:
        path = root / name
        if not path.exists():
            # Lahman nests files in a 'core/' subdir depending on the release.
            alt = root / "core" / name
            if alt.exists():
                path = alt
        with path.open(newline="", encoding="utf-8") as f:
            yield from csv.DictReader(f)

    return _open


def _rows_from_zip(zip_path: Path) -> CsvOpener:
    """Return an opener that reads CSVs from within a .zip archive."""
    archive = zipfile.ZipFile(zip_path, "r")
    # Build a filename → member index; match case-insensitively on basename.
    index: dict[str, str] = {}
    for member in archive.namelist():
        if member.endswith("/"):
            continue
        base = member.rsplit("/", 1)[-1]
        index.setdefault(base.lower(), member)

    def _open(name: str) -> Iterable[dict]:
        key = name.lower()
        if key not in index:
            raise FileNotFoundError(f"{name} not found in {zip_path}")
        with archive.open(index[key]) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            yield from csv.DictReader(text)

    return _open


def _int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


async def _load_people(session: AsyncSession, opener: CsvOpener) -> dict[str, int]:
    """Load People.csv → players. Returns bbref_id → player_id."""
    print("  people: People.csv")
    id_map: dict[str, int] = {}
    count = 0
    for row in opener("People.csv"):
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


async def _load_awards(session: AsyncSession, opener: CsvOpener, id_map: dict[str, int]) -> None:
    print("  awards: AwardsPlayers.csv")
    count = 0
    for row in opener("AwardsPlayers.csv"):
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


async def _load_award_shares_common(
    session: AsyncSession,
    opener: CsvOpener,
    id_map: dict[str, int],
    filename: str,
    resolve_award_type: Callable[[dict], str],
    commit_every: int,
    log_label: str,
) -> None:
    """Shared implementation for loading award voting-share CSVs.

    Reads *filename* via *opener*, resolves the award_type for each row via
    *resolve_award_type*, and inserts Award rows tagged top_3 / top_5 based on
    the points_won / points_max ratio.  Commits in batches of *commit_every*.
    """
    print(f"  {log_label}: {filename}")
    count = 0
    for row in opener(filename):
        player_id = id_map.get(row.get("playerID", ""))
        if player_id is None:
            continue

        points_won = _int(row.get("pointsWon")) or 0
        points_max = _int(row.get("pointsMax")) or 0
        if points_won <= 0 or points_max <= 0:
            continue

        award_type = resolve_award_type(row)
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
        if count % commit_every == 0:
            await session.commit()

    await session.commit()
    print(f"  {log_label}: {count} inserted")


async def _load_award_shares(
    session: AsyncSession, opener: CsvOpener, id_map: dict[str, int]
) -> None:
    """Load non-winner voting-share data into Award rows tagged top_3 / top_5.

    The existing `_award_near_misses` imposter query pulls Award rows where
    `notes IS NOT NULL` and != winner. Tagging share-vote recipients with
    top_3/top_5 makes them available as imposter candidates automatically.
    """
    await _load_award_shares_common(
        session=session,
        opener=opener,
        id_map=id_map,
        filename="AwardsSharePlayers.csv",
        resolve_award_type=lambda row: AWARD_NAME_MAP.get(
            row.get("awardID", ""), row.get("awardID", "")
        ),
        commit_every=1000,
        log_label="award shares",
    )


async def _load_award_share_managers(
    session: AsyncSession, opener: CsvOpener, id_map: dict[str, int]
) -> None:
    """Same as `_load_award_shares` but for AwardsShareManagers.csv.

    Managers live in the same People table and share the id_map; award_type
    always maps to 'Manager of the Year'.
    """
    await _load_award_shares_common(
        session=session,
        opener=opener,
        id_map=id_map,
        filename="AwardsShareManagers.csv",
        resolve_award_type=lambda row: "Manager of the Year",
        commit_every=500,
        log_label="manager award shares",
    )


async def _load_allstar(session: AsyncSession, opener: CsvOpener, id_map: dict[str, int]) -> None:
    print("  all-star: AllstarFull.csv")
    count = 0
    for row in opener("AllstarFull.csv"):
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


async def _load_batting(session: AsyncSession, opener: CsvOpener, id_map: dict[str, int]) -> None:
    print("  batting: Batting.csv")
    count = 0
    for row in opener("Batting.csv"):
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


async def _load_pitching(session: AsyncSession, opener: CsvOpener, id_map: dict[str, int]) -> None:
    """Update existing season_stats rows (from batting) with pitching numbers."""
    print("  pitching: Pitching.csv")
    updated = 0
    for row in opener("Pitching.csv"):
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Lahman CSVs into Cutline.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--path",
        type=Path,
        help="Path to the baseballdatabank directory (CSVs or a 'core/' subdir)",
    )
    group.add_argument(
        "--zip",
        dest="zip_path",
        type=Path,
        help="Path to a baseballdatabank .zip archive",
    )
    args = parser.parse_args()

    if args.path is not None:
        if not args.path.is_dir():
            raise SystemExit(f"Not a directory: {args.path}")
        opener = _rows_from_dir(args.path)
    else:
        if not args.zip_path.is_file():
            raise SystemExit(f"Not a file: {args.zip_path}")
        opener = _rows_from_zip(args.zip_path)

    asyncio.run(ingest(opener))


if __name__ == "__main__":
    main()
