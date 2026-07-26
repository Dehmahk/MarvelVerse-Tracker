"""add watched_with column to watch_history

Revision ID: 0007_add_watched_with
Revises: 0006_add_production_start_date
Create Date: 2026-07-25 00:00:00.000000

Adds WatchHistoryEntry.watched_with -- free text noting who a specific
watch event was shared with, distinct from notes (which is about the
watch itself, not who was there for it).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007_add_watched_with'
down_revision: Union[str, None] = '0006_add_production_start_date'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('watch_history', schema=None) as batch_op:
        batch_op.add_column(sa.Column('watched_with', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('watch_history', schema=None) as batch_op:
        batch_op.drop_column('watched_with')
