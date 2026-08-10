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
from PySide6 import QtCore, QtGui, QtWidgets

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
from .data_manager_dialog import ReferenceDataDialog, ensure_reference_data
from .general_pipeline import run_general_registration
from .landmarks import load_slicer_markups, write_slicer_markups
from .multi_reference_pipeline import MultiReferenceResult, run_multi_reference_registration
from .paths import bundled_asset_root
from .profile import AtlasLayer, AtlasProfile, load_profiles
from .reference_library import AtlasLayer as LibraryAtlasLayer
from .reference_library import load_reference_library
from .registration import RegistrationResult, register_landmarks
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
        self.setWindowTitle("Marmoset Atlas Mapper")
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
        self._setup_ui()
        QtCore.QTimer.singleShot(0, self._load_profile)

    def _setup_ui(self) -> None:
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)

        toolbar = QtWidgets.QHBoxLayout()
        toolbar.addWidget(QtWidgets.QLabel("Reference: <b>J0476M</b>"))
        toolbar.addSpacing(18)
        self.load_ct_button = QtWidgets.QPushButton("Load CT")
        self.load_ct_button.clicked.connect(self._load_user_ct)
        toolbar.addWidget(self.load_ct_button)
        self.import_button = QtWidgets.QPushButton("Import Landmarks")
        self.import_button.clicked.connect(self._import_user_markups)
        toolbar.addWidget(self.import_button)
        self.save_markups_button = QtWidgets.QPushButton("Save Landmarks")
        self.save_markups_button.clicked.connect(self._save_user_markups)
        toolbar.addWidget(self.save_markups_button)
        self.open_saved_qc_button = QtWidgets.QPushButton("Open results")
        self.open_saved_qc_button.setToolTip("Restore a previous registration workspace without recomputing registration.")
        self.open_saved_qc_button.clicked.connect(self._open_saved_qc)
        toolbar.addWidget(self.open_saved_qc_button)
        self.save_results_button = QtWidgets.QPushButton("Open Folder")
        self.save_results_button.setEnabled(False)
        self.save_results_button.clicked.connect(self._save_results)
        toolbar.addWidget(self.save_results_button)
        self.landmark_visibility_button = QtWidgets.QPushButton("Landmarks: ON")
        self.landmark_visibility_button.setCheckable(True)
        self.landmark_visibility_button.setChecked(True)
        self.landmark_visibility_button.toggled.connect(self._toggle_landmarks)
        toolbar.addWidget(self.landmark_visibility_button)
        self.data_manager_button = QtWidgets.QPushButton("Reference Data")
        self.data_manager_button.setToolTip("Download, import, or select the reference-data library.")
        self.data_manager_button.clicked.connect(self._open_data_manager)
        toolbar.addWidget(self.data_manager_button)
        toolbar.addStretch(1)
        root.addLayout(toolbar)

        self.reference_panel = VolumePanel(
            "J0476M Reference CT", interactive=False, view_specs=J0476M_REFERENCE_VIEWS
        )
        self.user_panel = VolumePanel(
            "Target CT — click a slice to place the selected landmark",
            interactive=True,
            view_specs=UNLABELED_VIEWS,
        )
        self.user_panel.point_clicked.connect(self._place_selected_point)
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
        self.status.showMessage("Loading reference profile…")

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
        self._log("Application started.")

    def _create_controls(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        panel.setMinimumWidth(310)
        layout = QtWidgets.QVBoxLayout(panel)
        instructions = QtWidgets.QLabel(
            "Place at least 3 non-collinear landmarks. The reference views jump to the corresponding "
            "reference landmark. More landmarks generally provide a more reliable registration."
        )
        instructions.setWordWrap(True)
        instructions.setStyleSheet("padding: 8px; background: #edf4ff; color: #14233b;")
        layout.addWidget(instructions)

        self.landmark_table = QtWidgets.QTableWidget(len(SKULL_BASE_LABELS), 3)
        self.landmark_table.setHorizontalHeaderLabels(["Landmark", "Status", "Residual"])
        self.landmark_table.verticalHeader().setVisible(False)
        self.landmark_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.landmark_table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.landmark_table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.landmark_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.landmark_table.itemSelectionChanged.connect(self._landmark_selection_changed)
        layout.addWidget(self.landmark_table)

        point_buttons = QtWidgets.QHBoxLayout()
        clear_selected = QtWidgets.QPushButton("Clear (selected)")
        clear_selected.clicked.connect(self._clear_selected)
        clear_all = QtWidgets.QPushButton("Clear (all)")
        clear_all.clicked.connect(self._clear_all)
        point_buttons.addWidget(clear_selected)
        point_buttons.addWidget(clear_all)
        layout.addLayout(point_buttons)

        type_row = QtWidgets.QHBoxLayout()
        type_row.addWidget(QtWidgets.QLabel("Registration type:"))
        self.registration_type_combo = QtWidgets.QComboBox()
        self.registration_type_combo.addItems(
            ["Landmark (Skull-base)", "Landmark (Skull-all)", "General (BRAINSFit)"]
        )
        self.registration_type_combo.currentTextChanged.connect(self._registration_type_changed)
        type_row.addWidget(self.registration_type_combo, 1)
        layout.addLayout(type_row)

        transform_row = QtWidgets.QHBoxLayout()
        transform_row.addWidget(QtWidgets.QLabel("Transform method:"))
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
        self.qc_button = QtWidgets.QPushButton("Open Quality Check")
        self.qc_button.setEnabled(False)
        self.qc_button.clicked.connect(self._show_qc)
        layout.addWidget(self.qc_button)

        viewer_group = QtWidgets.QGroupBox("Atlas viewer")
        mapping_layout = QtWidgets.QVBoxLayout(viewer_group)
        mapping_layout.addWidget(QtWidgets.QLabel("Atlas image layer:"))
        self.layer_combo = QtWidgets.QComboBox()
        mapping_layout.addWidget(self.layer_combo)
        self.atlas_viewer_button = QtWidgets.QPushButton("Open Atlas Viewer")
        self.atlas_viewer_button.setEnabled(False)
        self.atlas_viewer_button.clicked.connect(self._open_atlas_viewer)
        mapping_layout.addWidget(self.atlas_viewer_button)
        layout.addWidget(viewer_group)

        information_group = QtWidgets.QGroupBox("Atlas license and citation")
        information_layout = QtWidgets.QVBoxLayout(information_group)
        information = QtWidgets.QLabel(
            "<b>Brain/MINDS Marmoset Brain Atlas 2.0</b><br>"
            "License: CC BY 4.0<br>"
            "<a href='https://doi.org/10.6084/m9.figshare.29992687'>Atlas dataset and citation</a><br><br>"
            "<b>Marmoset Atlas Mapper</b><br>Software/paper citation: forthcoming"
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

    def _guard(self, action) -> None:
        try:
            action()
        except Exception as exc:
            traceback.print_exc()
            self._log(f"{exc}\n{traceback.format_exc().rstrip()}", "ERROR")
            QtWidgets.QMessageBox.critical(self, "Marmoset Atlas Mapper", f"{exc}")
            self.status.showMessage(f"Error: {exc}")

    def _method_changed(self, method: str) -> None:
        if not hasattr(self, "register_button"):
            return
        self._invalidate_registration()
        self._refresh_landmark_table()
        self._log(f"Transform method changed to {method}.")

    @property
    def registration_labels(self) -> tuple[str, ...]:
        if self.registration_type_combo.currentText() == "Landmark (Skull-base)":
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
            "Load User CT",
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
            self._invalidate_registration()
            self._refresh_landmark_table()
            self.register_button.setEnabled(False)
            self.status.showMessage(f"Loaded User CT: {path}")
            self._log(
                f"Loaded User CT: {path}; size={self.user_volume.display_image.GetSize()}, "
                f"spacing={tuple(round(v, 6) for v in self.user_volume.display_image.GetSpacing())}."
            )

        self._guard(action)

    def _import_user_markups(self) -> None:
        if self.user_volume is None:
            QtWidgets.QMessageBox.information(self, "Marmoset Atlas Mapper", "Load a User CT first.")
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import User CT Markups", "", "Slicer Markups (*.mrk.json);;JSON (*.json)")
        if not path:
            return

        def action() -> None:
            imported = load_slicer_markups(path)
            self.user_points = {
                label: imported[label] for label in SKULL_ALL_LABELS if label in imported
            }
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
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save User CT Markups", "UserCT_Landmarks.mrk.json", "Slicer Markups (*.mrk.json)")
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
            registration_type = manifest.get("RegistrationType")
            if registration_type not in {
                "Landmark (Skull-base)", "Landmark (Skull-all)", "General (BRAINSFit)"
            }:
                registration_type = (
                    "Landmark (Skull-base)"
                    if int(manifest.get("LandmarkCount", 0)) <= 8
                    else "Landmark (Skull-all)"
                )
            self.registration_type_combo.setCurrentText(registration_type)
            self.method_combo.setCurrentText(str(manifest.get("Method", "Rigid")))
            self.user_volume = session.target
            self.user_points = {
                label: np.asarray(point, dtype=float)
                for label, point in manifest.get("TargetLandmarks", {}).items()
                if label in SKULL_ALL_LABELS
            }
            self.user_panel.set_volume(self.user_volume)
            workspace = manifest.get("Workspace", {})
            restored_label = workspace.get("SelectedLandmark")
            if restored_label in self.registration_labels:
                self.selected_label = restored_label
            self.user_panel.set_points(self.user_points, self.selected_label)
            restored_index = workspace.get("TargetViewIndexXYZ")
            if isinstance(restored_index, list) and len(restored_index) == 3:
                self.user_panel.index_xyz = np.asarray(restored_index, dtype=float)
                self.user_panel.refresh()
            visible = bool(workspace.get("LandmarksVisible", True))
            self.landmark_visibility_button.setChecked(visible)
            restored_layer = workspace.get("AtlasLayer")
            if restored_layer:
                self.layer_combo.setCurrentText(restored_layer)
            self.warped_references = session.warped_references
            self.registration_result = next(
                (
                    route.registration
                    for route in session.result.routes
                    if route.reference.reference_id == "J0476M"
                ),
                session.result.routes[0].registration if session.result.routes else None,
            )
            self.qc_session = session
            self.current_output_directory = Path(directory).resolve()
            forward_path = self.current_output_directory / "Target_CT_to_BMA_MultiRef_K04_Forward.h5"
            if not forward_path.is_file():
                automatic = manifest.get("ForwardTransform") or manifest.get("ConsensusForwardTransform")
                if automatic:
                    candidate = Path(automatic)
                    forward_path = candidate if candidate.is_absolute() else self.current_output_directory / candidate
            self.user_to_atlas = read_transform(forward_path) if forward_path.is_file() else None
            self.qc_button.setEnabled(True)
            self.atlas_viewer_button.setEnabled(True)
            self.save_results_button.setEnabled(True)
            self._refresh_landmark_table()
            self._log(f"Restored saved registration workspace without recomputation: {directory}.")
            self.status.showMessage(f"Restored results: {directory}")

        self._guard(action)

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
        if self.user_points and QtWidgets.QMessageBox.question(self, "Clear all", "Clear all User CT landmarks?") != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.user_points.clear()
        self._invalidate_registration()
        self.user_panel.set_points({}, self.selected_label)
        self._refresh_landmark_table()

    def _invalidate_registration(self) -> None:
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
            residual = ""
            if self.registration_result is not None and label in self.registration_result.labels:
                index = self.registration_result.labels.index(label)
                residual = f"{self.registration_result.residual_distances[index]:.3f} mm"
            for column, value in enumerate((label, status, residual)):
                item = QtWidgets.QTableWidgetItem(value)
                if column == 1:
                    item.setForeground(QtGui.QColor("#198754") if status == "Placed" else QtGui.QColor("#c0392b"))
                self.landmark_table.setItem(row, column, item)
        ready = self.user_volume is not None and len(self._active_labels()) >= 3
        self.register_button.setEnabled(ready)

    def _run_registration(self) -> None:
        if self.user_volume is None:
            QtWidgets.QMessageBox.information(self, "Marmoset Atlas Mapper", "Load a User CT first.")
            return
        output_directory = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Select output directory for registration results",
        )
        if not output_directory:
            return

        def action() -> None:
            labels = self._active_labels()
            if len(labels) < 3:
                raise RuntimeError("At least 3 non-collinear landmarks are required.")
            method = self.method_combo.currentText()
            registration_type = self.registration_type_combo.currentText()
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
                if registration_type == "General (BRAINSFit)":
                    self.multi_result = run_general_registration(
                        target_ct_path=self.user_volume.source_path,
                        target_landmarks=self.user_points,
                        requested_labels=labels,
                        method=method,
                        library=self.reference_library,
                        output_directory=output_directory,
                        progress=progress,
                    )
                else:
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
                    reference_image = sitk.ReadImage(str(route.reference.ct_path))
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
                f"{registration_type} completed. Default image, landmark, transform, and QC outputs were generated."
            )
            self._show_qc()

        self._guard(action)

    def _write_workspace_state(self) -> None:
        if self.current_output_directory is None:
            return
        manifest_path = self.current_output_directory / "Run_Manifest.json"
        if not manifest_path.is_file():
            return
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["Workspace"] = {
            "SelectedLandmark": self.selected_label,
            "TargetViewIndexXYZ": self.user_panel.index_xyz.tolist(),
            "LandmarksVisible": self.landmark_visibility_button.isChecked(),
            "AtlasLayer": self.layer_combo.currentText(),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    def _show_qc(self) -> None:
        if self.qc_session is None:
            return
        MultiReferenceQualityCheckDialog(
            self,
            self.qc_session.target,
            self.qc_session.atlas_in_target,
            self.qc_session.warped_references,
            self.qc_session.result,
            self.qc_session.center_lps,
        ).exec()

    def _get_user_to_atlas(self) -> sitk.Transform:
        if self.multi_result is None or self.user_to_atlas is None:
            raise RuntimeError("Run K04 multi-reference consensus first.")
        return self.user_to_atlas

    def _get_atlas_to_user(self) -> sitk.CompositeTransform:
        raise RuntimeError(
            "A robust inverse consensus field has not been generated. "
            "The primary implementation intentionally provides forward Target CT → BMA mapping only."
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
            "3A output",
            f"The inverse passed QC and the Target CT was automatically resampled into BMA 2.0 geometry.\n\n"
            f"{path}\n\nThe path has been copied to the clipboard.",
        )

    def _atlas_layer_to_user_ct(self) -> None:
        if self.user_volume is None:
            return
        layer = self._selected_layer()
        default_name = layer.path.name.replace(".nii.gz", "") + "_in_UserCT.nii.gz"
        destination, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save Atlas layer in User CT space", default_name, "NIfTI (*.nii.gz *.nii);;NRRD (*.nrrd)")
        if not destination:
            return

        def action() -> None:
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
            try:
                atlas_image = sitk.ReadImage(str(layer.path))
                mapped = resample_atlas_to_target(
                    atlas_image,
                    self.user_volume.image,
                    self._get_user_to_atlas(),
                    layer.interpolation,
                )
                sitk.WriteImage(mapped, destination, True)
            finally:
                QtWidgets.QApplication.restoreOverrideCursor()
            self.status.showMessage(f"Saved {layer.name} in User CT space: {destination}")
            self._log(f"Saved {layer.name} in User CT space: {destination}.")
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
            csv_path = Path(destination).with_name(Path(destination).name.replace(".mrk.json", ".csv"))
            label_image = sitk.ReadImage(str(self.reference_library.atlas_label_map))
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
                image = sitk.ReadImage(str(path))
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
        dialog = ReferenceDataDialog(self, require_complete=False)
        dialog.exec()
        if dialog.data_ready:
            QtWidgets.QMessageBox.information(
                self,
                "Reference Data",
                "The data folder is complete and ready to use.",
            )


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
