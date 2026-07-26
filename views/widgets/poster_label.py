from __future__ import annotations

import weakref

import shiboken6
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QLabel, QWidget

from views import image_loader


def poster_placeholder_text(title: str) -> str:
    words = [w for w in title.split() if w]
    letters = "".join(w[0].upper() for w in words[:2])
    return letters or "?"


def _rounded_and_cropped(pixmap: QPixmap, size: QSize, radius: int) -> QPixmap:
    """Center-crop `pixmap` to exactly `size` (aspect-fill, like CSS
    `object-fit: cover`) and clip it to rounded corners, so real poster
    art matches the same border-radius the QSS already applies to the
    placeholder frames around it."""
    scaled = pixmap.scaled(
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    x = max(0, (scaled.width() - size.width()) // 2)
    y = max(0, (scaled.height() - size.height()) // 2)
    cropped = scaled.copy(x, y, size.width(), size.height())

    result = QPixmap(size)
    result.fill(Qt.GlobalColor.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size.width(), size.height(), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, cropped)
    painter.end()
    return result


class PosterLabel(QLabel):
    """A QLabel that shows a title's initials until real poster/backdrop
    art has been fetched (from cache or network), then swaps to that
    artwork -- used everywhere a project's cover art appears: Library
    cards and rows, the Timeline, the Dashboard's Recently Watched list,
    and the Project Detail hero.

    Keeps the same objectName-driven placeholder styling from the QSS
    (color/font-size for the initials) until an image is available, so
    nothing needs to change on the stylesheet side for the placeholder
    case -- this widget is a drop-in replacement for the plain QLabel
    placeholders that used to live in each of those widgets.
    """

    def __init__(self, *, corner_radius: int = 0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._corner_radius = corner_radius
        self._request_token = 0

    def set_corner_radius(self, radius: int) -> None:
        self._corner_radius = radius

    def set_poster(self, url: str | None, title: str) -> None:
        """Show `title`'s initials immediately, then asynchronously
        replace them with the real artwork at `url` once it's available
        (from disk cache or network). Safe to call repeatedly on a reused
        widget (e.g. a recycled card) -- a newer call always wins over a
        still-in-flight older one."""
        self.setPixmap(QPixmap())
        self.setText(poster_placeholder_text(title))

        self._request_token += 1
        token = self._request_token

        active_loader = image_loader.loader()
        if active_loader is None or not url:
            return

        # A weakref (rather than the closure capturing `self` directly)
        # so an in-flight download doesn't keep a torn-down widget's
        # Python wrapper artificially alive, and shiboken6.isValid()
        # (rather than hoping a RuntimeError gets raised) so a reply that
        # completes after the widget's underlying C++ object has already
        # been destroyed -- e.g. the view was rebuilt while this
        # download was still in flight -- is detected reliably instead
        # of risking a crash from touching a dead widget.
        weak_self = weakref.ref(self)

        def _on_ready(pixmap: QPixmap | None) -> None:
            label = weak_self()
            if label is None or not shiboken6.isValid(label):
                return
            if token != label._request_token:
                return
            if pixmap is None or pixmap.isNull():
                return
            label._apply_pixmap(pixmap)

        active_loader.request(url, _on_ready)

    def _apply_pixmap(self, pixmap: QPixmap) -> None:
        size = self.size()
        if size.width() <= 0 or size.height() <= 0:
            size = self.sizeHint()
        self.setPixmap(_rounded_and_cropped(pixmap, size, self._corner_radius))
        self.setText("")
