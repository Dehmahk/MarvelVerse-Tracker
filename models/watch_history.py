from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class WatchHistoryEntry(Base):
    """A single logged watch event for a project. A project can be watched
    (and logged) multiple times; UserProjectData.watched / rewatch_count are
    a convenient rollup, while this table is the full watch log."""

    __tablename__ = "watch_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    watched_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )
    is_rewatch: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free text -- "Sarah", "the whole family", "movie night group", etc.
    # Deliberately not a structured/normalized list of "people" records;
    # this is just a personal note about a specific watch event, not
    # meant to cross-reference against cast/crew Person rows.
    watched_with: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="watch_history")

    def __repr__(self) -> str:  # pragma: no cover - debug convenience only
        return f"<WatchHistoryEntry project_id={self.project_id} watched_at={self.watched_at}>"
