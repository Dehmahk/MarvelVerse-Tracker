from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base, TimestampMixin


class Collection(TimestampMixin, Base):
    """A user-curated, ordered group of projects, e.g. 'Infinity Saga Ranked'
    or 'Weekend Marathon'. Distinct from Universe/Franchise, which are
    canonical groupings synced from reference data."""

    __tablename__ = "collections"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_smart: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    project_links: Mapped[list["CollectionProject"]] = relationship(
        back_populates="collection",
        cascade="all, delete-orphan",
        order_by="CollectionProject.position",
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience only
        return f"<Collection id={self.id} name={self.name!r}>"


class CollectionProject(Base):
    """Association object linking a Project to a Collection with an explicit
    manual ordering position (drag-to-reorder in the UI)."""

    __tablename__ = "collection_projects"
    __table_args__ = (
        UniqueConstraint("collection_id", "project_id", name="uq_collection_project"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    collection_id: Mapped[int] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    collection: Mapped["Collection"] = relationship(back_populates="project_links")
    project: Mapped["Project"] = relationship(back_populates="collection_links")
