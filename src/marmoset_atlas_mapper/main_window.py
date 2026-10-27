from __future__ import annotations

import csv
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import SimpleITK as sitk
from .native_io import read_image, write_image
from PySide6 import QtCore, QtGui, QtWidgets
from . import __version__

from .imaging import (
    VolumeData,
    compose_user_to_atlas,
    compose_atlas_to_user_for_resampling,
    map_points_to_atlas,
    read_color_table,
    resample_atlas_layer_into_user,
    resample_user_ct_into_atlas,
    resample_reference_into_user,
    sample_label,
    save_registration_outputs,
)
from .image_resampling import resample_atlas_to_target
from .io_manifest import write_json
from .data_manager_dialog import ReferenceDataDialog, ensure_reference_data
from .ants_registration import REGISTRATION_TYPE as ANTS_REGISTRATION_TYPE
from .landmarks import load_slicer_markups, write_slicer_markups
from .multi_reference_pipeline import MultiReferenceResult, run_multi_reference_registration
from .paths import bundled_asset_root
from .profile import AtlasLayer, AtlasProfile, load_profiles
from .reference_library import AtlasLayer as LibraryAtlasLayer
from .reference_library import load_reference_library
from .registration import RegistrationResult, register_landmarks
from .registration_modes import normalize_registration_type
from .saved_qc import load_saved_qc_session
from .transform_io import read_transform
from .widgets import (
    AtlasLayerViewerDialog,
    J0476M_REFERENCE_VIEWS,
    MultiReferenceQualityCheckDialog,
    UNLABELED_VIEWS,
    VolumePanel,
)


SKULL_BASE_LABELS = tuple(f"LM{index:02d}" for index in range(1, 9))
SKULL_ALL_LABELS = tuple(f"LM{index:02d}" for index in range(1, 14))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Marmoset Atlas Mapper {__version__}")
        self.resize(1650, 930)
        self.profiles = load_profiles()
        self.reference_library = load_reference_library()
        self.profile: AtlasProfile = next(
            profile for profile in self.profiles if profile.reference_id == "J0476M"
        )
        self.reference_volume: VolumeData | None = None
        self.user_volume: VolumeData | None = None
        self.reference_points: dict[str, np.ndarray] = {}
        self.user_points: dict[str, np.ndarray] = {}
        self.selected_label = SKULL_BASE_LABELS[0]
        self.registration_result: RegistrationResult | None = None
        self.warped_reference: VolumeData | None = None
        self.user_to_atlas: sitk.CompositeTransform | None = None
        self.atlas_to_user: sitk.CompositeTransform | None = None
        self.multi_result: MultiReferenceResult | None = None
        self.warped_references: dict[str, VolumeData] = {}
        self.current_output_directory: Path | None = None
        self.qc_session = None
        self._busy = False
        self._restoring = False
        self._workspace_timer = QtCore.QTimer(self)
        self._workspace_timer.setSingleShot(True)
        self._workspace_timer.setInterval(250)
        self._workspace_timer.timeout.connect(self._write_workspace_state)
        self._setup_ui()
        QtCore.QTimer.singleShot(0, lambda: self._guard(self._load_profile, busy=True))

    def _setup_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)

        toolbar = QtWidgets.QHBoxLayout()
        toolbar.addWidget(QtWidgets.QLabel(f"Preview: <b>J0476M</b> | <b>Nref = {len(self.reference_library.references)}</b>"))
        toolbar.addSpacing(18)
        self.load_ct_button = QtWidgets.QPushButton("Load CT")
        self.load_ct_button.clicked.connect(self._load_user_ct)
        toolbar.addWidget(self.load_ct_button)
        self.import_button = QtWidgets.QPushButton("Import landmarks")
        self.import_button.clicked.connect(self._import_user_markups)
        toolbar.addWidget(self.import_button)
        self.save_markups_button = QtWidgets.QPushButton("Save landmarks")
        self.save_markups_button.clicked.connect(self._save_user_markups)
        toolbar.addWidget(self.save_markups_button)
        self.open_saved_qc_button = QtWidgets.QPushButton("Open results")
        self.open_saved_qc_button.setToolTip("Reopen a saved run without repeating registration.")
        self.open_saved_qc_button.clicked.connect(self._open_saved_qc)
        toolbar.addWidget(self.open_saved_qc_button)
        self.save_results_button = QtWidgets.QPushButton("Open output folder")
        self.save_results_button.setEnabled(False)
        self.save_results_button.clicked.connect(self._save_results)
        toolbar.addWidget(self.save_results_button)
        self.landmark_visibility_button = QtWidgets.QPushButton("Landmarks: ON")
        self.landmark_visibility_button.setCheckable(True)
        self.landmark_visibility_button.setChecked(True)
        self.landmark_visibility_button.toggled.connect(self._toggle_landmarks)
        toolbar.addWidget(self.landmark_visibility_button)
        self.data_manager_button = QtWidgets.QPushButton("Reference data")
        self.data_manager_button.setToolTip("Check the reference images, landmarks, and transforms.")
        self.data_manager_button.clicked.connect(self._open_data_manager)
        toolbar.addWidget(self.data_manager_button)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

        self.reference_panel = VolumePanel(
            "Reference CT: J0476M", interactive=False, view_specs=J0476M_REFERENCE_VIEWS
        )
        self.user_panel = VolumePanel(
            "Target CT",
            interactive=True,
            view_specs=UNLABELED_VIEWS,
            window_level_controls=True,
        )
        self.user_panel.point_clicked.connect(self._place_selected_point)
        self.user_panel.window_level_control.changed.connect(self._write_workspace_state)
        self.user_panel.state_changed.connect(self._schedule_workspace_save)
        viewer_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        viewer_splitter.addWidget(self.reference_panel)
        viewer_splitter.addWidget(self.user_panel)
        viewer_splitter.setSizes([420, 420])

        controls = self._create_controls()
        horizontal_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        horizontal_splitter.addWidget(viewer_splitter)
        horizontal_splitter.addWidget(controls)
        horizontal_splitter.setSizes([1320, 320])
        root.addWidget(horizontal_splitter, 1)

        self.status = QtWidgets.QStatusBar()
        self.setStatusBar(self.status)
        self.status.showMessage("Loading reference CT…")

        self.log_output = QtWidgets.QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setMaximumBlockCount(2000)
        self.log_output.setStyleSheet(
            "QPlainTextEdit { background: #111318; color: #d9e2ef; "
            "font-family: Consolas, 'Courier New', monospace; font-size: 11px; }"
        )
        self.log_dock = QtWidgets.QDockWidget("Processing log", self)
        self.log_dock.setObjectName("ProcessingLogDock")
        self.log_dock.setAllowedAreas(QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)
        self.log_dock.setWidget(self.log_output)
        self.log_dock.setMinimumHeight(115)
        self.addDockWidget(QtCore.Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        self.menuBar().addMenu("View").addAction(self.log_dock.toggleViewAction())
        self.log_dock.hide()
        self.layer_combo.currentTextChanged.connect(self._schedule_workspace_save)
        self._log("Application started.")

    def _create_controls(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        panel.setMinimumWidth(310)
        layout = QtWidgets.QVBoxLayout(panel)
        instructions = QtWidgets.QLabel(
            "Select a landmark, then click its position in the target CT."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("padding: 8px; background: #edf4ff; color: #14233b;")
        layout.addWidget(instructions)

        self.landmark_table = QtWidgets.QTableWidget(len(SKULL_BASE_LABELS), 2)
        self.landmark_table.setHorizontalHeaderLabels(["Landmark", "Status"])
        self.landmark_table.verticalHeader().setVisible(False)
        self.landmark_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.landmark_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.landmark_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.landmark_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.landmark_table.itemSelectionChanged.connect(self._landmark_selection_changed)
        layout.addWidget(self.landmark_table)

        point_buttons = QtWidgets.QHBoxLayout()
        clear_selected = QtWidgets.QPushButton("Clear selected")
        clear_selected.clicked.connect(self._clear_selected)
        clear_all = QtWidgets.QPushButton("Clear all")
        clear_all.clicked.connect(self._clear_all)
        point_buttons.addWidget(clear_selected)
        point_buttons.addWidget(clear_all)
        layout.addLayout(point_buttons)

        type_row = QtWidgets.QHBoxLayout()
        type_row.addWidget(QtWidgets.QLabel("Registration type:"))
        self.registration_type_combo = QtWidgets.QComboBox()
        self.registration_type_combo.addItems(
            ["Landmarks (skull base)", "Landmarks (total)", ANTS_REGISTRATION_TYPE]
        )
        self.registration_type_combo.currentTextChanged.connect(self._registration_type_changed)
        type_row.addWidget(self.registration_type_combo, 1)
        layout.addLayout(type_row)

        transform_row = QtWidgets.QHBoxLayout()
        transform_row.addWidget(QtWidgets.QLabel("Transform:"))
        self.method_combo = QtWidgets.QComboBox()
        self.method_combo.addItems(["Rigid", "Similarity"])
        self.method_combo.currentTextChanged.connect(self._method_changed)
        transform_row.addWidget(self.method_combo, 1)
        layout.addLayout(transform_row)

        self.register_button = QtWidgets.QPushButton("Run registration")
        self.register_button.setMinimumHeight(42)
        self.register_button.setEnabled(False)
        self.register_button.clicked.connect(self._run_registration)
        layout.addWidget(self.register_button)
        self.qc_button = QtWidgets.QPushButton("Open quality check")
        self.qc_button.setEnabled(False)
        self.qc_button.clicked.connect(self._show_qc)
        layout.addWidget(self.qc_button)

        viewer_group = QtWidgets.QGroupBox("Atlas viewer")
        mapping_layout = QtWidgets.QVBoxLayout(viewer_group)
        mapping_layout.addWidget(QtWidgets.QLabel("Atlas layer:"))
        self.layer_combo = QtWidgets.QComboBox()
        mapping_layout.addWidget(self.layer_combo)
        self.atlas_viewer_button = QtWidgets.QPushButton("Open atlas viewer")
        self.atlas_viewer_button.setEnabled(False)
        self.atlas_viewer_button.clicked.connect(self._open_atlas_viewer)
        mapping_layout.addWidget(self.atlas_viewer_button)
        layout.addWidget(viewer_group)

        information_group = QtWidgets.QGroupBox("Atlas license and citation")
        information_layout = QtWidgets.QVBoxLayout(information_group)
        information = QtWidgets.QLabel(
            "<b>Brain/MINDS Marmoset Brain Atlas 2.0</b><br>"
            "Atlas license: CC BY 4.0<br>"
            "<a href='https://doi.org/10.6084/m9.figshare.29992687'>Atlas dataset and citation</a><br><br>"
            f"<b>Marmoset Atlas Mapper v{__version__}</b>"
        )
        information.setWordWrap(True)
        information.setOpenExternalLinks(True)
        information.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextBrowserInteraction)
        information_layout.addWidget(information)
        layout.addWidget(information_group)
        layout.addStretch(1)
        self._refresh_landmark_table()
        return panel

    def _log(self, message: str, level: str = "INFO") -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_output.appendPlainText(f"[{timestamp}] {level:<5} {message}")
        scrollbar = self.log_output.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _guard(self, action, *, busy: bool = False) -> None:
        if busy and self._busy:
            return
        if busy:
            self._busy = True
            self.centralWidget().setEnabled(False)
        try:
            action()
        except Exception as exc:
            traceback.print_exc()
            self._log(f"{exc}\n{traceback.format_exc().rstrip()}", "ERROR")
            QtWidgets.QMessageBox.critical(self, "Marmoset Atlas Mapper", f"{exc}")
            self.status.showMessage(f"Error: {exc}")
        finally:
            if busy:
                self._busy = False
                self.centralWidget().setEnabled(True)

    def closeEvent(self, event) -> None:
        if self._busy:
            event.ignore()
            self.status.showMessage("Please wait until processing has finished before closing.")
            return
        self._write_workspace_state()
        super().closeEvent(event)

    def _schedule_workspace_save(self, *_args) -> None:
        if not self._restoring:
            self._workspace_timer.start()

    def _method_changed(self, method: str) -> None:
        if not hasattr(self, "register_button"):
            return
        self._invalidate_registration()
        self._refresh_landmark_table()
        self._log(f"Transform method changed to {method}.")

    @property
    def registration_labels(self) -> tuple[str, ...]:
        if self.registration_type_combo.currentText() == "Landmarks (skull base)":
            return SKULL_BASE_LABELS
        return SKULL_ALL_LABELS

    def _registration_type_changed(self, registration_type: str) -> None:
        labels = self.registration_labels
        if self.selected_label not in labels:
            self.selected_label = labels[0]
        self.landmark_table.setRowCount(len(labels))
        self._invalidate_registration()
        self._select_landmark(self.selected_label)
        self._refresh_landmark_table()
        self._log(f"Registration type changed to {registration_type}.")

    def _toggle_landmarks(self, visible: bool) -> None:
        self.reference_panel.set_points_visible(visible)
        self.user_panel.set_points_visible(visible)
        self.landmark_visibility_button.setText(f"Landmarks: {'ON' if visible else 'OFF'}")
        self._schedule_workspace_save()

    def _load_profile(self) -> None:
        missing = self.profile.missing_files()
        if missing:
            listing = "\n".join(str(path) for path in missing[:12])
            raise FileNotFoundError(f"Atlas profile is incomplete. Missing files:\n{listing}")
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            self.reference_volume = VolumeData.read(self.profile.reference_ct)
            self.reference_points = load_slicer_markups(self.profile.reference_landmarks)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.reference_panel.setTitle(f"{self.profile.reference_id} Reference CT")
        self.reference_panel.set_volume(self.reference_volume)
        self.reference_panel.set_points(
            {label: self.reference_points[label] for label in self.registration_labels}, self.selected_label
        )
        if self.multi_result is not None:
            preview_route = next(
                route
                for route in self.multi_result.routes
                if route.reference.reference_id == self.profile.reference_id
            )
            self.registration_result = preview_route.registration
            self.warped_reference = self.warped_references.get(self.profile.reference_id)
        self.layer_combo.clear()
        for layer in self.reference_library.atlas_layers:
            self.layer_combo.addItem(layer.name, layer)
        self._select_landmark(self.selected_label)
        self._refresh_landmark_table()
        self.status.showMessage("Loaded J0476M reference")
        self._log("Loaded fixed J0476M reference.")

    def _load_user_ct(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Load target CT",
            "",
            "Medical image (*.nii *.nii.gz *.nrrd *.nhdr);;All files (*)",
        )
        if not path:
            return

        def action() -> None:
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
            try:
                self.user_volume = VolumeData.read(path)
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()
            self.user_panel.set_volume(self.user_volume)
            self.user_points.clear()
            self.user_panel.set_points({}, self.selected_label)
            self._invalidate_registration()
            self._refresh_landmark_table()
            self.register_button.setEnabled(False)
            self.status.showMessage(f"Loaded target CT: {path}")
            self._log(
                f"Loaded target CT: {path}; size={self.user_volume.display_image.GetSize()}, "
                f"spacing={tuple(round(v, 6) for v in self.user_volume.display_image.GetSpacing())}."
            )

        self._guard(action, busy=True)

    def _import_user_markups(self) -> None:
        if self.user_volume is None:
            QtWidgets.QMessageBox.information(self, "Marmoset Atlas Mapper", "Load a target CT first.")
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import target landmarks", "", "Slicer Markups (*.mrk.json);;JSON (*.json)")
        if not path:
            return

        def action() -> None:
            imported = load_slicer_markups(path)
            points = {
                label: imported[label] for label in SKULL_ALL_LABELS if label in imported
            }
            if not points:
                raise ValueError("No placed points labeled LM01–LM13 were found. Your current landmarks have not been changed.")
            self.user_points = points
            self._invalidate_registration()
            self._refresh_landmark_table()
            self.user_panel.set_points(self.user_points, self.selected_label)
            if self.selected_label in self.user_points:
                self.user_panel.jump_to_physical(self.user_points[self.selected_label])
            self.status.showMessage(f"Imported {len(self.user_points)} registration landmarks")
            self._log(f"Imported {len(self.user_points)} registration landmarks from {path}.")

        self._guard(action)

    def _save_user_markups(self) -> None:
        if not self.user_points:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save target landmarks", "TargetCT_Landmarks.mrk.json", "Slicer Markups (*.mrk.json)")
        if path:
            self._guard(lambda: write_slicer_markups(path, self.user_points))

    def _open_saved_qc(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Select a saved registration result folder")
        if not directory:
            return

        def action() -> None:
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
            try:
                session = load_saved_qc_session(directory)
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()
            manifest = json.loads((Path(directory) / "Run_Manifest.json").read_text(encoding="utf-8"))
            registration_type = normalize_registration_type(manifest.get("RegistrationType"))
            if registration_type not in {
                "Landmarks (skull base)", "Landmarks (total)", ANTS_REGISTRATION_TYPE
            }:
                registration_type = (
                    "Landmarks (skull base)"
                    if int(manifest.get("LandmarkCount", 0)) <= 8
                    else "Landmarks (total)"
                )
            workspace = manifest.get("Workspace", {})
            points = {
                label: np.asarray(point, dtype=float)
                for label, point in workspace.get("TargetLandmarks", manifest.get("TargetLandmarks", {})).items()
                if label in SKULL_ALL_LABELS
            }
            if any(point.shape != (3,) or not np.isfinite(point).all() for point in points.values()):
                raise ValueError("Saved workspace contains invalid landmark coordinates.")
            contrast = workspace.get("TargetWindowLevel", {})
            if "Window" in contrast and "Level" in contrast:
                session.target.set_window_level(float(contrast["Window"]), float(contrast["Level"]))
            restored_index = workspace.get("TargetViewIndexXYZ")
            if restored_index is not None:
                restored_index = np.asarray(restored_index, dtype=float)
                if restored_index.shape != (3,) or not np.isfinite(restored_index).all():
                    raise ValueError("Saved workspace contains an invalid slice position.")
            automatic = manifest.get("ForwardTransform") or manifest.get("ConsensusForwardTransform")
            candidate = Path(automatic) if automatic else Path("Target_CT_to_BMA_MultiRef_K04_Forward.h5")  # legacy results
            forward_path = Path(directory) / candidate.name if candidate.is_absolute() else Path(directory) / candidate
            if not forward_path.is_file():
                raise FileNotFoundError(f"Saved forward transform is missing: {forward_path}")
            forward = read_transform(forward_path)
            # Validate everything before replacing the current workspace. Block
            # settings callbacks so opening B cannot save B's settings into A.
            self._restoring = True
            try:
                self._invalidate_registration()
                self.registration_type_combo.setCurrentText(registration_type)
                self.method_combo.setCurrentText(str(manifest.get("Method", "Rigid")))
                self.user_volume = session.target
                self.user_points = points
                self.user_panel.set_volume(self.user_volume)
                label = workspace.get("SelectedLandmark", self.registration_labels[0])
                self._select_landmark(label if label in self.registration_labels else self.registration_labels[0])
                if restored_index is not None:
                    self.user_panel.index_xyz = np.clip(restored_index, 0, np.array(self.user_volume.display_image.GetSize()) - 1)
                    self.user_panel.refresh()
                self.landmark_visibility_button.setChecked(bool(workspace.get("LandmarksVisible", True)))
                self.layer_combo.setCurrentText(workspace.get("AtlasLayer", self.layer_combo.itemText(0)))
                self.warped_references = session.warped_references
                self.registration_result = next(
                    (route.registration for route in session.result.routes if route.reference.reference_id == "J0476M"),
                    session.result.routes[0].registration if session.result.routes else None)
                self.warped_reference = self.warped_references.get("J0476M")
                self.qc_session = session
                self.current_output_directory = Path(directory).resolve()
                self.user_to_atlas = forward
                self.qc_button.setEnabled(True)
                self.atlas_viewer_button.setEnabled(True)
                self.save_results_button.setEnabled(True)
                self._refresh_landmark_table()
            finally:
                self._restoring = False
            self._log(f"Restored saved registration workspace without recomputation: {directory}.")
            self.status.showMessage(f"Restored results: {directory}")

        self._guard(action, busy=True)

    def _landmark_selection_changed(self) -> None:
        rows = self.landmark_table.selectionModel().selectedRows()
        if not rows:
            return
        self._select_landmark(self.registration_labels[rows[0].row()])

    def _select_landmark(self, label: str) -> None:
        self.selected_label = label
        row = self.registration_labels.index(label)
        self.landmark_table.blockSignals(True)
        self.landmark_table.selectRow(row)
        self.landmark_table.blockSignals(False)
        if label in self.reference_points:
            self.reference_panel.jump_to_physical(self.reference_points[label])
        self.reference_panel.set_points(
            {item: self.reference_points[item] for item in self.registration_labels if item in self.reference_points},
            label,
        )
        self.user_panel.set_points(self.user_points, label)
        if label in self.user_points:
            self.user_panel.jump_to_physical(self.user_points[label])
        self._schedule_workspace_save()

    def _place_selected_point(self, point_lps: np.ndarray) -> None:
        if self.user_volume is None:
            return
        self.user_points[self.selected_label] = np.asarray(point_lps, dtype=float)
        self._invalidate_registration()
        self.user_panel.set_points(self.user_points, self.selected_label)
        self._refresh_landmark_table()
        current = self.registration_labels.index(self.selected_label)
        for offset in range(1, len(self.registration_labels) + 1):
            candidate = self.registration_labels[(current + offset) % len(self.registration_labels)]
            if candidate not in self.user_points:
                self._select_landmark(candidate)
                break

    def _clear_selected(self) -> None:
        self.user_points.pop(self.selected_label, None)
        self._invalidate_registration()
        self.user_panel.set_points(self.user_points, self.selected_label)
        self._refresh_landmark_table()

    def _clear_all(self) -> None:
        if self.user_points and QtWidgets.QMessageBox.question(self, "Clear all", "Clear all landmarks on the target CT?") != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.user_points.clear()
        self._invalidate_registration()
        self.user_panel.set_points({}, self.selected_label)
        self._refresh_landmark_table()

    def _invalidate_registration(self) -> None:
        self._workspace_timer.stop()
        self.registration_result = None
        self.warped_reference = None
        self.user_to_atlas = None
        self.atlas_to_user = None
        self.multi_result = None
        self.warped_references.clear()
        self.qc_session = None
        self.current_output_directory = None
        for button in (self.qc_button, self.atlas_viewer_button, self.save_results_button):
            button.setEnabled(False)

    def _active_labels(self) -> list[str]:
        return [label for label in self.registration_labels if label in self.user_points]

    def _refresh_landmark_table(self) -> None:
        self.landmark_table.setRowCount(len(self.registration_labels))
        for row, label in enumerate(self.registration_labels):
            status = "Placed" if label in self.user_points else "Missing"
            for column, value in enumerate((label, status)):
                item = QtWidgets.QTableWidgetItem(value)
                if column == 1:
                    item.setForeground(QtGui.QColor("#198754") if status == "Placed" else QtGui.QColor("#c0392b"))
                self.landmark_table.setItem(row, column, item)
        ready = self.user_volume is not None and len(self._active_labels()) >= 3
        self.register_button.setEnabled(ready)

    def _run_registration(self) -> None:
        if self._busy:
            return
        if self.user_volume is None:
            QtWidgets.QMessageBox.information(self, "Marmoset Atlas Mapper", "Load a target CT first.")
            return
        output_directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select output directory for registration results",
        )
        if not output_directory:
            return
        # Preserve earlier results and failed-run diagnostics rather than mixing
        # files from different runs (especially old inverse outputs).
        if any(Path(output_directory).iterdir()):
            output_directory = str(Path(output_directory) / datetime.now().strftime("Run_%Y%m%d_%H%M%S_%f"))

        def action() -> None:
            labels = self._active_labels()
            if len(labels) < 3:
                raise RuntimeError("At least 3 non-collinear landmarks are required.")
            method = self.method_combo.currentText()
            registration_type = self.registration_type_combo.currentText()
            self._invalidate_registration()
            self._log(
                f"Starting {registration_type}, {method}, with "
                f"{len(labels)} requested landmarks: {', '.join(labels)}."
            )

            def progress(message: str) -> None:
                level = "WARN" if message.startswith("WARNING:") else "INFO"
                self._log(message, level)
                self.status.showMessage(message)
                QtWidgets.QApplication.processEvents()

            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
            try:
                self.multi_result = run_multi_reference_registration(
                    target_ct_path=self.user_volume.source_path,
                    target_landmarks=self.user_points,
                    requested_labels=labels,
                    method=method,
                    library=self.reference_library,
                    output_directory=output_directory,
                    progress=progress,
                    registration_type=registration_type,
                )
                self.user_to_atlas = self.multi_result.consensus_transform
                self.warped_references = {}
                for route in self.multi_result.routes:
                    reference_image = read_image(route.reference.ct_path)
                    warped = resample_reference_into_user(
                        reference_image,
                        self.user_volume.image,
                        route.registration.matrix_lps,
                    )
                    self.warped_references[route.reference.reference_id] = VolumeData.from_image(
                        warped,
                        f"{route.reference.reference_id}_in_TargetCT",
                    )
                preview_route = next(
                    route
                    for route in self.multi_result.routes
                    if route.reference.reference_id == self.profile.reference_id
                )
                self.registration_result = preview_route.registration
                self.warped_reference = self.warped_references[self.profile.reference_id]
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()

            center = np.mean(
                np.vstack([self.user_points[label] for label in self.multi_result.landmark_subset.labels]),
                axis=0,
            )
            atlas_volume = VolumeData.from_image(
                self.multi_result.atlas_reference_in_target,
                "BMA2.0_in_TargetCT",
            )
            self.qc_session = SimpleNamespace(
                target=self.user_volume,
                atlas_in_target=atlas_volume,
                warped_references=self.warped_references,
                result=self.multi_result,
                center_lps=tuple(center),
            )
            self.current_output_directory = Path(output_directory).resolve()
            self._write_workspace_state()
            self.qc_button.setEnabled(True)
            self.atlas_viewer_button.setEnabled(True)
            self.save_results_button.setEnabled(True)
            self._refresh_landmark_table()
            self.status.showMessage(f"{registration_type}, {method} completed: {output_directory}")
            self._log(
                f"{registration_type} completed. Images, landmarks, transforms, and QC reports have been saved."
            )
            self._show_qc()

        self._guard(action, busy=True)

    def _write_workspace_state(self) -> None:
        if self.current_output_directory is None or self._restoring:
            return
        manifest_path = self.current_output_directory / "Run_Manifest.json"
        if not manifest_path.is_file():
            return
        try:
            self._save_workspace_to_manifest(manifest_path)
        except (OSError, ValueError) as exc:
            self._log(f"Could not save viewer settings (result data unchanged): {exc}", "WARN")

    def _save_workspace_to_manifest(self, manifest_path: Path) -> None:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["Workspace"] = {
            "SelectedLandmark": self.selected_label,
            "TargetViewIndexXYZ": self.user_panel.index_xyz.tolist(),
            "LandmarksVisible": self.landmark_visibility_button.isChecked(),
            "AtlasLayer": self.layer_combo.currentText(),
            "TargetLandmarks": {label: np.asarray(point).tolist() for label, point in self.user_points.items()},
            "TargetWindowLevel": {"Window": self.user_volume.window, "Level": self.user_volume.level}
            if self.user_volume is not None else {},
        }
        write_json(manifest_path, manifest)

    def _show_qc(self) -> None:
        if self.qc_session is None:
            return
        self._guard(lambda: MultiReferenceQualityCheckDialog(
            self,
            self.qc_session.target,
            self.qc_session.atlas_in_target,
            self.qc_session.warped_references,
            self.qc_session.result,
            self.qc_session.center_lps,
        ).exec())

    def _get_user_to_atlas(self) -> sitk.Transform:
        if self.user_to_atlas is None:
            raise RuntimeError("Run registration or open saved results first.")
        return self.user_to_atlas

    def _get_atlas_to_user(self) -> sitk.CompositeTransform:
        raise RuntimeError(
            "No inverse transform is available for this operation. "
            "Check the saved inverse QC report for details."
        )

    def _selected_layer(self) -> LibraryAtlasLayer:
        layer = self.layer_combo.currentData()
        if not isinstance(layer, LibraryAtlasLayer):
            raise RuntimeError("No atlas layer is selected.")
        return layer

    def _user_ct_to_atlas(self) -> None:
        if self.multi_result is None or self.multi_result.inverse is None:
            return
        path = (self.multi_result.output_directory / "TargetCT_in_BMA2.0.nii.gz").resolve()
        QtWidgets.QApplication.clipboard().setText(str(path))
        QtWidgets.QMessageBox.information(
            self,
            "Target CT in atlas space",
            f"The inverse transform passed QC. The target CT has been saved in BMA 2.0 space.\n\n"
            f"{path}\n\nThe path has been copied to the clipboard.",
        )

    def _atlas_layer_to_user_ct(self) -> None:
        if self.user_volume is None:
            return
        layer = self._selected_layer()
        default_name = layer.path.name.replace(".nii.gz", "") + "_in_UserCT.nii.gz"
        destination, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save atlas layer in target CT space", default_name, "NIfTI (*.nii.gz *.nii);;NRRD (*.nrrd)")
        if not destination:
            return

        def action() -> None:
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
            try:
                atlas_image = read_image(layer.path)
                mapped = resample_atlas_to_target(
                    atlas_image,
                    self.user_volume.image,
                    self._get_user_to_atlas(),
                    layer.interpolation,
                )
                write_image(mapped, destination, True)
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()
            self.status.showMessage(f"Saved {layer.name} in target CT space: {destination}")
            self._log(f"Saved {layer.name} in target CT space: {destination}.")
            QtWidgets.QMessageBox.information(self, "Mapping completed", f"Saved:\n{destination}")

        self._guard(action)

    def _map_markups_to_atlas(self) -> None:
        source, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select CT-space Markups", "", "Slicer Markups (*.mrk.json);;JSON (*.json)")
        if not source:
            return
        default_name = Path(source).name.replace(".mrk.json", "") + "_in_BMA2.mrk.json"
        destination, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save BMA 2.0 Markups", default_name, "Slicer Markups (*.mrk.json)")
        if not destination:
            return

        def action() -> None:
            points = load_slicer_markups(source)
            mapped = map_points_to_atlas(points, self._get_user_to_atlas())
            write_slicer_markups(destination, mapped, name="BMA2")
            csv_path = Path(destination).with_suffix(".csv")
            if Path(destination).name.endswith(".mrk.json"):
                csv_path = Path(destination).with_name(Path(destination).name[:-9] + ".csv")
            label_image = read_image(self.reference_library.atlas_label_map)
            names = read_color_table(self.reference_library.atlas_color_table)
            with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
                writer = csv.writer(handle)
                writer.writerow(["Label", "L_mm", "P_mm", "S_mm", "RegionValue", "RegionName"])
                for label, point in mapped.items():
                    value = sample_label(label_image, point)
                    writer.writerow([label, *point.tolist(), value, names.get(value, "Outside atlas")])
            self.status.showMessage(f"Mapped {len(mapped)} CT points to BMA 2.0")
            self._log(f"Mapped {len(mapped)} CT points to BMA 2.0: {destination}.")
            QtWidgets.QMessageBox.information(self, "Mapping completed", f"Saved:\n{destination}\n{csv_path}")

        self._guard(action)

    def _open_atlas_viewer(self) -> None:
        if self.current_output_directory is None or self.user_volume is None:
            return

        def action() -> None:
            manifest_path = self.current_output_directory / "Run_Manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            outputs = manifest.get("AutomaticOutputs", {}).get("AtlasLayersInTargetCT", {})
            layers: dict[str, VolumeData] = {}
            for name, value in outputs.items():
                path = Path(value)
                if not path.is_absolute():
                    path = self.current_output_directory / path
                image = read_image(path)
                if image.GetNumberOfComponentsPerPixel() > 1:
                    image = sitk.VectorMagnitude(sitk.Cast(image, sitk.sitkVectorFloat32))
                layers[name] = VolumeData.from_image(image, path)
            center = (
                self.qc_session.center_lps
                if self.qc_session is not None
                else self.user_volume.index_to_physical(
                    (np.asarray(self.user_volume.display_image.GetSize(), dtype=float) - 1.0) / 2.0
                )
            )
            AtlasLayerViewerDialog(
                self,
                self.user_volume,
                layers,
                center,
                self.layer_combo.currentText(),
            ).exec()

        self._guard(action)

    def _save_results(self) -> None:
        if self.current_output_directory is None:
            return
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.current_output_directory)))

    def _open_data_manager(self) -> None:
        def action():
            dialog = ReferenceDataDialog(self, require_complete=False)
            dialog.exec()
            if dialog.data_ready:
                QtWidgets.QMessageBox.information(
                    self, "Reference data", "The data folder is complete and ready to use.")
        self._guard(action)


def run() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Marmoset Atlas Mapper")
    app.setOrganizationName("TMDU")
    icon_path = bundled_asset_root() / "marmoset_atlas_mapper_icon.png"
    if icon_path.is_file():
        app.setWindowIcon(QtGui.QIcon(str(icon_path)))
    app.setStyle("Fusion")
    palette = app.palette()
    palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#f7f9fc"))
    app.setPalette(palette)
    if not ensure_reference_data():
        return 0
    window = MainWindow()
    if not app.windowIcon().isNull():
        window.setWindowIcon(app.windowIcon())
    window.show()
    return app.exec()
