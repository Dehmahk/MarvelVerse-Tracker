from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base

project_genres = Table(
    "project_genres",
    Base.metadata,
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("genre_id", ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)


class Genre(Base):
    """A canonical genre tag (Action, Sci-Fi, Comedy, ...). Many-to-many with
    Project. Distinct from user-defined Tags, which are personal organization."""

    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    projects: Mapped[list["Project"]] = relationship(
        secondary=project_genres, back_populates="genres"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience only
        return f"<Genre id={self.id} name={self.name!r}>"
