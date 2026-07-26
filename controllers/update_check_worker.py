from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class UpdateCheckWorker(QThread):
    """Runs services.update_service.check_for_update() on a background
    thread -- it's a network call to GitHub's API, and even though it's
    normally fast, "normally fast" isn't a guarantee a UI thread should
    ever be betting on. Same reasoning as TMDBSyncWorker.

    Always emits exactly one `finished_checking` signal -- with an
    UpdateInfo if a newer version is available, or None if not (no
    update, network failure, or the repo isn't configured yet all look
    the same to a caller: nothing to do).
    """

    finished_checking = Signal(object)  # UpdateInfo | None

    def __init__(self, current_version: str, repo: str, parent=None) -> None:
        super().__init__(parent)
        self._current_version = current_version
        self._repo = repo

    def run(self) -> None:  # noqa: D102 - QThread override
        from services.update_service import check_for_update

        result = check_for_update(self._current_version, self._repo)
        self.finished_checking.emit(result)
