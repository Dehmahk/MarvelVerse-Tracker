"""add skipped column to user_project_data

Revision ID: 0003_add_skipped_flag
Revises: 0002_expand_achievement_tiers
Create Date: 2026-07-23 00:00:00.000000

Adds UserProjectData.skipped -- "I've deliberately chosen not to watch
this," independent of watched/favorite/wishlist. A plain nullable=False
Boolean column with a server-side default, so existing rows all become
skipped=False rather than NULL.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003_add_skipped_flag'
down_revision: Union[str, None] = '0002_expand_achievement_tiers'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('user_project_data', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('skipped', sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table('user_project_data', schema=None) as batch_op:
        batch_op.drop_column('skipped')
