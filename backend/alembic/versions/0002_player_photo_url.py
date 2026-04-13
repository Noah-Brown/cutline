"""Add photo_url to players.

Revision ID: 0002_player_photo_url
Revises: 0001_initial
Create Date: 2026-04-13

"""
from alembic import op
import sqlalchemy as sa


revision = "0002_player_photo_url"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "players",
        sa.Column("photo_url", sa.String(length=500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("players", "photo_url")
