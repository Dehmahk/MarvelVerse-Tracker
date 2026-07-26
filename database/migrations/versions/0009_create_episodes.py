"""create episodes table

Revision ID: 0009_create_episodes
Revises: 0008_add_is_hidden
Create Date: 2026-07-26 00:00:00.000000

Adds the episodes table for per-episode watch tracking on TV shows,
separate from UserProjectData's single whole-show watched flag.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009_create_episodes'
down_revision: Union[str, None] = '0008_add_is_hidden'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'episodes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('season_number', sa.Integer(), nullable=False),
        sa.Column('episode_number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=256), nullable=True),
        sa.Column('watched', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('watched_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'season_number', 'episode_number', name='uq_episode_identity'),
    )
    with op.batch_alter_table('episodes', schema=None) as batch_op:
        batch_op.create_index('ix_episodes_project_id', ['project_id'])


def downgrade() -> None:
    op.drop_table('episodes')
