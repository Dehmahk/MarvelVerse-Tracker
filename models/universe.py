from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin


class Universe(TimestampMixin, Base):
    """A top-level continuity, e.g. Marvel Cinematic Universe, Sony's Spider-Man
    Universe, or the Fox X-Men Universe. Projects and franchises belong to one."""

    __tablename__ = "universes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    abbreviation: Mapped[str | None] = mapped_column(String(16), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    color_hex: Mapped[str | None] = mapped_column(String(7), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    franchises: Mapped[list["Franchise"]] = relationship(
        back_populates="universe",
        cascade="all, delete-orphan",
        order_by="Franchise.name",
    )
    projects: Mapped[list["Project"]] = relationship(
        back_populates="universe",
        order_by="Project.release_date",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience only
        return f"<Universe id={self.id} name={self.name!r}>"
