"""Initial schema.

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-13

"""
from alembic import op
import sqlalchemy as sa


revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("bbref_id", sa.String(length=20), nullable=False, unique=True),
        sa.Column("name_display", sa.String(length=200), nullable=False),
        sa.Column("name_first", sa.String(length=100)),
        sa.Column("name_last", sa.String(length=100)),
        sa.Column("debut_year", sa.Integer()),
        sa.Column("final_year", sa.Integer()),
        sa.Column("primary_position", sa.String(length=10)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.create_table(
        "awards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("award_type", sa.String(length=100), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("league", sa.String(length=5)),
        sa.Column("team", sa.String(length=100)),
        sa.Column("notes", sa.Text()),
        sa.UniqueConstraint("player_id", "award_type", "year", name="uq_award_player_year"),
    )
    op.create_index("ix_awards_type_year", "awards", ["award_type", "year"])

    op.create_table(
        "season_stats",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("team", sa.String(length=100)),
        sa.Column("league", sa.String(length=5)),
        sa.Column("games", sa.Integer()),
        sa.Column("batting_avg", sa.Numeric(4, 3)),
        sa.Column("home_runs", sa.Integer()),
        sa.Column("rbi", sa.Integer()),
        sa.Column("hits", sa.Integer()),
        sa.Column("stolen_bases", sa.Integer()),
        sa.Column("ops", sa.Numeric(5, 3)),
        sa.Column("war", sa.Numeric(4, 1)),
        sa.Column("wins", sa.Integer()),
        sa.Column("losses", sa.Integer()),
        sa.Column("era", sa.Numeric(4, 2)),
        sa.Column("strikeouts", sa.Integer()),
        sa.Column("saves", sa.Integer()),
        sa.Column("innings_pitched", sa.Numeric(5, 1)),
        sa.UniqueConstraint("player_id", "year", "team", name="uq_season_player_year_team"),
    )

    op.create_table(
        "allstar_appearances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("team", sa.String(length=100)),
        sa.Column("league", sa.String(length=5)),
        sa.UniqueConstraint("player_id", "year", name="uq_allstar_player_year"),
    )

    op.create_table(
        "player_teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("team", sa.String(length=100), nullable=False),
        sa.Column("league", sa.String(length=5)),
        sa.UniqueConstraint("player_id", "year", "team", name="uq_player_team_year"),
    )

    op.create_table(
        "puzzles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("puzzle_date", sa.Date(), nullable=False, unique=True),
        sa.Column("category_text", sa.String(length=300), nullable=False),
        sa.Column("category_type", sa.String(length=100), nullable=False),
        sa.Column("imposter_count", sa.Integer(), nullable=False),
        sa.Column("difficulty", sa.String(length=20), server_default="medium"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint("imposter_count BETWEEN 2 AND 4", name="ck_puzzle_imposter_count"),
    )

    op.create_table(
        "puzzle_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("puzzle_id", sa.Integer(), sa.ForeignKey("puzzles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("grid_position", sa.Integer(), nullable=False),
        sa.Column("is_qualifier", sa.Boolean(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.UniqueConstraint("puzzle_id", "grid_position", name="uq_entry_puzzle_position"),
        sa.UniqueConstraint("puzzle_id", "player_id", name="uq_entry_puzzle_player"),
        sa.CheckConstraint("grid_position BETWEEN 0 AND 8", name="ck_entry_grid_position"),
    )

    op.create_table(
        "submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("puzzle_id", sa.Integer(), sa.ForeignKey("puzzles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", sa.String(length=100), nullable=False),
        sa.Column("selections", sa.JSON(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("max_score", sa.Integer(), nullable=False),
        sa.Column("perfect", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("puzzle_id", "session_id", name="uq_submission_puzzle_session"),
    )


def downgrade() -> None:
    op.drop_table("submissions")
    op.drop_table("puzzle_entries")
    op.drop_table("puzzles")
    op.drop_table("player_teams")
    op.drop_table("allstar_appearances")
    op.drop_table("season_stats")
    op.drop_index("ix_awards_type_year", table_name="awards")
    op.drop_table("awards")
    op.drop_table("players")
