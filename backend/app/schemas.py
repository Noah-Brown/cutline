"""Pydantic request/response schemas for the public + admin APIs."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# --- Public: Puzzle --------------------------------------------------------


class PuzzlePlayer(BaseModel):
    grid_position: int = Field(ge=0, le=8)
    name: str
    player_id: int
    photo_url: str | None = None


class PuzzleResponse(BaseModel):
    puzzle_id: int
    puzzle_number: int
    date: date
    category: str
    players: list[PuzzlePlayer]


class SubmissionMarks(BaseModel):
    """Tri-state marks for a submission. Positions not in either list are BLANK."""

    yes: list[int] = Field(default_factory=list)
    no: list[int] = Field(default_factory=list)

    @field_validator("yes", "no")
    @classmethod
    def _valid_positions(cls, v: list[int]) -> list[int]:
        if any(p < 0 or p > 8 for p in v):
            raise ValueError("grid_position must be in [0, 8]")
        if len(set(v)) != len(v):
            raise ValueError("positions must not contain duplicates")
        return sorted(set(v))


class SubmitRequest(BaseModel):
    puzzle_id: int
    session_id: str = Field(min_length=1, max_length=100)
    marks: SubmissionMarks

    @field_validator("marks")
    @classmethod
    def _disjoint(cls, v: SubmissionMarks) -> SubmissionMarks:
        overlap = set(v.yes) & set(v.no)
        if overlap:
            raise ValueError(f"positions cannot be in both yes and no: {sorted(overlap)}")
        return v


ResultLiteral = Literal[
    "correct",
    "false_positive",
    "correct_reject",
    "wrong_reject",
    "unanswered",
]
MarkLiteral = Literal["yes", "no", "blank"]


class PlayerResult(BaseModel):
    grid_position: int
    player_id: int
    name: str
    photo_url: str | None = None
    is_qualifier: bool
    mark: MarkLiteral
    result: ResultLiteral
    explanation: str


class SubmitResponse(BaseModel):
    puzzle_id: int
    score: int
    max_score: int
    perfect: bool
    results: list[PlayerResult]
    share_text: str


class PuzzleStats(BaseModel):
    puzzle_id: int
    submissions: int
    avg_score: float | None
    perfect_count: int
    completion_rate: float | None = None


class StreakResponse(BaseModel):
    session_id: str
    current_streak: int
    longest_streak: int
    last_played_date: date | None


# --- Admin -----------------------------------------------------------------


class PuzzleEntryIn(BaseModel):
    player_id: int
    grid_position: int = Field(ge=0, le=8)
    is_qualifier: bool
    explanation: str = Field(min_length=1, max_length=500)


class CreatePuzzleRequest(BaseModel):
    puzzle_date: date
    category_text: str = Field(min_length=1, max_length=300)
    category_type: str = Field(min_length=1, max_length=100)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    entries: list[PuzzleEntryIn]
    published: bool = False

    @field_validator("entries")
    @classmethod
    def _validate_entries(cls, v: list[PuzzleEntryIn]) -> list[PuzzleEntryIn]:
        if len(v) != 9:
            raise ValueError("puzzle must have exactly 9 entries")
        positions = {e.grid_position for e in v}
        if positions != set(range(9)):
            raise ValueError("entries must cover grid_positions 0..8 exactly once")
        qualifiers = sum(1 for e in v if e.is_qualifier)
        imposters = 9 - qualifiers
        if imposters < 2 or imposters > 4:
            raise ValueError("puzzle must have 2–4 imposters (5–7 qualifiers)")
        return v


class CategoryInfo(BaseModel):
    key: str
    display: str
    difficulty_hint: str


class PlayerSearchHit(BaseModel):
    player_id: int
    name: str
    debut_year: int | None
    final_year: int | None
    primary_position: str | None
    photo_url: str | None = None


class PlayerUpdate(BaseModel):
    """Partial update of a player — MVP surface is just photo_url."""

    photo_url: str | None = Field(default=None, max_length=500)


class PhotoUploadResponse(BaseModel):
    player_id: int
    photo_url: str


class QualifierPoolResponse(BaseModel):
    category_key: str
    qualifiers: list[PlayerSearchHit]
    imposter_candidates: list[PlayerSearchHit]
