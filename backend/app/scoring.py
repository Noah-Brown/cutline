"""Scoring engine and share-grid generation — tri-state marks.

Each card gets one of three marks:
  • YES   — the player thinks this name qualifies
  • NO    — the player thinks this name is an imposter
  • BLANK — the player is unsure / left it alone

Scoring (correct calls only — wrong calls and blanks score 0):
  YES on qualifier  → +1 (CORRECT)
  NO  on imposter   → +1 (CORRECT_REJECT)
  YES on imposter   →  0 (FALSE_POSITIVE)
  NO  on qualifier  →  0 (WRONG_REJECT)
  BLANK on either   →  0 (UNANSWERED)

max_score is 9. The UI requires a mark on every card, so BLANK/UNANSWERED
should not occur in real submissions — the model still supports it so the
share-grid renderer and older submissions keep working.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Mark(str, Enum):
    YES = "yes"
    NO = "no"
    BLANK = "blank"


class ResultKind(str, Enum):
    CORRECT = "correct"                 # YES on qualifier
    FALSE_POSITIVE = "false_positive"   # YES on imposter
    CORRECT_REJECT = "correct_reject"   # NO on imposter
    WRONG_REJECT = "wrong_reject"       # NO on qualifier
    UNANSWERED = "unanswered"           # BLANK


@dataclass(frozen=True)
class EntryOutcome:
    grid_position: int
    is_qualifier: bool
    mark: Mark
    result: ResultKind


@dataclass(frozen=True)
class ScoreResult:
    score: int
    max_score: int
    perfect: bool
    outcomes: list[EntryOutcome]


def classify(is_qualifier: bool, mark: Mark) -> ResultKind:
    if mark is Mark.YES:
        return ResultKind.CORRECT if is_qualifier else ResultKind.FALSE_POSITIVE
    if mark is Mark.NO:
        return ResultKind.WRONG_REJECT if is_qualifier else ResultKind.CORRECT_REJECT
    return ResultKind.UNANSWERED


_POINTS: dict[ResultKind, int] = {
    ResultKind.CORRECT: 1,
    ResultKind.CORRECT_REJECT: 1,
    ResultKind.FALSE_POSITIVE: 0,
    ResultKind.WRONG_REJECT: 0,
    ResultKind.UNANSWERED: 0,
}


def score_submission(
    entries: list[tuple[int, bool]],  # (grid_position, is_qualifier)
    marks: dict[int, Mark],           # grid_position → mark (missing = BLANK)
) -> ScoreResult:
    """Compute the score and per-entry outcomes under tri-state rules."""
    outcomes: list[EntryOutcome] = []
    score = 0

    for grid_position, is_qualifier in entries:
        mark = marks.get(grid_position, Mark.BLANK)
        kind = classify(is_qualifier, mark)
        score += _POINTS[kind]
        outcomes.append(
            EntryOutcome(
                grid_position=grid_position,
                is_qualifier=is_qualifier,
                mark=mark,
                result=kind,
            )
        )

    outcomes.sort(key=lambda o: o.grid_position)
    max_score = len(entries)  # 9
    return ScoreResult(
        score=score,
        max_score=max_score,
        perfect=score == max_score,
        outcomes=outcomes,
    )


# --- Share-grid rendering -------------------------------------------------

_EMOJI: dict[ResultKind, str] = {
    ResultKind.CORRECT: "🟩",
    ResultKind.CORRECT_REJECT: "🟩",    # you correctly identified an imposter
    ResultKind.FALSE_POSITIVE: "🔴",     # picked an imposter as a qualifier
    ResultKind.WRONG_REJECT: "🟨",       # rejected a real qualifier
    ResultKind.UNANSWERED: "⬜",         # left blank
}


def render_share_grid(outcomes: list[EntryOutcome]) -> str:
    """Render a 3×3 emoji grid (left-to-right, top-to-bottom)."""
    by_pos = {o.grid_position: o for o in outcomes}
    rows: list[str] = []
    for row in range(3):
        cells: list[str] = []
        for col in range(3):
            pos = row * 3 + col
            outcome = by_pos.get(pos)
            cells.append(_EMOJI[outcome.result] if outcome else "⬜")
        rows.append("".join(cells))
    return "\n".join(rows)


def render_share_text(
    *,
    game_name: str,
    puzzle_number: int,
    category_text: str,
    outcomes: list[EntryOutcome],
    score: int,
    max_score: int,
) -> str:
    """Render the full shareable string, spoiler-free."""
    grid = render_share_grid(outcomes)
    return (
        f"⚾ {game_name} #{puzzle_number} — \"{category_text}\"\n"
        f"{grid}\n"
        f"Score: {score}/{max_score}"
    )
