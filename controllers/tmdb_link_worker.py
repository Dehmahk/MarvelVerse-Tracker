from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from models import ProjectType


class TMDBLinkWorker(QThread):
    """Runs services.tmdb_sync_service.link_project_to_tmdb() on a
    background thread -- same reasoning as TMDBSyncWorker/
    TMDBSearchWorker: pulling full details for one project is still a
    real network call.
    """

    succeeded = Signal(int)  # the project_id that was linked
    failed = Signal(str)  # a human-readable error message

    def __init__(
        self,
        project_id: int,
        tmdb_id: int,
        project_type: ProjectType,
        api_key: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._project_id = project_id
        self._tmdb_id = tmdb_id
        self._project_type = project_type
        self._api_key = api_key

    def run(self) -> None:  # noqa: D102 - QThread override
        from services.tmdb_client import TMDBError
        from services.tmdb_sync_service import link_project_to_tmdb

        try:
            link_project_to_tmdb(self._project_id, self._tmdb_id, self._project_type, self._api_key)
        except TMDBError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive catch-all
            self.failed.emit(f"Unexpected error: {exc}")
        else:
            self.succeeded.emit(self._project_id)
