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
