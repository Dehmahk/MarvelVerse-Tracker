from __future__ import annotations

from datetime import date, datetime

"""Presentation-only rating/date formatting, driven by the Personalization
and Privacy preferences on the Settings page.

Follows the same "module-level singleton, configure() once" pattern as
views.image_loader: these are display concerns with no database/service
involvement, so a view-layer module (not a service) owns them, and every
widget that shows a rating or a date (Timeline markers, Library rows,
Dashboard's Recently Watched panel, Project Details) pulls from the same
configured preferences rather than each re-deriving them from AppConfig
itself.
"""

_prefs = {
    "date_format": "mdy",
    "rating_scale": "ten",
    "mask_ratings": False,
}


def configure(*, date_format: str = "mdy", rating_scale: str = "ten", mask_ratings: bool = False) -> None:
    """Call once at startup (MainWindow.__init__) and again any time the
    Personalization/Privacy panels are saved, so every already-built widget
    picks up the new preference the next time it re-renders."""
    _prefs["date_format"] = date_format
    _prefs["rating_scale"] = rating_scale
    _prefs["mask_ratings"] = mask_ratings


def current_date_format() -> str:
    return _prefs["date_format"]


def current_rating_scale() -> str:
    return _prefs["rating_scale"]


def ratings_masked() -> bool:
    return _prefs["mask_ratings"]


def format_long_date(value: date | datetime | None) -> str:
    """A full "Month Day, Year" (or "Day Month Year" for the ``dmy``
    preference) date, or "TBA" for an unreleased/undated project -- the
    style used by Project Details' release-date fact and watch-history
    entries."""
    if value is None:
        return "TBA"
    pattern = "%d %B %Y" if _prefs["date_format"] == "dmy" else "%B %d, %Y"
    return value.strftime(pattern)


def format_short_date(value: date | datetime | None) -> str:
    """An abbreviated-month date (or "" for ``None``), the style used by
    the Dashboard's Recently Watched panel and the Settings backups list."""
    if value is None:
        return ""
    pattern = "%d %b %Y" if _prefs["date_format"] == "dmy" else "%b %d, %Y"
    return value.strftime(pattern)


def format_rating(rating: float | None) -> str:
    """A rating (stored as a 0-10 float, same as the rating input control
    itself, which this does not change) formatted for display according to
    the ``rating_scale`` preference, or masked entirely per
    ``mask_ratings``. Callers that prefix their own symbol (e.g. Timeline's
    "★ 8.5") should use this for the numeric/symbol part only where noted;
    this function includes its own star/thumb glyph for the "five_star"/
    "thumbs" scales since those glyphs differ from the plain "ten" scale's
    bare number."""
    if _prefs["mask_ratings"]:
        return "🔒"
    if rating is None:
        return "—"
    scale = _prefs["rating_scale"]
    if scale == "five_star":
        return f"{rating / 2:.1f} ★"
    if scale == "thumbs":
        return "👍" if rating >= 5 else "👎"
    return f"★ {rating:.1f}"
