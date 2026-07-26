"""Calendar page data -- every project in the catalog with a known
release date, for month-by-month browsing (not just the Dashboard's
"Coming Soon" strip, which only looks forward from today).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from database import session_scope
from models import Project, ProjectStatus, ProjectType


@dataclass(frozen=True)
class CalendarProject:
    """One dated project, for a single day on the Calendar page."""

    project_id: int
    title: str
    project_type: ProjectType
    status: ProjectStatus
    poster_path: str | None
    release_date: date


def get_calendar_projects() -> tuple[CalendarProject, ...]:
    """Every project with a release_date set, across all time -- past
    and future alike, so the Calendar page can page back through
    history or forward through announced releases without a separate
    backend call for each. Ordered by date; the view itself groups
    these by month/day locally (same "fetch once, re-render locally on
    navigation" pattern the Achievements sort toggle and Dashboard's
    Universe/Phase toggle already use), since re-querying on every
    single month-navigation click would be wasteful for a catalog this
    size.
    """
    with session_scope() as session:
        rows = session.execute(
            select(Project)
            .where(Project.release_date.is_not(None))
            .order_by(Project.release_date.asc())
        ).scalars().all()

        return tuple(
            CalendarProject(
                project_id=p.id,
                title=p.title,
                project_type=p.project_type,
                status=p.status,
                poster_path=p.poster_path,
                release_date=p.release_date,
            )
            for p in rows
        )
