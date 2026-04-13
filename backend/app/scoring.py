"""Scoring engine and share-grid generation.

Scoring rules (per design spec):
  +1 for each qualifier the player tapped (correct selection)
  -1 for each imposter the player tapped (false positive)
  -1 for each qualifier the player did NOT tap (missed qualifier)
   0 for each imposter the player correctly avoided

max_score == number of qualifiers in the puzzle.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ResultKind(str, Enum):
    CORRECT = "correct"                # qualifier tapped
    FALSE_POSITIVE = "false_positive"  # imposter tapped
    MISSED = "missed"                  # qualifier not tapped
    CORRECT_AVOID = "correct_avoid"    # imposter not tapped


@dataclass(frozen=True)
class EntryOutcome:
    grid_position: int
    is_qualifier: bool
    was_selected: bool
    result: ResultKind


@dataclass(frozen=True)
class ScoreResult:
    score: int
    max_score: int
    perfect: bool
    outcomes: list[EntryOutcome]


def classify(is_qualifier: bool, was_selected: bool) -> ResultKind:
    if is_qualifier and was_selected:
        return ResultKind.CORRECT
    if is_qualifier and not was_selected:
        return ResultKind.MISSED
    if (not is_qualifier) and was_selected:
        return ResultKind.FALSE_POSITIVE
    return ResultKind.CORRECT_AVOID


def score_submission(
    entries: list[tuple[int, bool]],  # (grid_position, is_qualifier)
    selections: set[int],
) -> ScoreResult:
    """Compute the score and per-entry outcomes.

    Args:
        entries: Iterable of (grid_position, is_qualifier) for all 9 grid slots.
        selections: Set of grid_positions the player tapped.
    """
    outcomes: list[EntryOutcome] = []
    score = 0
    max_score = 0

    for grid_position, is_qualifier in entries:
        was_selected = grid_position in selections
        kind = classify(is_qualifier, was_selected)

        if is_qualifier:
            max_score += 1

        if kind is ResultKind.CORRECT:
            score += 1
        elif kind is ResultKind.FALSE_POSITIVE:
            score -= 1
        elif kind is ResultKind.MISSED:
            score -= 1

        outcomes.append(
            EntryOutcome(
                grid_position=grid_position,
                is_qualifier=is_qualifier,
                was_selected=was_selected,
                result=kind,
            )
        )

    outcomes.sort(key=lambda o: o.grid_position)
    perfect = score == max_score
    return ScoreResult(score=score, max_score=max_score, perfect=perfect, outcomes=outcomes)


# --- Share-grid rendering -------------------------------------------------

_EMOJI = {
    ResultKind.CORRECT: "🟩",
    ResultKind.CORRECT_AVOID: "🟩",  # green: you got it right (avoided imposter)
    ResultKind.FALSE_POSITIVE: "🔴",  # red: you selected an imposter
    ResultKind.MISSED: "🟨",          # yellow: you missed a qualifier
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
