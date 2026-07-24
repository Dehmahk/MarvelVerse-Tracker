"""SQLAlchemy models for MarvelVerse Tracker.

Importing this package registers every mapped class on ``Base.metadata``,
which is required before ``Base.metadata.create_all(...)`` or Alembic
autogeneration can see the full schema. Always import models through this
package (``from models import Project``) rather than reaching into
individual submodules, so the registration order stays predictable.
"""

from models.base import Base, TimestampMixin
from models.universe import Universe
from models.franchise import Franchise
from models.genre import Genre, project_genres
from models.tag import Tag, project_tags
from models.person import Person, ProjectCast, ProjectCrew
from models.project import Project, ProjectType, ProjectStatus
from models.user_data import UserProjectData
from models.watch_history import WatchHistoryEntry
from models.collection import Collection, CollectionProject
from models.achievement import (
    Achievement,
    AchievementCriteriaType,
    AchievementTier,
    UserAchievement,
)

__all__ = [
    "Base",
    "TimestampMixin",
    "Universe",
    "Franchise",
    "Genre",
    "project_genres",
    "Tag",
    "project_tags",
    "Person",
    "ProjectCast",
    "ProjectCrew",
    "Project",
    "ProjectType",
    "ProjectStatus",
    "UserProjectData",
    "WatchHistoryEntry",
    "Collection",
    "CollectionProject",
    "Achievement",
    "AchievementCriteriaType",
    "AchievementTier",
    "UserAchievement",
]
