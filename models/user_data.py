from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin


class UserProjectData(TimestampMixin, Base):
    """One-to-one, per-project record of everything personal to the user:
    watched status, rating, favorite flag, notes, wishlist, rewatch count.

    This table is intentionally separate from Project so that an API
    refresh of canonical metadata (poster, synopsis, cast, ...) can never
    overwrite anything the user has recorded here."""

    __tablename__ = "user_project_data"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    watched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    wishlist: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # "I've deliberately chosen not to watch this" -- e.g. a one-shot short
    # or spin-off the user isn't interested in. Independent of watched/
    # favorite/wishlist, same as those three are independent of each
    # other; nothing in the schema enforces them being mutually exclusive.
    skipped: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_watched_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    rewatch_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="user_data")

    def __repr__(self) -> str:  # pragma: no cover - debug convenience only
        return f"<UserProjectData project_id={self.project_id} watched={self.watched}>"
