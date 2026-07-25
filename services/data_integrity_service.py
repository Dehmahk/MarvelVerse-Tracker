"""Audits the catalog for likely data-quality problems -- duplicate
projects, missing fields, and universe/franchise assignments that don't
line up with each other. Given how much of this catalog was entered by
hand (rather than exclusively through TMDB sync), these are the kinds
of mistakes that are easy to make and easy to miss without deliberately
checking for them.

This is read-only: it only reports issues, it never fixes anything
automatically. Automatically "fixing" a likely duplicate or a
mismatched universe assignment risks being wrong in a way a human
wouldn't be, so every issue here is something for a person to look at
and decide on themselves.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select

from database import session_scope
from models import Franchise, Project, ProjectCast, ProjectCrew


class IntegrityIssueType(str, Enum):
    DUPLICATE_TITLE_AND_YEAR = "duplicate_title_and_year"
    DUPLICATE_TMDB_ID = "duplicate_tmdb_id"
    DUPLICATE_SLUG = "duplicate_slug"
    MISSING_SYNOPSIS = "missing_synopsis"
    MISSING_GENRES = "missing_genres"
    MISSING_CAST = "missing_cast"
    MISSING_RUNTIME = "missing_runtime"
    FRANCHISE_UNIVERSE_MISMATCH = "franchise_universe_mismatch"


@dataclass(frozen=True)
class IntegrityIssue:
    """One flagged issue -- `project_ids` holds every project involved
    (more than one for duplicate-style issues, exactly one otherwise)."""

    issue_type: IntegrityIssueType
    description: str
    project_ids: tuple[int, ...]


def check_data_integrity() -> tuple[IntegrityIssue, ...]:
    """Runs every check below in one pass and returns everything found,
    in no particular priority order -- the caller decides how to group
    or triage them. Safe to call anytime; this never modifies data."""
    issues: list[IntegrityIssue] = []

    with session_scope() as session:
        projects = session.execute(select(Project)).scalars().all()

        issues.extend(_check_duplicate_title_and_year(projects))
        issues.extend(_check_duplicate_tmdb_id(projects))
        issues.extend(_check_duplicate_slug(projects))
        issues.extend(_check_missing_fields(session, projects))
        issues.extend(_check_franchise_universe_mismatch(session, projects))

    return tuple(issues)


def _check_duplicate_title_and_year(projects) -> list[IntegrityIssue]:
    """Same title *and* same release year is a strong signal of an
    accidental duplicate entry -- unlike title alone (several genuinely
    different films share a title, e.g. the three different "Fantastic
    Four" movies in this catalog, but never in the same year)."""
    groups: dict[tuple[str, int], list[Project]] = defaultdict(list)
    for project in projects:
        if project.release_date is None:
            continue
        key = (project.title.strip().lower(), project.release_date.year)
        groups[key].append(project)

    issues = []
    for (title, year), group in groups.items():
        if len(group) > 1:
            issues.append(
                IntegrityIssue(
                    issue_type=IntegrityIssueType.DUPLICATE_TITLE_AND_YEAR,
                    description=f'Possible duplicate: "{group[0].title}" ({year}) appears {len(group)} times.',
                    project_ids=tuple(p.id for p in group),
                )
            )
    return issues


def _check_duplicate_tmdb_id(projects) -> list[IntegrityIssue]:
    groups: dict[int, list[Project]] = defaultdict(list)
    for project in projects:
        if project.tmdb_id is not None:
            groups[project.tmdb_id].append(project)

    issues = []
    for tmdb_id, group in groups.items():
        if len(group) > 1:
            titles = ", ".join(f'"{p.title}"' for p in group)
            issues.append(
                IntegrityIssue(
                    issue_type=IntegrityIssueType.DUPLICATE_TMDB_ID,
                    description=f"tmdb_id {tmdb_id} is linked to {len(group)} different projects: {titles}.",
                    project_ids=tuple(p.id for p in group),
                )
            )
    return issues


def _check_duplicate_slug(projects) -> list[IntegrityIssue]:
    """Slugs have a unique DB constraint, so this should be structurally
    impossible -- kept anyway as a defensive check in case that
    constraint is ever loosened or bypassed (e.g. a direct SQL import)."""
    groups: dict[str, list[Project]] = defaultdict(list)
    for project in projects:
        groups[project.slug].append(project)

    issues = []
    for slug, group in groups.items():
        if len(group) > 1:
            issues.append(
                IntegrityIssue(
                    issue_type=IntegrityIssueType.DUPLICATE_SLUG,
                    description=f'Slug "{slug}" is used by {len(group)} different projects.',
                    project_ids=tuple(p.id for p in group),
                )
            )
    return issues


def _check_missing_fields(session, projects) -> list[IntegrityIssue]:
    """Only checks RELEASED projects -- an announced/upcoming/
    in-production project genuinely may not have a synopsis, genres,
    cast, or runtime yet, and that's expected, not a data problem."""
    from models import ProjectStatus

    issues = []
    for project in projects:
        if project.status != ProjectStatus.RELEASED:
            continue

        if not project.synopsis:
            issues.append(
                IntegrityIssue(
                    issue_type=IntegrityIssueType.MISSING_SYNOPSIS,
                    description=f'"{project.title}" has no synopsis.',
                    project_ids=(project.id,),
                )
            )
        if not project.genres:
            issues.append(
                IntegrityIssue(
                    issue_type=IntegrityIssueType.MISSING_GENRES,
                    description=f'"{project.title}" has no genres assigned.',
                    project_ids=(project.id,),
                )
            )
        if not project.runtime_minutes:
            issues.append(
                IntegrityIssue(
                    issue_type=IntegrityIssueType.MISSING_RUNTIME,
                    description=f'"{project.title}" has no runtime set.',
                    project_ids=(project.id,),
                )
            )

    project_ids_with_cast = {
        row[0] for row in session.execute(select(ProjectCast.project_id).distinct())
    }
    for project in projects:
        if project.status != ProjectStatus.RELEASED:
            continue
        if project.id not in project_ids_with_cast:
            issues.append(
                IntegrityIssue(
                    issue_type=IntegrityIssueType.MISSING_CAST,
                    description=f'"{project.title}" has no cast listed.',
                    project_ids=(project.id,),
                )
            )

    return issues


def _check_franchise_universe_mismatch(session, projects) -> list[IntegrityIssue]:
    """A project's own universe_id doesn't have to match its
    franchise's universe_id -- that's a deliberate, supported pattern in
    this catalog (e.g. Spider-Man 3 is filed under the Marvel Multiverse
    universe but the Venom franchise, whose own "home" universe is
    SpiderVerse). This only flags it when *most* of a franchise's
    members disagree with the franchise's own universe, which is a much
    stronger signal of an actual mistake (the franchise assigned to the
    wrong universe entirely, or a batch of projects assigned to the
    wrong franchise) than one or two deliberate exceptions."""
    franchises = session.execute(select(Franchise)).scalars().all()
    projects_by_franchise: dict[int, list[Project]] = defaultdict(list)
    for project in projects:
        if project.franchise_id is not None:
            projects_by_franchise[project.franchise_id].append(project)

    issues = []
    for franchise in franchises:
        members = projects_by_franchise.get(franchise.id, [])
        if len(members) < 2:
            continue
        mismatched = [p for p in members if p.universe_id != franchise.universe_id]
        if len(mismatched) > len(members) / 2:
            issues.append(
                IntegrityIssue(
                    issue_type=IntegrityIssueType.FRANCHISE_UNIVERSE_MISMATCH,
                    description=(
                        f'"{franchise.name}" franchise: {len(mismatched)} of {len(members)} '
                        "member projects belong to a different universe than the franchise "
                        "itself -- worth checking whether the franchise (or these projects) "
                        "are filed under the right universe."
                    ),
                    project_ids=tuple(p.id for p in mismatched),
                )
            )
    return issues
