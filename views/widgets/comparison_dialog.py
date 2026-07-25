from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


def _format_item(item) -> str:
    if item.my_rating is not None and item.friend_rating is not None:
        return f"{item.title}  (you: {item.my_rating:g}, them: {item.friend_rating:g})"
    if item.my_rating is not None:
        return f"{item.title}  (you: {item.my_rating:g})"
    if item.friend_rating is not None:
        return f"{item.title}  (them: {item.friend_rating:g})"
    return item.title


def _build_list_tab(items) -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    if not items:
        empty = QLabel("Nothing here.")
        empty.setObjectName("emptyState")
        layout.addWidget(empty)
        return widget

    list_widget = QListWidget()
    for item in items:
        list_widget.addItem(QListWidgetItem(_format_item(item)))
    layout.addWidget(list_widget)
    return widget


class ComparisonDialog(QDialog):
    """Shows the results of services.comparison_service.compare_with_friend_export()
    -- purely informational, read-only on both sides. Takes a duck-typed
    ComparisonResult."""

    def __init__(self, result, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Compare with a Friend")
        self.setMinimumSize(520, 440)

        layout = QVBoxLayout(self)

        summary = QLabel(
            f"You've both seen {len(result.both_watched)} of the "
            f"{len(result.both_watched) + len(result.only_me_watched) + len(result.only_friend_watched)} "
            f"things either of you has watched ({result.overlap_percent}% overlap)."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        tabs = QTabWidget()
        tabs.addTab(_build_list_tab(result.both_watched), f"You've Both Seen ({len(result.both_watched)})")
        tabs.addTab(_build_list_tab(result.only_me_watched), f"Only You've Seen ({len(result.only_me_watched)})")
        tabs.addTab(
            _build_list_tab(result.only_friend_watched), f"Only They've Seen ({len(result.only_friend_watched)})"
        )
        layout.addWidget(tabs, 1)

        neither_label = QLabel(f"Neither of you has watched {result.neither_watched_count} other things.")
        neither_label.setObjectName("statSubtitle")
        layout.addWidget(neither_label)

        button_row = QHBoxLayout()
        button_row.addStretch()
        close_button = QPushButton("Close")
        close_button.setObjectName("primaryButton")
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)
