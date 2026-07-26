from __future__ import annotations

import sys
from pathlib import Path


def resource_root() -> Path:
    """Where MarvelVerse Tracker's bundled, read-only resources live --
    ``themes/*.qss``, ``database/migrations/``, ``alembic.ini`` -- as
    opposed to ``settings.config.AppConfig``, which is about *writable*
    per-user data (the database, poster cache, logs, and settings file).

    Running from source (``python main.py``), these are simply relative
    to the project root (this file's own location). Packaged with
    PyInstaller, they're bundled as data files and extracted to a
    different location at runtime instead: ``sys._MEIPASS`` for a
    onefile build, or the folder the executable itself lives in for a
    onedir build -- see ``packaging/MarvelVerseTracker.spec``, which is
    responsible for actually including them.
    """
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent
