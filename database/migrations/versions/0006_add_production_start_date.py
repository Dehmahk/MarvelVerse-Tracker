"""add production_start_date column to projects

Revision ID: 0006_add_production_start_date
Revises: 0005_add_tv_metadata
Create Date: 2026-07-24 00:00:00.000000

Adds Project.production_start_date -- "date began production", distinct
from release_date. Curation field, same as in_universe_date/season_count/
etc.: nullable, not currently fetched by TMDB sync, set by hand.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006_add_production_start_date'
down_revision: Union[str, None] = '0005_add_tv_metadata'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.add_column(sa.Column('production_start_date', sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_column('production_start_date')
