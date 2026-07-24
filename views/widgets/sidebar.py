from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QListWidget, QListWidgetItem, QVBoxLayout

SIDEBAR_EXPANDED_WIDTH = 240
SIDEBAR_COLLAPSED_WIDTH = 72

_ROLE_ICON = Qt.ItemDataRole.UserRole
_ROLE_LABEL = Qt.ItemDataRole.UserRole + 1

NAV_ENTRIES: list[tuple[str, str, str]] = [
    # (icon, label, page_title) - page_title is what the toolbar displays
    ("⌂", "Dashboard", "Dashboard"),
    ("▦", "Library", "Library"),
    ("◷", "Timeline", "Timeline"),
    ("▣", "Collections", "Collections"),
    ("🏆", "Achievements", "Achievements"),
    ("⚙", "Settings", "Settings"),
]


class Sidebar(QFrame):
    """Primary navigation. Purely presentational — it knows nothing about
    the database or services, only that rows map to page indices."""

    navigate = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("sidebar")
        self._collapsed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 20, 12, 20)

        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setSpacing(6)

        for icon, label, _page_title in NAV_ENTRIES:
            item = QListWidgetItem(f"{icon}   {label}")
            item.setData(_ROLE_ICON, icon)
            item.setData(_ROLE_LABEL, label)
            self.navigation.addItem(item)

        self.navigation.currentRowChanged.connect(self.navigate.emit)
        self.navigation.setCurrentRow(0)

        layout.addWidget(self.navigation)

        self.set_collapsed(False)

    def page_title(self, index: int) -> str:
        if 0 <= index < len(NAV_ENTRIES):
            return NAV_ENTRIES[index][2]
        return ""

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.setFixedWidth(SIDEBAR_COLLAPSED_WIDTH if collapsed else SIDEBAR_EXPANDED_WIDTH)

        for row in range(self.navigation.count()):
            item = self.navigation.item(row)
            icon = item.data(_ROLE_ICON)
            label = item.data(_ROLE_LABEL)
            item.setText(icon if collapsed else f"{icon}   {label}")
            item.setToolTip(label if collapsed else "")

    def is_collapsed(self) -> bool:
        return self._collapsed
