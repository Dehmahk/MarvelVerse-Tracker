from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout


class DataIntegrityDialog(QDialog):
    """Shows the results of services.data_integrity_service.check_data_integrity()
    -- purely informational, since the check itself never modifies
    anything. Just a single "Close" button; there's nothing to pick or
    confirm here, unlike TMDBLinkDialog."""

    def __init__(self, issues, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Data Integrity Check")
        self.setMinimumSize(520, 400)

        layout = QVBoxLayout(self)

        if not issues:
            heading = QLabel("No issues found. Your library looks clean!")
        else:
            count_text = "1 issue found." if len(issues) == 1 else f"{len(issues)} issues found."
            heading = QLabel(f"{count_text} This check is read-only -- nothing has been changed.")
        heading.setWordWrap(True)
        layout.addWidget(heading)

        if issues:
            list_widget = QListWidget()
            for issue in issues:
                list_widget.addItem(QListWidgetItem(issue.description))
            layout.addWidget(list_widget, 1)

        button_row = QHBoxLayout()
        button_row.addStretch()
        close_button = QPushButton("Close")
        close_button.setObjectName("primaryButton")
        close_button.clicked.connect(self.accept)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)
