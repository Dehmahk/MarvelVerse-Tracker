"""add is_hidden column to achievements

Revision ID: 0008_add_is_hidden
Revises: 0007_add_watched_with
Create Date: 2026-07-26 00:00:00.000000

Adds Achievement.is_hidden -- marks a "secret" achievement whose real
name/description/icon stay hidden as "???" in the UI until unlocked.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008_add_is_hidden'
down_revision: Union[str, None] = '0007_add_watched_with'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('achievements', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('is_hidden', sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table('achievements', schema=None) as batch_op:
        batch_op.drop_column('is_hidden')
