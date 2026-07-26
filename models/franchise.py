from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin


class Franchise(TimestampMixin, Base):
    """A sub-grouping inside a Universe, e.g. Avengers, Spider-Man, X-Men,
    Guardians of the Galaxy. Used for filtering and grouping in the library."""

    __tablename__ = "franchises"

    id: Mapped[int] = mapped_column(primary_key=True)
    universe_id: Mapped[int] = mapped_column(
        ForeignKey("universes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    universe: Mapped["Universe"] = relationship(back_populates="franchises")
    projects: Mapped[list["Project"]] = relationship(
        back_populates="franchise",
        order_by="Project.release_date",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience only
        return f"<Franchise id={self.id} name={self.name!r}>"
