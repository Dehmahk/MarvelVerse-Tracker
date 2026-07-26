from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class TMDBSyncWorker(QThread):
    """Runs services.tmdb_sync_service.sync_from_tmdb() on a background
    thread.

    A real sync means dozens to hundreds of paginated TMDB API calls,
    each with real network latency -- running that on the UI thread (as
    every other service call in this app does) would freeze the entire
    window, with no repainting and no other page usable, for as long as
    the sync takes.

    Safe to run on a background thread: database.connection.init_engine()
    already sets check_same_thread=False and uses a thread-local
    scoped_session, specifically so a second thread doing its own,
    independent unit of work via session_scope() doesn't collide with
    whatever the main thread's session is doing.

    Emits exactly one of `succeeded`/`failed` when done, always followed
    by QThread's own built-in `finished` signal -- the controller
    connects to that last one to know it's safe to start a new sync and
    clear its reference to this worker.
    """

    succeeded = Signal(object)  # services.tmdb_sync_service.SyncResult
    failed = Signal(str)  # a human-readable error message

    def __init__(self, api_key: str, parent=None) -> None:
        super().__init__(parent)
        self._api_key = api_key

    def run(self) -> None:  # noqa: D102 - QThread override
        from services.tmdb_client import TMDBError
        from services.tmdb_sync_service import sync_from_tmdb

        try:
            result = sync_from_tmdb(self._api_key)
        except TMDBError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive catch-all
            self.failed.emit(f"Unexpected error: {exc}")
        else:
            self.succeeded.emit(result)
