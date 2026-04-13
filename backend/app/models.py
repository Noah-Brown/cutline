"""SQLAlchemy ORM models matching the Cutline design spec schema."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    ARRAY,
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    bbref_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name_display: Mapped[str] = mapped_column(String(200), nullable=False)
    name_first: Mapped[str | None] = mapped_column(String(100))
    name_last: Mapped[str | None] = mapped_column(String(100))
    debut_year: Mapped[int | None] = mapped_column(Integer)
    final_year: Mapped[int | None] = mapped_column(Integer)
    primary_position: Mapped[str | None] = mapped_column(String(10))
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    photo_url: Mapped[str | None] = mapped_column(String(500))

    awards: Mapped[list["Award"]] = relationship(back_populates="player", cascade="all, delete-orphan")
    seasons: Mapped[list["SeasonStat"]] = relationship(back_populates="player", cascade="all, delete-orphan")
    allstars: Mapped[list["AllStarAppearance"]] = relationship(back_populates="player", cascade="all, delete-orphan")
    teams: Mapped[list["PlayerTeam"]] = relationship(back_populates="player", cascade="all, delete-orphan")


class Award(Base):
    __tablename__ = "awards"
    __table_args__ = (
        UniqueConstraint("player_id", "award_type", "year", name="uq_award_player_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    award_type: Mapped[str] = mapped_column(String(100), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    league: Mapped[str | None] = mapped_column(String(5))
    team: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)

    player: Mapped[Player] = relationship(back_populates="awards")


class SeasonStat(Base):
    __tablename__ = "season_stats"
    __table_args__ = (
        UniqueConstraint("player_id", "year", "team", name="uq_season_player_year_team"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    team: Mapped[str | None] = mapped_column(String(100))
    league: Mapped[str | None] = mapped_column(String(5))
    games: Mapped[int | None] = mapped_column(Integer)

    # Batting
    batting_avg: Mapped[Decimal | None] = mapped_column(Numeric(4, 3))
    home_runs: Mapped[int | None] = mapped_column(Integer)
    rbi: Mapped[int | None] = mapped_column(Integer)
    hits: Mapped[int | None] = mapped_column(Integer)
    stolen_bases: Mapped[int | None] = mapped_column(Integer)
    ops: Mapped[Decimal | None] = mapped_column(Numeric(5, 3))
    war: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))

    # Pitching
    wins: Mapped[int | None] = mapped_column(Integer)
    losses: Mapped[int | None] = mapped_column(Integer)
    era: Mapped[Decimal | None] = mapped_column(Numeric(4, 2))
    strikeouts: Mapped[int | None] = mapped_column(Integer)
    saves: Mapped[int | None] = mapped_column(Integer)
    innings_pitched: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))

    player: Mapped[Player] = relationship(back_populates="seasons")


class AllStarAppearance(Base):
    __tablename__ = "allstar_appearances"
    __table_args__ = (
        UniqueConstraint("player_id", "year", name="uq_allstar_player_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    team: Mapped[str | None] = mapped_column(String(100))
    league: Mapped[str | None] = mapped_column(String(5))

    player: Mapped[Player] = relationship(back_populates="allstars")


class PlayerTeam(Base):
    __tablename__ = "player_teams"
    __table_args__ = (
        UniqueConstraint("player_id", "year", "team", name="uq_player_team_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    team: Mapped[str] = mapped_column(String(100), nullable=False)
    league: Mapped[str | None] = mapped_column(String(5))

    player: Mapped[Player] = relationship(back_populates="teams")


class Puzzle(Base):
    __tablename__ = "puzzles"
    __table_args__ = (
        CheckConstraint(
            "imposter_count BETWEEN 2 AND 4", name="ck_puzzle_imposter_count"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    puzzle_date: Mapped[date] = mapped_column(Date, unique=True, nullable=False)
    category_text: Mapped[str] = mapped_column(String(300), nullable=False)
    category_type: Mapped[str] = mapped_column(String(100), nullable=False)
    imposter_count: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    entries: Mapped[list["PuzzleEntry"]] = relationship(
        back_populates="puzzle",
        cascade="all, delete-orphan",
        order_by="PuzzleEntry.grid_position",
    )
    submissions: Mapped[list["Submission"]] = relationship(
        back_populates="puzzle", cascade="all, delete-orphan"
    )


class PuzzleEntry(Base):
    __tablename__ = "puzzle_entries"
    __table_args__ = (
        UniqueConstraint("puzzle_id", "grid_position", name="uq_entry_puzzle_position"),
        UniqueConstraint("puzzle_id", "player_id", name="uq_entry_puzzle_player"),
        CheckConstraint(
            "grid_position BETWEEN 0 AND 8", name="ck_entry_grid_position"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    puzzle_id: Mapped[int] = mapped_column(ForeignKey("puzzles.id", ondelete="CASCADE"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    grid_position: Mapped[int] = mapped_column(Integer, nullable=False)
    is_qualifier: Mapped[bool] = mapped_column(Boolean, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    puzzle: Mapped[Puzzle] = relationship(back_populates="entries")
    player: Mapped[Player] = relationship()


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint("puzzle_id", "session_id", name="uq_submission_puzzle_session"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    puzzle_id: Mapped[int] = mapped_column(ForeignKey("puzzles.id", ondelete="CASCADE"))
    session_id: Mapped[str] = mapped_column(String(100), nullable=False)
    # Store selections as JSON for SQLite compatibility; Postgres would use ARRAY(Integer).
    selections: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    max_score: Mapped[int] = mapped_column(Integer, nullable=False)
    perfect: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    puzzle: Mapped[Puzzle] = relationship(back_populates="submissions")
