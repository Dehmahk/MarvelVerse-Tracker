from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin


class Episode(Base, TimestampMixin):
    """One episode of one season of a TV-shaped Project -- lets a show be
    tracked episode-by-episode instead of only as a single watched/
    unwatched unit the way UserProjectData tracks movies.

    Unlike Project (shared reference data meant to eventually come from
    TMDB), this behaves more like Collection: entirely local, user-side
    data. Rows are generated locally from a project's own season_count/
    episode_count (see services.episode_service.ensure_episodes_exist)
    the first time its episodes are actually looked at, with a generic
    "Episode N" title and no air_date/runtime/summary -- those three
    fields are only ever populated by a real TMDB sync
    (services.episode_service.sync_episodes_from_tmdb, for a project
    that already has a real tmdb_id), never guessed or fabricated.
    """

    __tablename__ = "episodes"
    __table_args__ = (
        UniqueConstraint("project_id", "season_number", "episode_number", name="uq_episode_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    season_number: Mapped[int] = mapped_column(Integer, nullable=False)
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(256), nullable=True)
    air_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    runtime_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    watched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    watched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="episodes")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover - debug convenience only
        return f"<Episode project_id={self.project_id} S{self.season_number}E{self.episode_number}>"
