"""Unit tests for the tri-state scoring engine and share-grid renderer."""

from __future__ import annotations

from app.scoring import (
    EntryOutcome,
    Mark,
    ResultKind,
    render_share_grid,
    render_share_text,
    score_submission,
)


# 6 qualifiers + 3 imposters (matches the seed puzzle shape).
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

QUALIFIERS = {0, 1, 3, 4, 6, 8}
IMPOSTERS = {2, 5, 7}


def _marks(*, yes: set[int] = frozenset(), no: set[int] = frozenset()) -> dict[int, Mark]:
    m: dict[int, Mark] = {}
    for p in yes:
        m[p] = Mark.YES
    for p in no:
        m[p] = Mark.NO
    return m


def test_all_blanks_scores_zero() -> None:
    result = score_submission(SAMPLE_ENTRIES, {})
    assert result.score == 0
    assert result.max_score == 9
    assert all(o.result is ResultKind.UNANSWERED for o in result.outcomes)


def test_perfect_requires_yes_on_qualifiers_and_no_on_imposters() -> None:
    marks = _marks(yes=QUALIFIERS, no=IMPOSTERS)
    result = score_submission(SAMPLE_ENTRIES, marks)
    assert result.score == 9
    assert result.max_score == 9
    assert result.perfect is True
    kinds = {o.result for o in result.outcomes}
    assert kinds == {ResultKind.CORRECT, ResultKind.CORRECT_REJECT}


def test_worst_case_inverted_scores_zero() -> None:
    # YES on every imposter, NO on every qualifier — every call wrong, no points.
    marks = _marks(yes=IMPOSTERS, no=QUALIFIERS)
    result = score_submission(SAMPLE_ENTRIES, marks)
    assert result.score == 0


def test_yes_on_qualifier_only_ignoring_imposters() -> None:
    # Classic cautious play: say yes to the 6 qualifiers, leave imposters blank
    marks = _marks(yes=QUALIFIERS)
    result = score_submission(SAMPLE_ENTRIES, marks)
    assert result.score == 6
    assert result.perfect is False


def test_no_on_imposters_only() -> None:
    # Just identify imposters, don't commit on anything else
    marks = _marks(no=IMPOSTERS)
    result = score_submission(SAMPLE_ENTRIES, marks)
    assert result.score == 3


def test_mixed_marks() -> None:
    # YES on 4 qualifiers (+4), NO on 1 imposter (+1), YES on 1 imposter (0),
    # NO on 1 qualifier (0), leave 2 blank (0)
    marks: dict[int, Mark] = {
        0: Mark.YES,   # qualifier → +1
        1: Mark.YES,   # qualifier → +1
        3: Mark.YES,   # qualifier → +1
        4: Mark.YES,   # qualifier → +1
        2: Mark.NO,    # imposter  → +1
        5: Mark.YES,   # imposter  →  0 (false positive)
        6: Mark.NO,    # qualifier →  0 (wrong reject)
        # positions 7, 8 blank → 0
    }
    # 4 correct yes + 1 correct no = 5
    result = score_submission(SAMPLE_ENTRIES, marks)
    assert result.score == 5
    assert result.max_score == 9

    kinds = {o.grid_position: o.result for o in result.outcomes}
    assert kinds[0] is ResultKind.CORRECT
    assert kinds[2] is ResultKind.CORRECT_REJECT
    assert kinds[5] is ResultKind.FALSE_POSITIVE
    assert kinds[6] is ResultKind.WRONG_REJECT
    assert kinds[7] is ResultKind.UNANSWERED
    assert kinds[8] is ResultKind.UNANSWERED


def test_share_grid_emojis_cover_all_kinds() -> None:
    outcomes = [
        EntryOutcome(0, True,  Mark.YES,   ResultKind.CORRECT),
        EntryOutcome(1, False, Mark.NO,    ResultKind.CORRECT_REJECT),
        EntryOutcome(2, False, Mark.YES,   ResultKind.FALSE_POSITIVE),
        EntryOutcome(3, True,  Mark.NO,    ResultKind.WRONG_REJECT),
        EntryOutcome(4, True,  Mark.BLANK, ResultKind.UNANSWERED),
        EntryOutcome(5, False, Mark.BLANK, ResultKind.UNANSWERED),
        EntryOutcome(6, True,  Mark.YES,   ResultKind.CORRECT),
        EntryOutcome(7, False, Mark.NO,    ResultKind.CORRECT_REJECT),
        EntryOutcome(8, True,  Mark.YES,   ResultKind.CORRECT),
    ]
    grid = render_share_grid(outcomes)
    assert grid.splitlines() == [
        "🟩🟩🔴",
        "🟨⬜⬜",
        "🟩🟩🟩",
    ]


def test_share_text_format() -> None:
    outcomes = [
        EntryOutcome(i, True, Mark.YES, ResultKind.CORRECT) for i in range(9)
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


def test_share_text_appends_url_when_set() -> None:
    outcomes = [
        EntryOutcome(i, True, Mark.YES, ResultKind.CORRECT) for i in range(9)
    ]
    text = render_share_text(
        game_name="Cutline",
        puzzle_number=42,
        category_text="Won NL MVP",
        outcomes=outcomes,
        score=9,
        max_score=9,
        share_url="https://cutline.example/",
    )
    assert text.splitlines()[-1] == "https://cutline.example/"
