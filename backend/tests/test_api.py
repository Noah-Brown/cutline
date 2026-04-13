"""End-to-end HTTP tests for the puzzle + admin API."""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"


async def test_get_today_returns_puzzle(client, seeded_puzzle):
    r = await client.get("/api/puzzle/today")
    assert r.status_code == 200
    body = r.json()
    assert body["puzzle_id"] == seeded_puzzle["puzzle_id"]
    assert body["category"] == "Won NL MVP"
    assert len(body["players"]) == 9
    assert {p["grid_position"] for p in body["players"]} == set(range(9))
    # No answer leakage: the public puzzle response must not reveal is_qualifier
    assert all("is_qualifier" not in p for p in body["players"])


async def test_submit_perfect_score(client, seeded_puzzle):
    r = await client.post(
        "/api/puzzle/submit",
        json={
            "puzzle_id": seeded_puzzle["puzzle_id"],
            "session_id": "sess-perfect",
            "selections": sorted(seeded_puzzle["qualifier_positions"]),
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["score"] == 6
    assert body["max_score"] == 6
    assert body["perfect"] is True
    assert len(body["results"]) == 9
    assert "Score: 6/6" in body["share_text"]
    assert "Cutline" in body["share_text"]


async def test_submit_mixed_scoring(client, seeded_puzzle):
    # 4 correct + 1 FP + 2 missed
    selections = [0, 1, 3, 4, 2]  # 4 qualifiers + 1 imposter
    r = await client.post(
        "/api/puzzle/submit",
        json={
            "puzzle_id": seeded_puzzle["puzzle_id"],
            "session_id": "sess-mix",
            "selections": selections,
        },
    )
    assert r.status_code == 200
    body = r.json()
    # +4 correct - 1 FP - 2 missed (6 qualifiers, 4 selected) = +1
    assert body["score"] == 1
    assert body["max_score"] == 6
    assert body["perfect"] is False


async def test_submit_duplicate_rejected(client, seeded_puzzle):
    payload = {
        "puzzle_id": seeded_puzzle["puzzle_id"],
        "session_id": "sess-dup",
        "selections": [0],
    }
    r1 = await client.post("/api/puzzle/submit", json=payload)
    assert r1.status_code == 200
    r2 = await client.post("/api/puzzle/submit", json=payload)
    assert r2.status_code == 409


async def test_submit_rejects_invalid_positions(client, seeded_puzzle):
    r = await client.post(
        "/api/puzzle/submit",
        json={
            "puzzle_id": seeded_puzzle["puzzle_id"],
            "session_id": "sess-bad",
            "selections": [0, 42],
        },
    )
    assert r.status_code == 422


async def test_archive_fetch_by_date(client, seeded_puzzle):
    r = await client.get(f"/api/puzzle/{seeded_puzzle['puzzle_date'].isoformat()}")
    assert r.status_code == 200
    body = r.json()
    assert body["puzzle_id"] == seeded_puzzle["puzzle_id"]


async def test_archive_404_when_missing(client):
    r = await client.get("/api/puzzle/1999-01-01")
    assert r.status_code == 404


async def test_stats_after_submission(client, seeded_puzzle):
    await client.post(
        "/api/puzzle/submit",
        json={
            "puzzle_id": seeded_puzzle["puzzle_id"],
            "session_id": "stats-sess",
            "selections": sorted(seeded_puzzle["qualifier_positions"]),
        },
    )
    r = await client.get(f"/api/puzzle/stats?puzzle_id={seeded_puzzle['puzzle_id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["submissions"] == 1
    assert body["perfect_count"] == 1


async def test_admin_requires_token(client):
    r = await client.get("/api/admin/categories")
    assert r.status_code == 401


async def test_admin_categories_ok_with_token(client):
    r = await client.get(
        "/api/admin/categories", headers={"Authorization": "Bearer dev-admin-token"}
    )
    assert r.status_code == 200
    body = r.json()
    assert any(c["key"] == "award_mvp_nl" for c in body)


async def test_streak_with_single_play(client, seeded_puzzle):
    await client.post(
        "/api/puzzle/submit",
        json={
            "puzzle_id": seeded_puzzle["puzzle_id"],
            "session_id": "streaker",
            "selections": [0],
        },
    )
    r = await client.get("/api/puzzle/streak?session_id=streaker")
    assert r.status_code == 200
    body = r.json()
    assert body["longest_streak"] == 1
    assert body["current_streak"] in (0, 1)  # depends on today's date vs puzzle_date
