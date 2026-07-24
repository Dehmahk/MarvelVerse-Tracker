"""add in_universe_date column to projects

Revision ID: 0004_add_in_universe_date
Revises: 0003_add_skipped_flag
Create Date: 2026-07-24 00:00:00.000000

Adds Project.in_universe_date -- free-text in-story timeline placement
("Early 2018", "Three weeks after the Battle of New York"), distinct from
release_date (the real-world release date). Nullable, no default: most
existing rows won't have a value until backfilled, and that's a valid
"unknown/not applicable" state, not a data problem to paper over.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004_add_in_universe_date'
down_revision: Union[str, None] = '0003_add_skipped_flag'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.add_column(sa.Column('in_universe_date', sa.String(length=128), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_column('in_universe_date')
