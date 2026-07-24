"""expand achievement tiers and add all-achievements-complete criteria

Revision ID: 0002_expand_achievement_tiers
Revises: 0001_initial_schema
Create Date: 2026-07-23 00:00:00.000000

Adds AchievementTier.DIAMOND / AchievementTier.MARVELOUS and
AchievementCriteriaType.ALL_ACHIEVEMENTS_COMPLETE. Both columns use
SQLAlchemy's non-native Enum (native_enum=False), which SQLite implements
as a plain VARCHAR with a CHECK constraint enumerating the allowed values
-- so widening either enum in models/achievement.py requires actually
altering that constraint here, not just editing the Python enum. SQLite
can't ALTER a CHECK constraint in place, so this goes through Alembic's
batch mode (recreate-the-table-under-the-hood), same as any other SQLite
column-definition change.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002_expand_achievement_tiers'
down_revision: Union[str, None] = '0001_initial_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_TIERS = ('BRONZE', 'SILVER', 'GOLD', 'PLATINUM')
_NEW_TIERS = ('BRONZE', 'SILVER', 'GOLD', 'PLATINUM', 'DIAMOND', 'MARVELOUS')

_OLD_CRITERIA = (
    'WATCH_COUNT', 'UNIVERSE_COMPLETE', 'FRANCHISE_COMPLETE', 'GENRE_COUNT',
    'RATING_COUNT', 'REWATCH_COUNT', 'COLLECTION_COMPLETE',
)
_NEW_CRITERIA = _OLD_CRITERIA + ('ALL_ACHIEVEMENTS_COMPLETE',)


def upgrade() -> None:
    with op.batch_alter_table('achievements', schema=None) as batch_op:
        batch_op.alter_column(
            'tier',
            existing_type=sa.Enum(*_OLD_TIERS, name='achievementtier', native_enum=False, length=16),
            type_=sa.Enum(*_NEW_TIERS, name='achievementtier', native_enum=False, length=16),
            existing_nullable=False,
        )
        batch_op.alter_column(
            'criteria_type',
            existing_type=sa.Enum(
                *_OLD_CRITERIA, name='achievementcriteriatype', native_enum=False, length=32
            ),
            type_=sa.Enum(
                *_NEW_CRITERIA, name='achievementcriteriatype', native_enum=False, length=32
            ),
            existing_nullable=False,
        )


def downgrade() -> None:
    # Reverting drops DIAMOND/MARVELOUS/ALL_ACHIEVEMENTS_COMPLETE from the
    # allowed set again -- only safe if no row actually uses one of those
    # values at the time this runs (same caveat as any enum-narrowing
    # downgrade).
    with op.batch_alter_table('achievements', schema=None) as batch_op:
        batch_op.alter_column(
            'criteria_type',
            existing_type=sa.Enum(
                *_NEW_CRITERIA, name='achievementcriteriatype', native_enum=False, length=32
            ),
            type_=sa.Enum(
                *_OLD_CRITERIA, name='achievementcriteriatype', native_enum=False, length=32
            ),
            existing_nullable=False,
        )
        batch_op.alter_column(
            'tier',
            existing_type=sa.Enum(*_NEW_TIERS, name='achievementtier', native_enum=False, length=16),
            type_=sa.Enum(*_OLD_TIERS, name='achievementtier', native_enum=False, length=16),
            existing_nullable=False,
        )
