from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

logger = logging.getLogger(__name__)

ImageCallback = Callable[["QPixmap | None"], None]


class PosterImageLoader(QObject):
    """Async, disk-cached loader for TMDB poster/backdrop art.

    Deliberately Qt-coupled (QPixmap, QNetworkAccessManager), so it lives
    in the views layer rather than services -- the services layer stays
    free of any GUI toolkit dependency, per the "views never touch the
    database/services layer" split the rest of the app follows in reverse.

    Every lookup is disk-cache-first: once a URL has been downloaded once,
    later requests for it are a synchronous local file read (fast, no
    network round trip, callback fires on the same tick). A cache miss is
    fetched via QNetworkAccessManager on Qt's own event loop, so it never
    blocks the UI thread; the response is written to the cache directory
    before the callback fires so subsequent requests are instant.
    """

    def __init__(self, cache_dir: Path) -> None:
        super().__init__()
        self._cache_dir = Path(cache_dir) / "posters"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._manager = QNetworkAccessManager(self)
        # url -> callbacks waiting on an in-flight request, so a burst of
        # widgets asking for the same poster at once (e.g. a Library page
        # rebuild) triggers exactly one network request instead of one per
        # widget.
        self._pending: dict[str, list[ImageCallback]] = {}
        # url -> the in-flight QNetworkReply, tracked purely so shutdown()
        # can abort and disconnect it -- see shutdown()'s docstring for why
        # that matters.
        self._replies: dict[str, QNetworkReply] = {}

    def _cache_path(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        suffix = Path(QUrl(url).path()).suffix or ".jpg"
        return self._cache_dir / f"{digest}{suffix}"

    def request(self, url: str | None, callback: ImageCallback) -> None:
        """Resolve `url` to a QPixmap and hand it to `callback(pixmap)`,
        asynchronously unless it's already cached on disk. Calls back with
        `None` if `url` is falsy or the image can't be fetched/decoded, so
        callers can fall back to their initials placeholder."""
        if not url:
            callback(None)
            return

        cache_path = self._cache_path(url)
        if cache_path.exists():
            pixmap = QPixmap(str(cache_path))
            callback(pixmap if not pixmap.isNull() else None)
            return

        if url in self._pending:
            self._pending[url].append(callback)
            return

        self._pending[url] = [callback]
        reply = self._manager.get(QNetworkRequest(QUrl(url)))
        self._replies[url] = reply
        reply.finished.connect(lambda: self._on_finished(url, cache_path, reply))

    def _on_finished(self, url: str, cache_path: Path, reply: QNetworkReply) -> None:
        self._replies.pop(url, None)
        callbacks = self._pending.pop(url, [])
        pixmap: QPixmap | None = None
        try:
            if reply.error() == QNetworkReply.NetworkError.NoError:
                raw = bytes(reply.readAll())
                candidate = QPixmap()
                if candidate.loadFromData(raw) and not candidate.isNull():
                    pixmap = candidate
                    try:
                        cache_path.write_bytes(raw)
                    except OSError:
                        logger.warning("Could not write poster cache file %s", cache_path)
            else:
                logger.debug("Poster download failed for %s: %s", url, reply.errorString())
        finally:
            reply.deleteLater()

        for callback in callbacks:
            callback(pixmap)

    def shutdown(self) -> None:
        """Abort every in-flight request and drop pending callbacks.

        Called by configure() before this loader is replaced as the
        module-level singleton (e.g. MainWindow gets rebuilt). Without
        this, an old QNetworkReply could still be in flight when its
        QNetworkAccessManager parent becomes unreachable and eligible for
        garbage collection -- and the reply's `finished` signal firing
        against a manager mid-teardown is exactly the kind of dangling
        C++-object callback that crashes rather than raising a clean
        Python exception.
        """
        for url, reply in list(self._replies.items()):
            reply.finished.disconnect()
            reply.abort()
            reply.deleteLater()
        self._replies.clear()
        self._pending.clear()


_loader: PosterImageLoader | None = None


def configure(cache_dir: Path) -> None:
    """Call once at startup (MainWindow.__init__, which already receives
    AppConfig) before any widget requests a poster. Safe to call again
    later (e.g. MainWindow rebuilt) -- any previous loader is shut down
    first so it can't leave a dangling in-flight request behind."""
    global _loader
    if _loader is not None:
        _loader.shutdown()
    _loader = PosterImageLoader(cache_dir)


def loader() -> PosterImageLoader | None:
    """The configured singleton, or None if configure() hasn't been
    called yet -- e.g. a unit test building a widget in isolation.
    Callers must treat None the same as "no image available"."""
    return _loader


def format_cache_size(size_bytes: int) -> str:
    """Human-readable byte count, e.g. "42.3 MB" -- same unit-stepping
    pattern as services.backup_service.BackupInfo.size_display."""
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def cache_size_bytes() -> int:
    """Total size, in bytes, of every cached poster file on disk. Used by
    the Settings > Data & Sync panel to show the user how much space the
    poster cache is using. Returns 0 if configure() hasn't been called yet
    or the cache directory doesn't exist (e.g. a fresh install that
    hasn't downloaded any posters)."""
    if _loader is None or not _loader._cache_dir.exists():
        return 0
    return sum(path.stat().st_size for path in _loader._cache_dir.iterdir() if path.is_file())


def clear_cache() -> int:
    """Delete every cached poster file on disk and return how many files
    were removed. Safe to call while the app is running -- posters
    already displayed on screen stay in memory (Qt already decoded them
    into QPixmaps), they just get re-downloaded next time they're
    requested (e.g. after navigating away and back, or restarting).
    No-ops (returns 0) if configure() hasn't been called yet or the
    cache directory doesn't exist."""
    if _loader is None or not _loader._cache_dir.exists():
        return 0
    removed = 0
    for path in _loader._cache_dir.iterdir():
        if path.is_file():
            try:
                path.unlink()
                removed += 1
            except OSError:
                logger.warning("Could not remove cached poster file %s", path)
    return removed
