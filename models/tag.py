from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base

project_tags = Table(
    "project_tags",
    Base.metadata,
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    """A user-defined organizational label (e.g. 'Must Rewatch', 'Filler',
    'Post-Credits Only'). Unlike Genre, tags are personal and freely created."""

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    color_hex: Mapped[str | None] = mapped_column(String(7), nullable=True)

    projects: Mapped[list["Project"]] = relationship(
        secondary=project_tags, back_populates="tags"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience only
        return f"<Tag id={self.id} name={self.name!r}>"
