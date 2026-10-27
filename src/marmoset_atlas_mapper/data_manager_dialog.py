from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from .data_manager import active_data_status, load_data_catalog
from .paths import application_root


class ReferenceDataDialog(QtWidgets.QDialog):
    """Check the data library included in the complete package."""

    def __init__(self, parent=None, require_complete: bool = True) -> None:
        super().__init__(parent)
        self.catalog = load_data_catalog()
        self.require_complete = require_complete
        self.data_ready = False
        self.setWindowTitle("Reference data")
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
            "The complete package includes the atlas and all six references.<br>"
            f"If files are missing, extract <b>{self.catalog.package_filename}</b> into a new folder. "
            "Open MarmosetAtlasMapper.exe from that folder, with <b>data</b> and "
            "<b>_internal</b> beside it.<br>"
            "For a source installation, place the package's <b>data</b> folder in the "
            "source directory. After restoring files, click <b>Check again</b>."
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
            download_page = QtWidgets.QPushButton("Open download page")
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
