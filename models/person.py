from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin


class Person(TimestampMixin, Base):
    """An actor, director, writer, or producer associated with one or more
    projects, either as cast (via ProjectCast) or crew (via ProjectCrew)."""

    __tablename__ = "people"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(160), unique=True, nullable=False, index=True)
    photo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    birthday: Mapped[date | None] = mapped_column(Date, nullable=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)

    cast_credits: Mapped[list["ProjectCast"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )
    crew_credits: Mapped[list["ProjectCrew"]] = relationship(
        back_populates="person", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience only
        return f"<Person id={self.id} name={self.name!r}>"


class ProjectCast(Base):
    """Association object linking a Person to a Project as a cast member,
    carrying the character name and billing order for that specific project."""

    __tablename__ = "project_cast"
    __table_args__ = (
        UniqueConstraint("project_id", "person_id", "character_name", name="uq_cast_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[int] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), nullable=False, index=True
    )
    character_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    billing_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="cast")
    person: Mapped["Person"] = relationship(back_populates="cast_credits")


class ProjectCrew(Base):
    """Association object linking a Person to a Project as a crew member
    (director, writer, producer, composer, ...) with their role on that project."""

    __tablename__ = "project_crew"
    __table_args__ = (
        UniqueConstraint("project_id", "person_id", "role", name="uq_crew_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[int] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(64), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="crew")
    person: Mapped["Person"] = relationship(back_populates="crew_credits")
