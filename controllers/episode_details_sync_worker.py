from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class EpisodeDetailsSyncWorker(QThread):
    """Runs services.episode_service.sync_episodes_from_tmdb() on a
    background thread -- same reasoning as every other TMDB-touching
    worker in this app: it's a real network call (one per season), so
    it must never run on the UI thread.
    """

    succeeded = Signal(int)  # the project_id that was synced
    failed = Signal(str)  # a human-readable error message

    def __init__(self, project_id: int, api_key: str, parent=None) -> None:
        super().__init__(parent)
        self._project_id = project_id
        self._api_key = api_key

    def run(self) -> None:  # noqa: D102 - QThread override
        from services.tmdb_client import TMDBError
        from services.episode_service import sync_episodes_from_tmdb

        try:
            sync_episodes_from_tmdb(self._project_id, self._api_key)
        except (ValueError, TMDBError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive catch-all
            self.failed.emit(f"Unexpected error: {exc}")
        else:
            self.succeeded.emit(self._project_id)
