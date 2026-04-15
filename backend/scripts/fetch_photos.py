"""Populate Player.photo_url for upcoming-puzzle players from Wikipedia.

Uses the MediaWiki REST summary endpoint. Tries the "(baseball)" disambiguated
title first, falls back to the bare name. Accepts a result only when the page
summary looks like a baseball player (keyword check in description/extract).
Stores the thumbnail URL directly — no download.

Usage:
    python -m scripts.fetch_photos                  # players in next 14 days
    python -m scripts.fetch_photos --window 30      # wider window
    python -m scripts.fetch_photos --all-missing    # every null-photo player
    python -m scripts.fetch_photos --dry-run        # don't write
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import date, timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal
from app.models import Player, Puzzle, PuzzleEntry


WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
USER_AGENT = "CutlineBot/1.0 (https://cut-line.com; noah.brown94@gmail.com) httpx"
BASEBALL_HINTS = (
    "baseball",
    "pitcher",
    "outfielder",
    "infielder",
    "shortstop",
    "catcher",
    "first baseman",
    "second baseman",
    "third baseman",
    "designated hitter",
    "mlb",
    "major league",
)

log = logging.getLogger("fetch_photos")


async def _fetch_title(client: httpx.AsyncClient, title: str) -> dict | None:
    url = WIKI_SUMMARY.format(title=title.replace(" ", "_"))
    try:
        resp = await client.get(url, timeout=10.0)
    except httpx.HTTPError as exc:
        log.warning("GET %s failed: %s", url, exc)
        return None
    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        log.warning("GET %s returned %s", url, resp.status_code)
        return None
    return resp.json()


def _looks_like_baseball(summary: dict) -> bool:
    haystack = " ".join(
        (summary.get("description") or "", summary.get("extract") or "")
    ).lower()
    return any(h in haystack for h in BASEBALL_HINTS)


async def _lookup_photo(client: httpx.AsyncClient, name: str) -> str | None:
    for title in (f"{name} (baseball)", name):
        summary = await _fetch_title(client, title)
        if summary is None:
            continue
        # Disambig pages have type "disambiguation" — skip them.
        if summary.get("type") == "disambiguation":
            continue
        if not _looks_like_baseball(summary):
            continue
        thumb = (summary.get("thumbnail") or {}).get("source")
        if thumb:
            return thumb
    return None


async def _players_to_update(
    session: AsyncSession, window_days: int, all_missing: bool
) -> list[Player]:
    if all_missing:
        stmt = select(Player).where(Player.photo_url.is_(None))
        return list((await session.execute(stmt)).scalars().all())

    today = date.today()
    horizon = today + timedelta(days=window_days)
    stmt = (
        select(Player)
        .join(PuzzleEntry, PuzzleEntry.player_id == Player.id)
        .join(Puzzle, Puzzle.id == PuzzleEntry.puzzle_id)
        .where(Puzzle.puzzle_date >= today - timedelta(days=1))
        .where(Puzzle.puzzle_date <= horizon)
        .where(Player.photo_url.is_(None))
        .distinct()
    )
    return list((await session.execute(stmt)).scalars().all())


async def run(window_days: int, all_missing: bool, dry_run: bool) -> None:
    async with SessionLocal() as session:
        players = await _players_to_update(session, window_days, all_missing)
        if not players:
            print("No players need photos.")
            return

        print(f"Looking up photos for {len(players)} player(s)…")
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        hits = 0
        async with httpx.AsyncClient(headers=headers) as client:
            for p in players:
                url = await _lookup_photo(client, p.name_display)
                if url:
                    hits += 1
                    print(f"  ✓ {p.name_display} -> {url}")
                    if not dry_run:
                        p.photo_url = url
                else:
                    print(f"  · {p.name_display} — no match")

        if dry_run:
            await session.rollback()
            print(f"[dry-run] would update {hits} player(s)")
        else:
            await session.commit()
            print(f"Updated {hits} player(s).")


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Fetch missing player photos from Wikipedia.")
    parser.add_argument("--window", type=int, default=14, help="Look ahead this many days of puzzles.")
    parser.add_argument("--all-missing", action="store_true", help="Ignore window; update every null-photo player.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would change without writing.")
    args = parser.parse_args()
    asyncio.run(run(args.window, args.all_missing, args.dry_run))


if __name__ == "__main__":
    main()
