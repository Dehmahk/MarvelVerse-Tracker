"""add TV metadata columns to projects

Revision ID: 0005_add_tv_metadata
Revises: 0004_add_in_universe_date
Create Date: 2026-07-24 00:00:00.000000

Adds Project.season_count, episode_count, cancelled_date, and
next_season_release_date -- all nullable, all None for movies/shorts and
anything else that isn't an ongoing series. Curation fields (see
services/tmdb_sync_service.py's module docstring), same as
in_universe_date: not currently fetched by TMDB sync, set/edited by hand.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005_add_tv_metadata'
down_revision: Union[str, None] = '0004_add_in_universe_date'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.add_column(sa.Column('season_count', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('episode_count', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('cancelled_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('next_season_release_date', sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_column('next_season_release_date')
        batch_op.drop_column('cancelled_date')
        batch_op.drop_column('episode_count')
        batch_op.drop_column('season_count')
