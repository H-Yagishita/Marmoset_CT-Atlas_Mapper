from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from .data_manager import active_data_status, load_data_catalog
from .paths import application_root


class ReferenceDataDialog(QtWidgets.QDialog):
    """Explain and verify the manually installed data package."""

    def __init__(self, parent=None, require_complete: bool = True) -> None:
        super().__init__(parent)
        self.catalog = load_data_catalog()
        self.require_complete = require_complete
        self.data_ready = False
        self.setWindowTitle("Reference Data")
        self.setMinimumWidth(680)
        self.setModal(require_complete)
        self._setup_ui()
        self._refresh()

    def _setup_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel(
            f"<b>{self.catalog.display_name}</b><br>Dataset version: {self.catalog.version}"
        )
        layout.addWidget(title)

        instructions = QtWidgets.QLabel(
            f"1. Download <b>{self.catalog.package_filename}</b> using the link in the GitHub README.<br>"
            "2. Extract the ZIP. The extracted content contains a top-level <b>data</b> folder.<br>"
            "3. Copy that <b>data</b> folder directly beside MarmosetAtlasMapper.exe.<br>"
            "4. Return here and click <b>Check again</b>."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("padding: 10px; background: #edf4ff; color: #14233b;")
        layout.addWidget(instructions)

        expected = application_root() / "data"
        expected_label = QtWidgets.QLabel(f"Expected data folder:<br><code>{expected}</code>")
        expected_label.setWordWrap(True)
        expected_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(expected_label)

        self.status_label = QtWidgets.QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status_label)

        buttons = QtWidgets.QHBoxLayout()
        if self.catalog.landing_page_url:
            download_page = QtWidgets.QPushButton("Open data download page")
            download_page.clicked.connect(
                lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl(self.catalog.landing_page_url))
            )
            buttons.addWidget(download_page)
        check_button = QtWidgets.QPushButton("Check again")
        check_button.clicked.connect(self._refresh)
        buttons.addWidget(check_button)
        self.continue_button = QtWidgets.QPushButton("Continue")
        self.continue_button.clicked.connect(self.accept)
        buttons.addWidget(self.continue_button)
        layout.addLayout(buttons)

        license_label = QtWidgets.QLabel(self.catalog.license_summary)
        license_label.setWordWrap(True)
        license_label.setStyleSheet("color: #4c5565; font-size: 11px;")
        layout.addWidget(license_label)

        close_buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        close_buttons.rejected.connect(self.reject)
        layout.addWidget(close_buttons)

    def _refresh(self) -> None:
        status = active_data_status(self.catalog)
        self.data_ready = status.complete
        if status.complete:
            self.status_label.setText(f"<b>Status: Ready</b><br>Data location: {status.root / 'data'}")
        else:
            example = "<br>".join(str(path) for path in status.missing_files[:3])
            self.status_label.setText(
                f"<b>Status: Data folder is incomplete</b><br>"
                f"Missing files: {len(status.missing_files)}<br>{example}"
            )
        self.continue_button.setEnabled(status.complete)


def ensure_reference_data(parent=None) -> bool:
    catalog = load_data_catalog()
    if active_data_status(catalog).complete:
        return True
    dialog = ReferenceDataDialog(parent, require_complete=True)
    return dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted and dialog.data_ready
