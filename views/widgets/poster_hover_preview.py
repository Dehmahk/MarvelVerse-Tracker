from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from views.widgets.poster_label import PosterLabel

_PREVIEW_WIDTH = 220
_PREVIEW_HEIGHT = 320


class PosterHoverPreview(QFrame):
    """A larger poster popup shown after hovering a Library card for a
    moment, so you can get a better look at the art without leaving the
    grid to open the full Project Details page. A tooltip-style window
    (frameless, doesn't steal focus, doesn't appear in the taskbar) --
    same category of window as a real tooltip, just with an image in it
    instead of text.
    """

    def __init__(self) -> None:
        super().__init__(
            None,
            Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setObjectName("posterHoverPreview")
        # Shows without stealing keyboard focus from whatever the user
        # was actually interacting with -- exactly what a real tooltip
        # does, and for the same reason (it's a passive glance, not an
        # interaction).
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self.poster = PosterLabel(corner_radius=8)
        self.poster.setFixedSize(_PREVIEW_WIDTH, _PREVIEW_HEIGHT)
        layout.addWidget(self.poster)

        self.title_label = QLabel("")
        self.title_label.setObjectName("posterHoverPreviewTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setFixedWidth(_PREVIEW_WIDTH)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.title_label)

    def show_for(self, poster_path: str | None, title: str, anchor_global_pos: QPoint) -> None:
        """Populates the preview and shows it positioned near
        `anchor_global_pos` (a global-coordinates point, typically just
        outside the hovered card) -- clamped to stay fully on-screen
        rather than showing it half off the edge of the display."""
        self.poster.set_poster(poster_path, title)
        self.title_label.setText(title)
        self.adjustSize()

        screen = QGuiApplication.screenAt(anchor_global_pos) or QGuiApplication.primaryScreen()
        screen_rect = screen.availableGeometry() if screen else None

        x = anchor_global_pos.x()
        y = anchor_global_pos.y()
        if screen_rect is not None:
            x = min(x, screen_rect.right() - self.width())
            y = min(y, screen_rect.bottom() - self.height())
            x = max(x, screen_rect.left())
            y = max(y, screen_rect.top())

        self.move(x, y)
        self.show()
