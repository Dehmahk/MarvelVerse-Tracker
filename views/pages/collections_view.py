from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QStackedLayout,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from views.formatting import format_rating
from views.widgets.project_card import _STATUS_LABELS, _TYPE_LABELS, _enum_value

_PROJECT_ID_ROLE = Qt.ItemDataRole.UserRole


class CollectionsView(QWidget):
    """User-curated Collections: a master-detail page, list of collections
    on the left, the selected one's member projects (in manual order) on
    the right.

    Duck-typed the same way every other page is -- it only ever sees
    plain primitives in (ids, names, strings) and detached
    services.collection_service read models out (CollectionSummary,
    CollectionDetail), never a live ORM instance and never a database
    call of its own. Confirming a collection delete is handled directly
    in this view (like Settings' backup delete), but unconditionally --
    unlike backups, there's no Settings toggle scoped to collections
    specifically, and deleting one is destructive enough to always be
    worth a second look.
    """

    create_collection_requested = Signal(str, str)  # name, description
    collection_selected = Signal(int)  # collection_id
    rename_collection_requested = Signal(int, str, str)  # collection_id, name, description
    delete_collection_requested = Signal(int)  # collection_id
    add_project_requested = Signal(int, int)  # collection_id, project_id
    remove_project_requested = Signal(int, int)  # collection_id, project_id
    move_project_requested = Signal(int, int, str)  # collection_id, project_id, "up"/"down"
    project_activated = Signal(int)  # project_id

    def __init__(self) -> None:
        super().__init__()
        self._current_collection_id: int | None = None
        self._pickable_projects: list[tuple[int, str]] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 32)
        outer.setSpacing(16)

        heading = QLabel("Collections")
        heading.setObjectName("pageHeading")
        subtitle = QLabel(
            "Group projects into your own curated, manually-ordered lists -- "
            "a rewatch marathon, a personal ranking, whatever you like."
        )
        subtitle.setObjectName("pageSubtitle")
        subtitle.setWordWrap(True)
        outer.addWidget(heading)
        outer.addWidget(subtitle)

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self._build_list_panel())
        body.addWidget(self._build_detail_panel(), 1)
        outer.addLayout(body, 1)

    # --- construction helpers ------------------------------------------------

    def _build_list_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentPanel")
        panel.setFixedWidth(300)

        layout = QVBoxLayout(panel)
        layout.setSpacing(12)

        title = QLabel("Your Collections")
        title.setObjectName("sectionHeading")
        layout.addWidget(title)

        self.collections_list = QListWidget()
        self.collections_list.setObjectName("backupsList")
        self.collections_list.currentRowChanged.connect(self._on_collection_row_changed)
        layout.addWidget(self.collections_list, 1)

        self.new_collection_name_input = QLineEdit()
        self.new_collection_name_input.setObjectName("searchBox")
        self.new_collection_name_input.setPlaceholderText("New collection name")
        self.new_collection_name_input.returnPressed.connect(self._on_create_clicked)
        layout.addWidget(self.new_collection_name_input)

        self.create_collection_button = QPushButton("Create Collection")
        self.create_collection_button.setObjectName("primaryButton")
        self.create_collection_button.clicked.connect(self._on_create_clicked)
        layout.addWidget(self.create_collection_button)

        return panel

    def _build_detail_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("contentPanel")

        self._detail_stack = QStackedLayout(panel)

        empty_state = QLabel(
            "Select a collection on the left, or create a new one, to see its projects here."
        )
        empty_state.setObjectName("emptyState")
        empty_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_state.setWordWrap(True)
        self._detail_stack.addWidget(empty_state)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setSpacing(12)

        name_row = QHBoxLayout()
        name_row.setSpacing(10)
        self.detail_name_input = QLineEdit()
        self.detail_name_input.setObjectName("searchBox")
        self.detail_name_input.setPlaceholderText("Collection name")
        name_row.addWidget(self.detail_name_input, 1)

        self.save_details_button = QPushButton("Save")
        self.save_details_button.setObjectName("secondaryButton")
        self.save_details_button.clicked.connect(self._on_save_details_clicked)
        name_row.addWidget(self.save_details_button)

        self.delete_collection_button = QPushButton("Delete Collection")
        self.delete_collection_button.setObjectName("secondaryButton")
        self.delete_collection_button.clicked.connect(self._on_delete_collection_clicked)
        name_row.addWidget(self.delete_collection_button)
        detail_layout.addLayout(name_row)

        self.detail_description_input = QTextEdit()
        self.detail_description_input.setObjectName("notesEdit")
        self.detail_description_input.setPlaceholderText("Description (optional)")
        self.detail_description_input.setFixedHeight(60)
        detail_layout.addWidget(self.detail_description_input)

        projects_label = QLabel("Projects")
        projects_label.setObjectName("sectionHeading")
        detail_layout.addWidget(projects_label)

        self.projects_list = QListWidget()
        self.projects_list.setObjectName("backupsList")
        self.projects_list.itemDoubleClicked.connect(self._on_project_double_clicked)
        detail_layout.addWidget(self.projects_list, 1)

        project_button_row = QHBoxLayout()
        project_button_row.setSpacing(10)

        self.move_up_button = QPushButton("Move Up")
        self.move_up_button.setObjectName("secondaryButton")
        self.move_up_button.clicked.connect(lambda: self._on_move_clicked("up"))
        project_button_row.addWidget(self.move_up_button)

        self.move_down_button = QPushButton("Move Down")
        self.move_down_button.setObjectName("secondaryButton")
        self.move_down_button.clicked.connect(lambda: self._on_move_clicked("down"))
        project_button_row.addWidget(self.move_down_button)

        self.remove_project_button = QPushButton("Remove from Collection")
        self.remove_project_button.setObjectName("secondaryButton")
        self.remove_project_button.clicked.connect(self._on_remove_clicked)
        project_button_row.addWidget(self.remove_project_button)

        project_button_row.addStretch()
        detail_layout.addLayout(project_button_row)

        add_row = QHBoxLayout()
        add_row.setSpacing(10)

        self.add_project_combo = QComboBox()
        self.add_project_combo.setObjectName("filterCombo")
        self.add_project_combo.setMinimumWidth(240)
        self.add_project_combo.setFixedHeight(36)
        add_row.addWidget(self.add_project_combo, 1)

        self.add_project_button = QPushButton("Add Project")
        self.add_project_button.setObjectName("secondaryButton")
        self.add_project_button.clicked.connect(self._on_add_project_clicked)
        add_row.addWidget(self.add_project_button)

        detail_layout.addLayout(add_row)

        self._detail_stack.addWidget(detail)
        return panel

    # --- signal handlers -------------------------------------------------------

    def _on_collection_row_changed(self, row: int) -> None:
        if row < 0:
            self._current_collection_id = None
            self._detail_stack.setCurrentIndex(0)
            return
        item = self.collections_list.item(row)
        collection_id = item.data(_PROJECT_ID_ROLE)
        self.collection_selected.emit(collection_id)

    def _on_create_clicked(self) -> None:
        name = self.new_collection_name_input.text().strip()
        if not name:
            return
        self.create_collection_requested.emit(name, "")
        self.new_collection_name_input.clear()

    def _on_save_details_clicked(self) -> None:
        if self._current_collection_id is None:
            return
        name = self.detail_name_input.text().strip()
        if not name:
            return
        description = self.detail_description_input.toPlainText().strip()
        self.rename_collection_requested.emit(self._current_collection_id, name, description)

    def _on_delete_collection_clicked(self) -> None:
        if self._current_collection_id is None:
            return
        confirmed = QMessageBox.question(
            self,
            "Delete Collection",
            f'Delete "{self.detail_name_input.text()}"? This only removes the '
            "collection itself -- none of its projects are affected. This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        self.delete_collection_requested.emit(self._current_collection_id)

    def _selected_project_id(self) -> int | None:
        item = self.projects_list.currentItem()
        return item.data(_PROJECT_ID_ROLE) if item is not None else None

    def _on_move_clicked(self, direction: str) -> None:
        project_id = self._selected_project_id()
        if self._current_collection_id is None or project_id is None:
            return
        self.move_project_requested.emit(self._current_collection_id, project_id, direction)

    def _on_remove_clicked(self) -> None:
        project_id = self._selected_project_id()
        if self._current_collection_id is None or project_id is None:
            return
        self.remove_project_requested.emit(self._current_collection_id, project_id)

    def _on_add_project_clicked(self) -> None:
        if self._current_collection_id is None:
            return
        project_id = self.add_project_combo.currentData()
        if project_id is None:
            return
        self.add_project_requested.emit(self._current_collection_id, project_id)

    def _on_project_double_clicked(self, item: QListWidgetItem) -> None:
        project_id = item.data(_PROJECT_ID_ROLE)
        if project_id is not None:
            self.project_activated.emit(project_id)

    # --- controller-facing API ---------------------------------------------

    def select_collection(self, collection_id: int) -> None:
        """Select whichever row corresponds to `collection_id`, if it's
        currently in the list -- used right after creating a new
        collection, so the user lands on it immediately instead of
        having to find and click it themselves."""
        for row in range(self.collections_list.count()):
            if self.collections_list.item(row).data(_PROJECT_ID_ROLE) == collection_id:
                self.collections_list.setCurrentRow(row)
                return

    def set_collections(self, summaries) -> None:
        """Repopulate the collections list from a tuple of duck-typed
        services.collection_service.CollectionSummary objects. Preserves
        the current selection by id (not row) where possible, so a
        rename/reorder elsewhere doesn't kick the user back to "nothing
        selected"."""
        selected_id = self._current_collection_id
        restore_row = -1
        self.collections_list.blockSignals(True)
        try:
            self.collections_list.clear()
            for row, summary in enumerate(summaries):
                label = f"{summary.name}  ({summary.project_count})"
                item = QListWidgetItem(label)
                item.setData(_PROJECT_ID_ROLE, summary.id)
                self.collections_list.addItem(item)
                if summary.id == selected_id:
                    restore_row = row
            if restore_row >= 0:
                self.collections_list.setCurrentRow(restore_row)
        finally:
            self.collections_list.blockSignals(False)

        if restore_row < 0:
            self._current_collection_id = None
            self._detail_stack.setCurrentIndex(0)

    def set_collection_detail(self, detail) -> None:
        """Show `detail` (a duck-typed
        services.collection_service.CollectionDetail) in the right pane,
        or fall back to the empty state if `detail` is None (nothing
        selected, or the previously-selected collection no longer
        exists)."""
        if detail is None:
            self._current_collection_id = None
            self._detail_stack.setCurrentIndex(0)
            return

        self._current_collection_id = detail.id
        self.detail_name_input.setText(detail.name)
        self.detail_description_input.setPlainText(detail.description or "")

        self.projects_list.clear()
        for project in detail.projects:
            year = str(project.release_date.year) if project.release_date else "TBA"
            type_label = _TYPE_LABELS.get(_enum_value(project.project_type), "")
            status_label = _STATUS_LABELS.get(_enum_value(project.status), "")
            watched_mark = "✓ Watched" if project.watched else "Unwatched"
            rating = format_rating(project.rating) if project.rating is not None else ""
            bits = [bit for bit in (year, type_label, status_label, watched_mark, rating) if bit]
            item = QListWidgetItem(f"{project.title}  ·  {'  ·  '.join(bits)}")
            item.setData(_PROJECT_ID_ROLE, project.id)
            self.projects_list.addItem(item)

        self._detail_stack.setCurrentIndex(1)

    def set_pickable_projects(self, projects: list[tuple[int, str]]) -> None:
        """Populate the "Add Project" combo from (id, title) pairs --
        already filtered by the controller to exclude whatever's
        currently in this collection."""
        self._pickable_projects = list(projects)
        self.add_project_combo.clear()
        for project_id, title in projects:
            self.add_project_combo.addItem(title, project_id)
