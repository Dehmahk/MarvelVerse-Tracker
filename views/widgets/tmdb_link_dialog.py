from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

_RESULT_ROLE = Qt.ItemDataRole.UserRole


class TMDBLinkDialog(QDialog):
    """Shown after a "Find on TMDB" search completes -- lists the
    candidate matches (title, year, a short synopsis snippet) so the
    user can pick the right one to link this project to, or cancel if
    none of them are actually it.

    This app has no way to verify which result, if any, is correct --
    only the person using it can do that -- so this always requires an
    explicit pick, never guesses or auto-selects the first result.
    """

    def __init__(self, results, current_title: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Find on TMDB")
        self.setMinimumSize(460, 360)
        self.selected_result = None

        layout = QVBoxLayout(self)

        heading = QLabel(f'Results for "{current_title}":')
        layout.addWidget(heading)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.list_widget, 1)

        if not results:
            self.list_widget.hide()
            empty_label = QLabel(
                "No matches found on TMDB for this title. Try renaming the "
                "project to match its official title more closely, or check "
                "back after TMDB adds an entry for it."
            )
            empty_label.setWordWrap(True)
            layout.addWidget(empty_label)
        else:
            for result in results:
                year_text = f" ({result.year})" if result.year else ""
                snippet = f"\n{result.overview[:150]}" if result.overview else ""
                item = QListWidgetItem(f"{result.title}{year_text}{snippet}")
                item.setData(_RESULT_ROLE, result)
                self.list_widget.addItem(item)
            self.list_widget.setCurrentRow(0)

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self.cancel_button)

        self.link_button = QPushButton("Link Selected")
        self.link_button.setObjectName("primaryButton")
        self.link_button.setEnabled(bool(results))
        self.link_button.clicked.connect(self.accept)
        button_row.addWidget(self.link_button)

        layout.addLayout(button_row)

    def accept(self) -> None:  # noqa: D102 - QDialog override
        item = self.list_widget.currentItem()
        if item is not None:
            self.selected_result = item.data(_RESULT_ROLE)
        super().accept()
