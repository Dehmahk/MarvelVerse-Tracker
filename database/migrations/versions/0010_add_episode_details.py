"""add air_date, runtime_minutes, summary columns to episodes

Revision ID: 0010_add_episode_details
Revises: 0009_create_episodes
Create Date: 2026-07-26 00:00:00.000000

Adds Episode.air_date/runtime_minutes/summary -- populated only by a
real TMDB per-season sync (services.episode_service.sync_episodes_from_tmdb),
never fabricated.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010_add_episode_details'
down_revision: Union[str, None] = '0009_create_episodes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('episodes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('air_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('runtime_minutes', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('summary', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('episodes', schema=None) as batch_op:
        batch_op.drop_column('summary')
        batch_op.drop_column('runtime_minutes')
        batch_op.drop_column('air_date')
