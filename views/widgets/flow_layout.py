from __future__ import annotations

from PySide6.QtCore import QMargins, QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QSizePolicy, QWidget


class FlowLayout(QLayout):
    """A layout that arranges its children left-to-right, wrapping to a new
    row when it runs out of horizontal space. Qt has no built-in equivalent;
    this is the standard adaptation of Qt's own "Flow Layout" example.

    Used by the Library view's grid/poster modes so cards reflow naturally
    as the window (or the sidebar) is resized, instead of being locked to a
    fixed column count.
    """

    def __init__(self, parent: QWidget | None = None, margin: int = 0, spacing: int = 12) -> None:
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(QMargins(margin, margin, margin, margin))
        self.setSpacing(spacing)
        self._items: list[QLayoutItem] = []

    def __del__(self) -> None:
        while self.count():
            self.takeAt(0)

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(
            margins.left() + margins.right(),
            margins.top() + margins.bottom(),
        )
        return size

    def _do_layout(self, rect: QRect, *, test_only: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effective_rect = rect.adjusted(left, top, -right, -bottom)
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0
        spacing = self.spacing()

        for item in self._items:
            widget = item.widget()
            if widget is not None and not widget.isVisibleTo(self.parentWidget()):
                continue

            item_size = item.sizeHint()
            next_x = x + item_size.width() + spacing

            if next_x - spacing > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + spacing
                next_x = x + item_size.width() + spacing
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item_size))

            x = next_x
            line_height = max(line_height, item_size.height())

        return y + line_height - rect.y() + bottom
