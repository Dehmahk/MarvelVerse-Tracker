from __future__ import annotations

import enum
from datetime import date

from sqlalchemy import Date, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin
from models.genre import project_genres
from models.tag import project_tags


class ProjectType(str, enum.Enum):
    MOVIE = "movie"
    TV_SERIES = "tv_series"
    TV_SPECIAL = "tv_special"
    SHORT = "short"
    DOCUMENTARY = "documentary"
    ANIMATED_SERIES = "animated_series"


class ProjectStatus(str, enum.Enum):
    RELEASED = "released"
    UPCOMING = "upcoming"
    ANNOUNCED = "announced"
    IN_PRODUCTION = "in_production"
    CANCELLED = "cancelled"


class Project(TimestampMixin, Base):
    """Canonical, API-synchronizable data about a single Marvel project
    (a movie, series, or special). Never stores personal/user data directly —
    that lives on the one-to-one UserProjectData row so that refreshing
    canonical data can never clobber what the user has recorded."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)

    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True)
    project_type: Mapped[ProjectType] = mapped_column(
        Enum(ProjectType, native_enum=False, length=32), nullable=False
    )
    status: Mapped[ProjectStatus] = mapped_column(
        Enum(ProjectStatus, native_enum=False, length=32),
        default=ProjectStatus.ANNOUNCED,
        nullable=False,
    )

    universe_id: Mapped[int | None] = mapped_column(
        ForeignKey("universes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    franchise_id: Mapped[int | None] = mapped_column(
        ForeignKey("franchises.id", ondelete="SET NULL"), nullable=True, index=True
    )

    release_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    runtime_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    studio: Mapped[str | None] = mapped_column(String(128), nullable=True)
    synopsis: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Free text rather than a real Date column: in-story placement in the
    # Marvel timeline is often approximate or relative ("Early 2018",
    # "Three weeks after the Battle of New York", "During the Blip")
    # rather than an exact calendar date, and plenty of projects (most
    # one-shots, documentaries, anthology/non-canon content) don't have
    # one at all. Distinct from release_date, which is the real-world
    # release date and always a real, exact date when known.
    in_universe_date: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # --- TV-specific metadata (all None for movies/shorts/one-offs) ------------
    # Curation fields, same as in_universe_date above -- TMDB sync doesn't
    # currently fetch season/episode counts or cancellation/next-season
    # dates, so these are set by hand and protected the same way (see
    # services/tmdb_sync_service.py's module docstring).
    season_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Only meaningful when status == ProjectStatus.CANCELLED; when a show
    # is cancelled but the exact date isn't known/tracked, this stays
    # None even though the status itself already says CANCELLED.
    cancelled_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Set once a next season is confirmed/announced; None otherwise --
    # deliberately not implied by ProjectStatus, since a show can be
    # RELEASED (its current season is out) while also having a
    # next_season_release_date set for the one already announced.
    next_season_release_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # "Date began production" -- when filming/production actually started,
    # distinct from release_date. Curation field, same as the others
    # above: not currently fetched by TMDB sync, set by hand, protected
    # from being overwritten by a resync (see
    # services/tmdb_sync_service.py's module docstring).
    production_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    poster_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    background_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    trailer_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    saga: Mapped[str | None] = mapped_column(String(128), nullable=True)
    phase: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chronological_order: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    tmdb_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    imdb_id: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True)

    # --- relationships -----------------------------------------------------
    universe: Mapped["Universe"] = relationship(back_populates="projects")
    franchise: Mapped["Franchise"] = relationship(back_populates="projects")

    genres: Mapped[list["Genre"]] = relationship(
        secondary=project_genres, back_populates="projects", order_by="Genre.name"
    )
    tags: Mapped[list["Tag"]] = relationship(
        secondary=project_tags, back_populates="projects", order_by="Tag.name"
    )

    cast: Mapped[list["ProjectCast"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectCast.billing_order",
    )
    crew: Mapped[list["ProjectCrew"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    user_data: Mapped["UserProjectData"] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False
    )
    watch_history: Mapped[list["WatchHistoryEntry"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        # Secondary sort by id breaks ties deterministically when two
        # entries land in the same second (SQLite's CURRENT_TIMESTAMP has
        # only second-level precision).
        order_by="(WatchHistoryEntry.watched_at.desc(), WatchHistoryEntry.id.desc())",
    )
    collection_links: Mapped[list["CollectionProject"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience only
        return f"<Project id={self.id} title={self.title!r}>"
