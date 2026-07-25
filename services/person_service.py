"""Actor/Director detail pages -- a person's bio/photo plus every project
in the catalog they appear in, whether as cast or crew.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from database import session_scope
from models import Person, ProjectCast, ProjectCrew, ProjectType


@dataclass(frozen=True)
class PersonCredit:
    """One project a person is credited on -- either `character_name` or
    `crew_role` is set, never both (a person could in principle have
    both a cast and crew credit on the same project, e.g. an actor who
    also directed; that shows up as two separate PersonCredit entries
    rather than one merged one, since they're fundamentally different
    kinds of contribution)."""

    project_id: int
    title: str
    project_type: ProjectType
    poster_path: str | None
    release_date: date | None
    character_name: str | None
    crew_role: str | None


@dataclass(frozen=True)
class PersonDetail:
    """A flat, detached-safe read model for the Actor/Director Details
    page, built entirely inside the owning session_scope."""

    id: int
    name: str
    photo_path: str | None
    bio: str | None
    birthday: date | None
    cast_credits: tuple[PersonCredit, ...]
    crew_credits: tuple[PersonCredit, ...]

    @property
    def total_credits(self) -> int:
        return len(self.cast_credits) + len(self.crew_credits)


def _newest_first_sort_key(credit: PersonCredit) -> tuple[bool, int]:
    """Dated credits sort newest-first; undated ones (announced, no
    release date yet) always sort last, regardless of how this key is
    used -- ascending sort on (is_undated, -ordinal) achieves both at
    once: dated (False) sorts before undated (True), and among dated
    credits, a larger (less negative) ordinal -- i.e. a more recent
    date -- sorts first."""
    if credit.release_date is None:
        return (True, 0)
    return (False, -credit.release_date.toordinal())


def get_person_detail(person_id: int) -> PersonDetail | None:
    """None if no person with that id exists."""
    with session_scope() as session:
        person = session.scalar(
            select(Person)
            .options(
                joinedload(Person.cast_credits).joinedload(ProjectCast.project),
                joinedload(Person.crew_credits).joinedload(ProjectCrew.project),
            )
            .where(Person.id == person_id)
        )
        if person is None:
            return None

        cast_credits = tuple(
            PersonCredit(
                project_id=c.project.id,
                title=c.project.title,
                project_type=c.project.project_type,
                poster_path=c.project.poster_path,
                release_date=c.project.release_date,
                character_name=c.character_name,
                crew_role=None,
            )
            for c in person.cast_credits
        )
        crew_credits = tuple(
            PersonCredit(
                project_id=c.project.id,
                title=c.project.title,
                project_type=c.project.project_type,
                poster_path=c.project.poster_path,
                release_date=c.project.release_date,
                character_name=None,
                crew_role=c.role,
            )
            for c in person.crew_credits
        )

        return PersonDetail(
            id=person.id,
            name=person.name,
            photo_path=person.photo_path,
            bio=person.bio,
            birthday=person.birthday,
            cast_credits=tuple(sorted(cast_credits, key=_newest_first_sort_key)),
            crew_credits=tuple(sorted(crew_credits, key=_newest_first_sort_key)),
        )
