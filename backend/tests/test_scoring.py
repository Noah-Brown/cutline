"""Unit tests for the scoring engine and share-grid renderer."""

from __future__ import annotations

from app.scoring import (
    EntryOutcome,
    ResultKind,
    render_share_grid,
    render_share_text,
    score_submission,
)


# A small sample grid: 6 qualifiers + 3 imposters (matches the seed puzzle shape).
SAMPLE_ENTRIES: list[tuple[int, bool]] = [
    (0, True),   # Bonds
    (1, True),   # Pujols
    (2, False),  # Jeter (imposter)
    (3, True),   # Harper
    (4, True),   # Goldschmidt
    (5, False),  # Gwynn (imposter)
    (6, True),   # Freeman
    (7, False),  # Helton (imposter)
    (8, True),   # Acuña
]

QUALIFIER_POSITIONS = {0, 1, 3, 4, 6, 8}
IMPOSTER_POSITIONS = {2, 5, 7}


def test_perfect_score_hits_all_qualifiers_only() -> None:
    result = score_submission(SAMPLE_ENTRIES, QUALIFIER_POSITIONS)
    assert result.score == 6
    assert result.max_score == 6
    assert result.perfect is True
    for o in result.outcomes:
        if o.is_qualifier:
            assert o.result is ResultKind.CORRECT
        else:
            assert o.result is ResultKind.CORRECT_AVOID


def test_worst_case_all_imposters_no_qualifiers() -> None:
    result = score_submission(SAMPLE_ENTRIES, IMPOSTER_POSITIONS)
    # 3 false positives (-3) + 6 missed qualifiers (-6) = -9
    assert result.score == -9
    assert result.max_score == 6
    assert result.perfect is False


def test_mixed_submission_scoring() -> None:
    # Select 5 qualifiers + 1 imposter, miss 1 qualifier
    selections = {0, 1, 3, 4, 6, 2}  # 5 correct + 1 FP; pos 8 missed
    result = score_submission(SAMPLE_ENTRIES, selections)
    # +5 correct, -1 FP, -1 missed = 3
    assert result.score == 3
    assert result.max_score == 6
    assert result.perfect is False

    kinds_by_pos = {o.grid_position: o.result for o in result.outcomes}
    assert kinds_by_pos[0] is ResultKind.CORRECT
    assert kinds_by_pos[2] is ResultKind.FALSE_POSITIVE
    assert kinds_by_pos[8] is ResultKind.MISSED
    assert kinds_by_pos[5] is ResultKind.CORRECT_AVOID


def test_no_selections_scores_minus_qualifiers() -> None:
    result = score_submission(SAMPLE_ENTRIES, set())
    assert result.score == -6
    assert result.max_score == 6


def test_share_grid_shape_and_symbols() -> None:
    outcomes = [
        EntryOutcome(grid_position=i, is_qualifier=True, was_selected=True, result=ResultKind.CORRECT)
        for i in range(9)
    ]
    grid = render_share_grid(outcomes)
    assert grid.count("\n") == 2  # three rows
    assert grid.replace("\n", "") == "🟩" * 9


def test_share_grid_mixed_symbols() -> None:
    # Ordering matches spec's sample share:
    #   🟩🟩🟩
    #   🟩🔴🟩
    #   🟩🟩🟨
    outcomes = [
        EntryOutcome(0, True, True, ResultKind.CORRECT),
        EntryOutcome(1, True, True, ResultKind.CORRECT),
        EntryOutcome(2, True, True, ResultKind.CORRECT),
        EntryOutcome(3, True, True, ResultKind.CORRECT),
        EntryOutcome(4, False, True, ResultKind.FALSE_POSITIVE),
        EntryOutcome(5, True, True, ResultKind.CORRECT),
        EntryOutcome(6, True, True, ResultKind.CORRECT),
        EntryOutcome(7, True, True, ResultKind.CORRECT),
        EntryOutcome(8, True, False, ResultKind.MISSED),
    ]
    grid = render_share_grid(outcomes)
    assert grid.splitlines() == ["🟩🟩🟩", "🟩🔴🟩", "🟩🟩🟨"]


def test_share_text_format() -> None:
    outcomes = [
        EntryOutcome(i, True, True, ResultKind.CORRECT) for i in range(9)
    ]
    text = render_share_text(
        game_name="Cutline",
        puzzle_number=42,
        category_text="Won NL MVP",
        outcomes=outcomes,
        score=9,
        max_score=9,
    )
    lines = text.splitlines()
    assert lines[0].startswith("⚾ Cutline #42 — ")
    assert '"Won NL MVP"' in lines[0]
    assert lines[-1] == "Score: 9/9"
