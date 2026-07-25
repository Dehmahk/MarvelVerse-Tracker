from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin


class Episode(Base, TimestampMixin):
    """One episode of one season of a TV-shaped Project -- lets a show be
    tracked episode-by-episode instead of only as a single watched/
    unwatched unit the way UserProjectData tracks movies.

    Unlike Project (shared reference data meant to eventually come from
    TMDB), this behaves more like Collection: entirely local, user-side
    data. There's no live per-episode TMDB sync in this app, so rows
    here are generated locally from a project's own season_count/
    episode_count (see services.episode_service.ensure_episodes_exist)
    the first time its episodes are actually looked at, with a generic
    "Episode N" title rather than a real one -- accurate titles would
    need a real per-episode TMDB endpoint this app doesn't call.
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
    watched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    watched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="episodes")  # noqa: F821

    def __repr__(self) -> str:  # pragma: no cover - debug convenience only
        return f"<Episode project_id={self.project_id} S{self.season_number}E{self.episode_number}>"
