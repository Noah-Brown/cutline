"""End-to-end HTTP tests for the puzzle + admin API (tri-state scoring)."""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


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
            "marks": {
                "yes": sorted(seeded_puzzle["qualifier_positions"]),
                "no": sorted(seeded_puzzle["imposter_positions"]),
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["score"] == 9
    assert body["max_score"] == 9
    assert body["perfect"] is True
    assert len(body["results"]) == 9
    assert "Score: 9/9" in body["share_text"]
    assert "Cutline" in body["share_text"]


async def test_submit_mixed_scoring(client, seeded_puzzle):
    # YES on 4 qualifiers + 1 imposter; NO on 1 qualifier; others blank
    r = await client.post(
        "/api/puzzle/submit",
        json={
            "puzzle_id": seeded_puzzle["puzzle_id"],
            "session_id": "sess-mix",
            "marks": {"yes": [0, 1, 3, 4, 2], "no": [8]},
        },
    )
    assert r.status_code == 200
    body = r.json()
    # 4 correct YES + 0 (FP) + 0 (wrong reject) = 4
    assert body["score"] == 4
    assert body["max_score"] == 9
    assert body["perfect"] is False

    # Sanity: confirm the per-entry result kinds
    kinds = {r["grid_position"]: r["result"] for r in body["results"]}
    assert kinds[0] == "correct"
    assert kinds[2] == "false_positive"
    assert kinds[8] == "wrong_reject"
    assert kinds[5] == "unanswered"


async def test_submit_blank_scores_zero(client, seeded_puzzle):
    r = await client.post(
        "/api/puzzle/submit",
        json={
            "puzzle_id": seeded_puzzle["puzzle_id"],
            "session_id": "sess-blank",
            "marks": {"yes": [], "no": []},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["score"] == 0
    assert body["max_score"] == 9


async def test_submit_duplicate_rejected(client, seeded_puzzle):
    payload = {
        "puzzle_id": seeded_puzzle["puzzle_id"],
        "session_id": "sess-dup",
        "marks": {"yes": [0], "no": []},
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
            "marks": {"yes": [0, 42], "no": []},
        },
    )
    assert r.status_code == 422


async def test_submit_rejects_yes_and_no_overlap(client, seeded_puzzle):
    r = await client.post(
        "/api/puzzle/submit",
        json={
            "puzzle_id": seeded_puzzle["puzzle_id"],
            "session_id": "sess-overlap",
            "marks": {"yes": [0, 1], "no": [1, 2]},
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


async def test_archive_hides_future_puzzles(client, seeded_puzzle):
    # Even if a puzzle is staged + published for a future date, the public
    # archive endpoint must not leak it. Admin preview is the allowed path.
    from datetime import timedelta

    from app.database import SessionLocal
    from app.models import Player, Puzzle, PuzzleEntry

    future = seeded_puzzle["puzzle_date"] + timedelta(days=1)
    async with SessionLocal() as s:
        p = Player(bbref_id="future01", name_display="Future Player")
        s.add(p)
        await s.flush()
        puz = Puzzle(
            puzzle_date=future,
            category_text="Future Category",
            category_type="test",
            imposter_count=2,
            published=True,
        )
        s.add(puz)
        await s.flush()
        s.add(
            PuzzleEntry(
                puzzle_id=puz.id,
                player_id=p.id,
                grid_position=0,
                is_qualifier=True,
                explanation="x",
            )
        )
        await s.commit()

    r = await client.get(f"/api/puzzle/{future.isoformat()}")
    assert r.status_code == 404


async def test_stats_after_submission(client, seeded_puzzle):
    await client.post(
        "/api/puzzle/submit",
        json={
            "puzzle_id": seeded_puzzle["puzzle_id"],
            "session_id": "stats-sess",
            "marks": {
                "yes": sorted(seeded_puzzle["qualifier_positions"]),
                "no": sorted(seeded_puzzle["imposter_positions"]),
            },
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


async def test_admin_set_photo_url_via_patch(client, seeded_puzzle):
    # Grab a real player_id from the seeded puzzle via the public response.
    puzzle = (await client.get("/api/puzzle/today")).json()
    player_id = puzzle["players"][0]["player_id"]

    r = await client.patch(
        f"/api/admin/players/{player_id}",
        headers={"Authorization": "Bearer dev-admin-token"},
        json={"photo_url": "https://example.com/headshot.jpg"},
    )
    assert r.status_code == 200
    assert r.json()["photo_url"] == "https://example.com/headshot.jpg"

    # It should now come back in the public puzzle response.
    refreshed = (await client.get("/api/puzzle/today")).json()
    target = next(p for p in refreshed["players"] if p["player_id"] == player_id)
    assert target["photo_url"] == "https://example.com/headshot.jpg"


async def test_admin_upload_photo(client, seeded_puzzle, photo_dir):
    puzzle = (await client.get("/api/puzzle/today")).json()
    player_id = puzzle["players"][0]["player_id"]

    # Minimal valid 1x1 PNG
    png_bytes = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
    )

    r = await client.post(
        f"/api/admin/players/{player_id}/photo",
        headers={"Authorization": "Bearer dev-admin-token"},
        files={"file": ("headshot.png", png_bytes, "image/png")},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["player_id"] == player_id
    assert body["photo_url"].endswith(f"/{player_id}.png")

    # File persisted to the test-scoped photo dir
    files = list(photo_dir.glob(f"{player_id}.*"))
    assert len(files) == 1
    assert files[0].read_bytes() == png_bytes

    # And the URL now shows up on the public puzzle
    refreshed = (await client.get("/api/puzzle/today")).json()
    target = next(p for p in refreshed["players"] if p["player_id"] == player_id)
    assert target["photo_url"] == body["photo_url"]


async def test_admin_upload_rejects_non_image(client, seeded_puzzle):
    puzzle = (await client.get("/api/puzzle/today")).json()
    player_id = puzzle["players"][0]["player_id"]

    r = await client.post(
        f"/api/admin/players/{player_id}/photo",
        headers={"Authorization": "Bearer dev-admin-token"},
        files={"file": ("bogus.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400


async def test_streak_with_single_play(client, seeded_puzzle):
    await client.post(
        "/api/puzzle/submit",
        json={
            "puzzle_id": seeded_puzzle["puzzle_id"],
            "session_id": "streaker",
            "marks": {"yes": [0], "no": []},
        },
    )
    r = await client.get("/api/puzzle/streak?session_id=streaker")
    assert r.status_code == 200
    body = r.json()
    assert body["longest_streak"] == 1
    assert body["current_streak"] in (0, 1)
