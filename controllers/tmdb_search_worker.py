from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from models import ProjectType


class TMDBSearchWorker(QThread):
    """Runs services.tmdb_sync_service.search_tmdb() on a background
    thread -- same reasoning as TMDBSyncWorker: it's a network call, so
    it must never run on the UI thread.

    Used by the "Find on TMDB" flow (see project_detail_view.py and
    ApplicationController._on_find_on_tmdb_requested): unlike the
    automatic sync, which only ever discovers titles under Marvel
    Studios' own TMDB company entry, this searches TMDB directly by
    title, so it can find a project made by any studio (Fox, Sony, New
    Line, ...) -- the user then picks the correct match themselves out
    of the results, since only they can actually verify which one (if
    any) is right.
    """

    succeeded = Signal(object)  # list[services.tmdb_sync_service.TMDBSearchResult]
    failed = Signal(str)  # a human-readable error message

    def __init__(self, api_key: str, query: str, project_type: ProjectType, parent=None) -> None:
        super().__init__(parent)
        self._api_key = api_key
        self._query = query
        self._project_type = project_type

    def run(self) -> None:  # noqa: D102 - QThread override
        from services.tmdb_client import TMDBClient, TMDBError
        from services.tmdb_sync_service import search_tmdb

        try:
            client = TMDBClient(self._api_key)
            results = search_tmdb(client, self._query, self._project_type)
        except TMDBError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive catch-all
            self.failed.emit(f"Unexpected error: {exc}")
        else:
            self.succeeded.emit(results)
