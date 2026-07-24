from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal


class UpdateDownloadWorker(QThread):
    """Runs services.update_service.download_update() on a background
    thread -- streaming a whole executable over the network is exactly
    the kind of thing that must never run on the UI thread, same
    reasoning as TMDBSyncWorker.
    """

    succeeded = Signal(object)  # Path -- where the new .exe was saved
    failed = Signal(str)  # a human-readable error message

    def __init__(self, info, destination: Path, parent=None) -> None:
        super().__init__(parent)
        self._info = info
        self._destination = destination

    def run(self) -> None:  # noqa: D102 - QThread override
        from services.update_service import download_update

        try:
            path = download_update(self._info, self._destination)
        except Exception as exc:  # pragma: no cover - defensive catch-all
            self.failed.emit(str(exc))
        else:
            self.succeeded.emit(path)
