from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np
import SimpleITK as sitk
from PySide6 import QtCore, QtGui, QtWidgets

from .imaging import VolumeData, normalize_to_uint8
from .profile import QCBenchmark


ORIENTATIONS = ("Axial", "Coronal", "Sagittal")

# J0476M was acquired in a non-standard scanner orientation.  These view
# specifications deliberately describe the anatomy seen in that particular
# reference volume instead of deriving anatomical names from the file axes.
J0476M_REFERENCE_VIEWS = (
    ("Axial", "Horizontal (Axial)", {"left": "A", "right": "P"}),
    ("Coronal", "Sagittal", {"left": "A", "right": "P", "top": "D", "bottom": "V"}),
    ("Sagittal", "Coronal", {"left": "L", "right": "R", "top": "D", "bottom": "V"}),
)
UNLABELED_VIEWS = tuple((orientation, "", {}) for orientation in ORIENTATIONS)


def extract_display_plane(
    array_zyx: np.ndarray,
    orientation: str,
    index_xyz: Iterable[float],
) -> np.ndarray:
    """Extract a slice using the radiological display convention."""
    x, y, z = np.rint(np.asarray(tuple(index_xyz), dtype=float)).astype(int)
    x = int(np.clip(x, 0, array_zyx.shape[2] - 1))
    y = int(np.clip(y, 0, array_zyx.shape[1] - 1))
    z = int(np.clip(z, 0, array_zyx.shape[0] - 1))
    if orientation == "Axial":
        return array_zyx[z, :, :]
    if orientation == "Coronal":
        return np.flipud(array_zyx[:, y, :])
    if orientation == "Sagittal":
        return np.flipud(array_zyx[:, :, x])
    raise ValueError(f"Unsupported orientation: {orientation}")


def index_to_display_xy(
    index_xyz: Iterable[float],
    orientation: str,
    size_xyz: Iterable[int],
) -> tuple[float, float]:
    x, y, z = np.asarray(tuple(index_xyz), dtype=float)
    _size_x, _size_y, size_z = tuple(int(value) for value in size_xyz)
    if orientation == "Axial":
        return float(x), float(y)
    if orientation == "Coronal":
        return float(x), float(size_z - 1 - z)
    if orientation == "Sagittal":
        return float(y), float(size_z - 1 - z)
    raise ValueError(f"Unsupported orientation: {orientation}")


def display_xy_to_index(
    image_x: float,
    image_y: float,
    orientation: str,
    current_index_xyz: Iterable[float],
    size_xyz: Iterable[int],
) -> np.ndarray:
    x, y, z = np.asarray(tuple(current_index_xyz), dtype=float)
    _size_x, _size_y, size_z = tuple(int(value) for value in size_xyz)
    if orientation == "Axial":
        return np.array([image_x, image_y, z], dtype=float)
    if orientation == "Coronal":
        return np.array([image_x, y, size_z - 1 - image_y], dtype=float)
    if orientation == "Sagittal":
        return np.array([x, image_x, size_z - 1 - image_y], dtype=float)
    raise ValueError(f"Unsupported orientation: {orientation}")


def plane_pixel_spacing(
    orientation: str,
    spacing_xyz: Iterable[float],
) -> tuple[float, float]:
    spacing_x, spacing_y, spacing_z = tuple(float(value) for value in spacing_xyz)
    if orientation == "Axial":
        return spacing_x, spacing_y
    if orientation == "Coronal":
        return spacing_x, spacing_z
    if orientation == "Sagittal":
        return spacing_y, spacing_z
    raise ValueError(f"Unsupported orientation: {orientation}")


def qc_benchmark_state(
    fre_rms_mm: float,
    method: str,
    landmark_count: int,
    benchmark: QCBenchmark,
) -> str:
    if fre_rms_mm > benchmark.warning_threshold_mm:
        return "warning"
    if method == "Rigid" and landmark_count == 8:
        return "within_reference_range"
    return "context_only"


class ImageCanvas(QtWidgets.QWidget):
    clicked = QtCore.Signal(float, float)
    wheel_steps = QtCore.Signal(int)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(190, 190)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background: #111318;")
        self._image: QtGui.QImage | None = None
        self._image_size = QtCore.QSize(1, 1)
        self._pixel_spacing = (1.0, 1.0)
        self._crosshair: tuple[float, float] | None = None
        self._points: list[tuple[float, float, str, QtGui.QColor]] = []
        self._axis_labels: dict[str, str] = {}

    def set_axis_labels(self, labels: Mapping[str, str] | None) -> None:
        self._axis_labels = dict(labels or {})
        self.update()

    def set_array(self, array: np.ndarray, pixel_spacing: tuple[float, float] = (1.0, 1.0)) -> None:
        data = np.ascontiguousarray(array)
        if data.ndim == 2:
            if data.dtype != np.uint8:
                raise ValueError("Grayscale canvas data must be uint8.")
            height, width = data.shape
            image = QtGui.QImage(data.data, width, height, data.strides[0], QtGui.QImage.Format.Format_Grayscale8)
        elif data.ndim == 3 and data.shape[2] == 3:
            if data.dtype != np.uint8:
                raise ValueError("RGB canvas data must be uint8.")
            height, width, _ = data.shape
            image = QtGui.QImage(data.data, width, height, data.strides[0], QtGui.QImage.Format.Format_RGB888)
        else:
            raise ValueError(f"Unsupported canvas shape: {data.shape}")
        self._image = image.copy()
        self._image_size = QtCore.QSize(width, height)
        spacing_x, spacing_y = (float(value) for value in pixel_spacing)
        if spacing_x <= 0.0 or spacing_y <= 0.0:
            raise ValueError("Pixel spacing must be positive.")
        self._pixel_spacing = (spacing_x, spacing_y)
        self.update()

    def set_overlays(
        self,
        crosshair: tuple[float, float] | None,
        points: list[tuple[float, float, str, QtGui.QColor]],
    ) -> None:
        self._crosshair = crosshair
        self._points = points
        self.update()

    def _target_rect(self) -> QtCore.QRectF:
        if self._image is None:
            return QtCore.QRectF()
        physical_width = self._image_size.width() * self._pixel_spacing[0]
        physical_height = self._image_size.height() * self._pixel_spacing[1]
        scale = min(
            self.width() / max(physical_width, 1e-12),
            self.height() / max(physical_height, 1e-12),
        )
        target_width = physical_width * scale
        target_height = physical_height * scale
        x = (self.width() - target_width) / 2.0
        y = (self.height() - target_height) / 2.0
        return QtCore.QRectF(x, y, target_width, target_height)

    def _to_widget(self, image_x: float, image_y: float) -> QtCore.QPointF:
        rect = self._target_rect()
        return QtCore.QPointF(
            rect.left() + image_x * rect.width() / max(self._image_size.width(), 1),
            rect.top() + image_y * rect.height() / max(self._image_size.height(), 1),
        )

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), QtGui.QColor("#111318"))
        if self._image is None:
            painter.setPen(QtGui.QColor("#8a93a3"))
            painter.drawText(self.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, "No volume")
            return
        target = self._target_rect()
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(target, self._image)

        if self._axis_labels:
            painter.setPen(QtGui.QPen(QtGui.QColor("#f2f6ff"), 1.0))
            font = painter.font()
            font.setBold(True)
            font.setPointSize(max(font.pointSize(), 11))
            painter.setFont(font)
            margin = 7.0
            if "left" in self._axis_labels:
                painter.drawText(
                    QtCore.QRectF(target.left() + margin, target.center().y() - 15, 24, 30),
                    QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignLeft,
                    self._axis_labels["left"],
                )
            if "right" in self._axis_labels:
                painter.drawText(
                    QtCore.QRectF(target.right() - 24 - margin, target.center().y() - 15, 24, 30),
                    QtCore.Qt.AlignmentFlag.AlignVCenter | QtCore.Qt.AlignmentFlag.AlignRight,
                    self._axis_labels["right"],
                )
            if "top" in self._axis_labels:
                painter.drawText(
                    QtCore.QRectF(target.center().x() - 15, target.top() + margin, 30, 24),
                    QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop,
                    self._axis_labels["top"],
                )
            if "bottom" in self._axis_labels:
                painter.drawText(
                    QtCore.QRectF(target.center().x() - 15, target.bottom() - 24 - margin, 30, 24),
                    QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignBottom,
                    self._axis_labels["bottom"],
                )

        if self._crosshair is not None:
            point = self._to_widget(*self._crosshair)
            painter.setPen(QtGui.QPen(QtGui.QColor("#39d5ff"), 1.0))
            painter.drawLine(QtCore.QPointF(target.left(), point.y()), QtCore.QPointF(target.right(), point.y()))
            painter.drawLine(QtCore.QPointF(point.x(), target.top()), QtCore.QPointF(point.x(), target.bottom()))

        for image_x, image_y, label, color in self._points:
            point = self._to_widget(image_x, image_y)
            painter.setPen(QtGui.QPen(QtGui.QColor("#121212"), 3.0))
            painter.setBrush(color)
            painter.drawEllipse(point, 6.0, 6.0)
            painter.setPen(QtGui.QPen(color, 1.0))
            painter.drawText(point + QtCore.QPointF(8.0, -7.0), label)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.MouseButton.LeftButton or self._image is None:
            return
        rect = self._target_rect()
        position = event.position()
        if not rect.contains(position):
            return
        x = (position.x() - rect.left()) * self._image_size.width() / max(rect.width(), 1.0)
        y = (position.y() - rect.top()) * self._image_size.height() / max(rect.height(), 1.0)
        self.clicked.emit(float(np.clip(x, 0, self._image_size.width() - 1)), float(np.clip(y, 0, self._image_size.height() - 1)))

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        steps = int(event.angleDelta().y() / 120)
        if steps:
            self.wheel_steps.emit(steps)
            event.accept()


class SliceView(QtWidgets.QWidget):
    index_clicked = QtCore.Signal(object)
    slice_changed = QtCore.Signal(str, int)

    def __init__(
        self,
        orientation: str,
        parent: QtWidgets.QWidget | None = None,
        *,
        display_title: str | None = None,
        axis_labels: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.orientation = orientation
        self.volume: VolumeData | None = None
        self.index_xyz = np.zeros(3, dtype=float)
        self.points_lps: Mapping[str, np.ndarray] = {}
        self.selected_label = ""
        self.points_visible = True
        self.canvas = ImageCanvas()
        self.canvas.set_axis_labels(axis_labels)
        self.title = QtWidgets.QLabel(orientation if display_title is None else display_title)
        self.title.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.title.setStyleSheet("font-weight: 600; color: #dbe5f5;")
        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.position_label = QtWidgets.QLabel("0 / 0")
        self.position_label.setMinimumWidth(70)
        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(self.slider, 1)
        controls.addWidget(self.position_label)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.addWidget(self.title)
        layout.addWidget(self.canvas, 1)
        layout.addLayout(controls)
        self.slider.valueChanged.connect(self._slider_changed)
        self.canvas.clicked.connect(self._canvas_clicked)
        self.canvas.wheel_steps.connect(self._wheel)

    def _axis(self) -> int:
        return {"Sagittal": 0, "Coronal": 1, "Axial": 2}[self.orientation]

    def set_volume(self, volume: VolumeData) -> None:
        self.volume = volume
        size = np.asarray(volume.display_image.GetSize(), dtype=float)
        self.index_xyz = (size - 1.0) / 2.0
        axis = self._axis()
        self.slider.blockSignals(True)
        self.slider.setRange(0, int(size[axis] - 1))
        self.slider.setValue(int(round(self.index_xyz[axis])))
        self.slider.blockSignals(False)
        self.refresh()

    def set_state(
        self,
        index_xyz: Iterable[float],
        points_lps: Mapping[str, np.ndarray],
        selected_label: str,
    ) -> None:
        self.index_xyz = np.asarray(tuple(index_xyz), dtype=float)
        self.points_lps = points_lps
        self.selected_label = selected_label
        if self.volume is not None:
            axis = self._axis()
            self.slider.blockSignals(True)
            self.slider.setValue(int(round(self.index_xyz[axis])))
            self.slider.blockSignals(False)
        self.refresh()

    def _plane_and_xy(self) -> tuple[np.ndarray, tuple[float, float]]:
        assert self.volume is not None
        array = self.volume.array_zyx
        size_xyz = self.volume.display_image.GetSize()
        return (
            extract_display_plane(array, self.orientation, self.index_xyz),
            index_to_display_xy(self.index_xyz, self.orientation, size_xyz),
        )

    def _point_xy(self, index: np.ndarray) -> tuple[float, float]:
        assert self.volume is not None
        return index_to_display_xy(index, self.orientation, self.volume.display_image.GetSize())

    def refresh(self) -> None:
        if self.volume is None:
            return
        plane, crosshair = self._plane_and_xy()
        gray = normalize_to_uint8(plane, self.volume.window_min, self.volume.window_max)
        self.canvas.set_array(
            gray,
            plane_pixel_spacing(self.orientation, self.volume.display_image.GetSpacing()),
        )
        current_slice = int(round(self.index_xyz[self._axis()]))
        overlays: list[tuple[float, float, str, QtGui.QColor]] = []
        for label, point in (self.points_lps.items() if self.points_visible else ()):
            try:
                index = self.volume.physical_to_index(point)
            except RuntimeError:
                continue
            if abs(index[self._axis()] - current_slice) <= 0.65:
                color = QtGui.QColor("#ffcf4a") if label == self.selected_label else QtGui.QColor("#ff6685")
                overlays.append((*self._point_xy(index), label, color))
        self.canvas.set_overlays(crosshair, overlays)
        self.position_label.setText(f"{current_slice + 1} / {self.slider.maximum() + 1}")

    def _slider_changed(self, value: int) -> None:
        self.slice_changed.emit(self.orientation, value)

    def _wheel(self, steps: int) -> None:
        self.slider.setValue(int(np.clip(self.slider.value() + steps, self.slider.minimum(), self.slider.maximum())))

    def _canvas_clicked(self, image_x: float, image_y: float) -> None:
        assert self.volume is not None
        index = display_xy_to_index(
            image_x,
            image_y,
            self.orientation,
            self.index_xyz,
            self.volume.display_image.GetSize(),
        )
        self.index_clicked.emit(index)


class VolumePanel(QtWidgets.QGroupBox):
    point_clicked = QtCore.Signal(object)

    def __init__(
        self,
        title: str,
        *,
        interactive: bool,
        view_specs=None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(title, parent)
        self.interactive = interactive
        self.volume: VolumeData | None = None
        self.index_xyz = np.zeros(3, dtype=float)
        self.points_lps: dict[str, np.ndarray] = {}
        self.selected_label = ""
        specs = view_specs or tuple((orientation, orientation, {}) for orientation in ORIENTATIONS)
        self.views = {
            orientation: SliceView(orientation, display_title=display_title, axis_labels=axis_labels)
            for orientation, display_title, axis_labels in specs
        }
        layout = QtWidgets.QHBoxLayout(self)
        for view in self.views.values():
            layout.addWidget(view, 1)
            view.slice_changed.connect(self._slice_changed)
            if interactive:
                view.index_clicked.connect(self._index_clicked)

    def set_volume(self, volume: VolumeData) -> None:
        self.volume = volume
        size = np.asarray(volume.display_image.GetSize(), dtype=float)
        self.index_xyz = (size - 1.0) / 2.0
        for view in self.views.values():
            view.set_volume(volume)
        self.refresh()

    def set_points(self, points_lps: Mapping[str, Iterable[float]], selected_label: str = "") -> None:
        self.points_lps = {label: np.asarray(tuple(point), dtype=float) for label, point in points_lps.items()}
        self.selected_label = selected_label
        self.refresh()

    def set_points_visible(self, visible: bool) -> None:
        for view in self.views.values():
            view.points_visible = bool(visible)
        self.refresh()

    def jump_to_physical(self, point_lps: Iterable[float]) -> None:
        if self.volume is None:
            return
        index = self.volume.physical_to_index(tuple(point_lps))
        size = np.asarray(self.volume.display_image.GetSize(), dtype=float)
        self.index_xyz = np.clip(index, 0.0, size - 1.0)
        self.refresh()

    def refresh(self) -> None:
        for view in self.views.values():
            view.set_state(self.index_xyz, self.points_lps, self.selected_label)

    def _slice_changed(self, orientation: str, value: int) -> None:
        axis = {"Sagittal": 0, "Coronal": 1, "Axial": 2}[orientation]
        self.index_xyz[axis] = value
        self.refresh()

    def _index_clicked(self, index_xyz: np.ndarray) -> None:
        if self.volume is None:
            return
        size = np.asarray(self.volume.display_image.GetSize(), dtype=float)
        self.index_xyz = np.clip(index_xyz, 0.0, size - 1.0)
        self.refresh()
        self.point_clicked.emit(self.volume.index_to_physical(self.index_xyz))


class OverlaySliceView(SliceView):
    def __init__(self, orientation: str, base: VolumeData, overlay: VolumeData) -> None:
        self.overlay_volume = overlay
        super().__init__(orientation)
        self.set_volume(base)

    def refresh(self) -> None:
        if self.volume is None:
            return
        base_plane, crosshair = self._plane_and_xy()
        overlay_plane = extract_display_plane(
            self.overlay_volume.array_zyx,
            self.orientation,
            self.index_xyz,
        )
        base_gray = normalize_to_uint8(base_plane, self.volume.window_min, self.volume.window_max)
        overlay_gray = normalize_to_uint8(
            overlay_plane,
            self.overlay_volume.window_min,
            self.overlay_volume.window_max,
        )
        rgb = np.zeros((*base_gray.shape, 3), dtype=np.uint8)
        rgb[..., 0] = overlay_gray
        rgb[..., 1] = base_gray
        self.canvas.set_array(
            rgb,
            plane_pixel_spacing(self.orientation, self.volume.display_image.GetSpacing()),
        )
        self.canvas.set_overlays(crosshair, [])
        current_slice = int(round(self.index_xyz[self._axis()]))
        self.position_label.setText(f"{current_slice + 1} / {self.slider.maximum() + 1}")


class AtlasLayerViewerDialog(QtWidgets.QDialog):
    """Reloadable atlas-in-target overlay viewer with no registration work."""

    def __init__(
        self,
        parent: QtWidgets.QWidget,
        base: VolumeData,
        layers: Mapping[str, VolumeData],
        center_lps: Iterable[float],
        initial_layer: str | None = None,
    ) -> None:
        super().__init__(parent)
        if not layers:
            raise ValueError("No mapped Atlas layers are available in this result.")
        self.setWindowTitle("Atlas Layer Viewer")
        self.resize(1350, 720)
        self.base = base
        self.layers = dict(layers)
        self.index_xyz = base.physical_to_index(tuple(center_lps))
        root = QtWidgets.QVBoxLayout(self)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Atlas image layer:"))
        self.layer_combo = QtWidgets.QComboBox()
        self.layer_combo.addItems(list(self.layers))
        if initial_layer in self.layers:
            self.layer_combo.setCurrentText(initial_layer)
        row.addWidget(self.layer_combo, 1)
        root.addLayout(row)
        self.legend = QtWidgets.QLabel()
        root.addWidget(self.legend)
        self.views_host = QtWidgets.QWidget()
        self.views_layout = QtWidgets.QHBoxLayout(self.views_host)
        root.addWidget(self.views_host, 1)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.layer_combo.currentTextChanged.connect(self._set_layer)
        self.views: dict[str, OverlaySliceView] = {}
        self._set_layer(self.layer_combo.currentText())

    def _set_layer(self, name: str) -> None:
        while self.views_layout.count():
            item = self.views_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.legend.setText(f"Red = {name}; Green = Target CT; Yellow = agreement.")
        self.views = {
            orientation: OverlaySliceView(orientation, self.base, self.layers[name])
            for orientation in ORIENTATIONS
        }
        for view in self.views.values():
            view.title.setText("")
            view.set_state(self.index_xyz, {}, "")
            view.slice_changed.connect(self._slice_changed)
            self.views_layout.addWidget(view, 1)

    def _slice_changed(self, orientation: str, value: int) -> None:
        axis = {"Sagittal": 0, "Coronal": 1, "Axial": 2}[orientation]
        self.index_xyz[axis] = value
        for view in self.views.values():
            view.set_state(self.index_xyz, {}, "")


class QualityCheckDialog(QtWidgets.QDialog):
    def __init__(
        self,
        parent: QtWidgets.QWidget,
        base: VolumeData,
        warped_reference: VolumeData,
        result,
        center_lps: Iterable[float],
        reference_id: str,
        benchmark: QCBenchmark,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Landmark Registration Quality Check")
        self.resize(1450, 820)
        layout = QtWidgets.QVBoxLayout(self)

        summary = QtWidgets.QLabel(
            f"Method: <b>{result.method}</b>&nbsp;&nbsp; "
            f"Landmarks: <b>{len(result.labels)}</b>&nbsp;&nbsp; "
            f"FRE RMS: <b>{result.rms_mm:.3f} mm</b>&nbsp;&nbsp; "
            f"Mean: <b>{result.mean_mm:.3f} mm</b>&nbsp;&nbsp; "
            f"Median: <b>{result.median_mm:.3f} mm</b>&nbsp;&nbsp; "
            f"Maximum: <b>{result.maximum_mm:.3f} mm</b>"
        )
        summary.setStyleSheet("font-size: 15px; padding: 8px; background: #e8f2ff; color: #10233f;")
        layout.addWidget(summary)

        benchmark_label = QtWidgets.QLabel(
            "FRE is displayed as landmark-registration QC only. It is not used for "
            "reference selection, weighting, or as an Atlas-mapping accuracy surrogate."
        )
        benchmark_label.setWordWrap(True)
        benchmark_label.setStyleSheet("padding: 9px; background: #e8f2ff; color: #183b66;")
        layout.addWidget(benchmark_label)

        tabs = QtWidgets.QTabWidget()
        overlay_tab = QtWidgets.QWidget()
        overlay_layout = QtWidgets.QVBoxLayout(overlay_tab)
        legend = QtWidgets.QLabel(
            f"Red = transformed {reference_id} reference CT, Green = user CT, Yellow = agreement"
        )
        overlay_layout.addWidget(legend)
        views_layout = QtWidgets.QHBoxLayout()
        self.overlay_views = {
            orientation: OverlaySliceView(orientation, base, warped_reference) for orientation in ORIENTATIONS
        }
        center_index = base.physical_to_index(tuple(center_lps))
        for view in self.overlay_views.values():
            view.set_state(center_index, {}, "")
            view.slice_changed.connect(self._slice_changed)
            views_layout.addWidget(view, 1)
        self.index_xyz = center_index.copy()
        overlay_layout.addLayout(views_layout, 1)
        tabs.addTab(overlay_tab, "Overlay")

        residual_tab = QtWidgets.QWidget()
        residual_layout = QtWidgets.QVBoxLayout(residual_tab)
        table = QtWidgets.QTableWidget(len(result.labels), 5)
        table.setHorizontalHeaderLabels(["Landmark", "Residual (mm)", "dL (mm)", "dP (mm)", "dS (mm)"])
        for row, (label, distance, vector) in enumerate(
            zip(result.labels, result.residual_distances, result.residual_vectors)
        ):
            values = [label, f"{distance:.4f}", *[f"{value:.4f}" for value in vector]]
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                if column > 0:
                    item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
                table.setItem(row, column, item)
        table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        residual_layout.addWidget(table)
        matrix_text = QtWidgets.QPlainTextEdit()
        matrix_text.setReadOnly(True)
        matrix_text.setMaximumHeight(180)
        matrix_text.setPlainText(
            f"User CT → {reference_id} {result.method} matrix (LPS)\n"
            + np.array2string(result.matrix_lps, precision=8)
        )
        residual_layout.addWidget(matrix_text)
        tabs.addTab(residual_tab, "Residuals and transform")
        layout.addWidget(tabs, 1)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _slice_changed(self, orientation: str, value: int) -> None:
        axis = {"Sagittal": 0, "Coronal": 1, "Axial": 2}[orientation]
        self.index_xyz[axis] = value
        for view in self.overlay_views.values():
            view.set_state(self.index_xyz, {}, "")


class MultiReferenceQualityCheckDialog(QtWidgets.QDialog):
    """Interactive QC for the equal-weight K04 forward consensus."""

    def __init__(
        self,
        parent: QtWidgets.QWidget,
        base: VolumeData,
        atlas_in_target: VolumeData,
        warped_references: Mapping[str, VolumeData],
        result,
        center_lps: Iterable[float],
    ) -> None:
        super().__init__(parent)
        registration_type = getattr(result, "registration_type", "K04 multi-reference")
        is_k04 = len(result.routes) == 4
        self.setWindowTitle(f"{registration_type} — Quality Check")
        self.resize(1480, 900)
        root = QtWidgets.QVBoxLayout(self)

        qc_color = "#e4f6e9" if result.qc.passed else "#ffe1e1"
        qc_text = "PASS" if result.qc.passed else "FAIL"
        route_title = "K04 equal-weight forward consensus" if is_k04 else "J0476M BRAINSFit forward route"
        summary = QtWidgets.QLabel(
            f"<b>{route_title}</b>&nbsp;&nbsp; "
            f"Method: <b>{result.method}</b>&nbsp;&nbsp; "
            f"Landmarks: <b>{len(result.landmark_subset.labels)}</b>&nbsp;&nbsp; "
            f"Transform QC: <b>{qc_text}</b>&nbsp;&nbsp; "
            f"Consensus approximation P95: "
            f"<b>{result.qc.consensus_approximation.p95_mm:.4f} mm</b>"
        )
        summary.setStyleSheet(f"font-size: 15px; padding: 9px; background: {qc_color}; color: #10233f;")
        root.addWidget(summary)

        inverse_qc = getattr(result, "inverse_qc", None)
        inverse_generated = getattr(result, "inverse", None) is not None
        inverse_text = ""
        if inverse_qc is not None:
            inverse_text = (
                f" Inverse QC: {'PASS' if inverse_qc.passed else 'FAIL'}, "
                f"round-trip P95 {inverse_qc.roundtrip.p95_mm:.4f} mm, "
                f"valid samples {inverse_qc.converged_target_samples}/{inverse_qc.target_sample_count}, "
                f"Atlas coverage {inverse_qc.atlas_coverage_fraction:.2%} (informational only); "
                f"3A {'generated' if inverse_generated else 'not generated'}."
            )
        information_text = (
            "Reference-wise FRE is displayed as landmark-registration QC only. "
            "It is not used as an Atlas-mapping accuracy surrogate, reference-selection rule, or weight."
            if is_k04
            else "The displayed landmark residual is a post-BRAINSFit landmark check; BRAINSFit optimizes image intensity, not FRE."
        )
        information = QtWidgets.QLabel(information_text + inverse_text)
        information.setWordWrap(True)
        information.setStyleSheet("padding: 9px; background: #e8f2ff; color: #183b66;")
        root.addWidget(information)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        tabs = QtWidgets.QTabWidget()
        overlays = [("Atlas MRI consensus", atlas_in_target), *sorted(warped_references.items())]
        self.overlay_sets: list[dict[str, OverlaySliceView]] = []
        center_index = base.physical_to_index(tuple(center_lps))
        self.index_xyz = center_index.copy()
        for name, overlay in overlays:
            tab = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(tab)
            legend = QtWidgets.QLabel(
                f"Red = {name}; Green = Target CT; Yellow = agreement. Slices are linked within this tab."
            )
            layout.addWidget(legend)
            views_layout = QtWidgets.QHBoxLayout()
            views = {
                orientation: OverlaySliceView(orientation, base, overlay)
                for orientation in ORIENTATIONS
            }
            for view in views.values():
                view.set_state(center_index, {}, "")
                view.slice_changed.connect(
                    lambda orientation, value, current=views: self._linked_slice_changed(
                        current, orientation, value
                    )
                )
                views_layout.addWidget(view, 1)
            self.overlay_sets.append(views)
            layout.addLayout(views_layout, 1)
            tabs.addTab(tab, name)
        splitter.addWidget(tabs)

        metrics = QtWidgets.QWidget()
        metrics_layout = QtWidgets.QHBoxLayout(metrics)
        route_table = QtWidgets.QTableWidget(len(result.routes), 6)
        route_table.setHorizontalHeaderLabels(
            ["Reference", "FRE RMS (mm)", "Mean (mm)", "Maximum (mm)", "Scale", "Route approx. P95 (mm)"]
        )
        for row, route in enumerate(result.routes):
            registration = route.registration
            approximation = result.qc.component_approximation[route.reference.reference_id]
            values = (
                route.reference.reference_id,
                f"{registration.rms_mm:.4f}",
                f"{registration.mean_mm:.4f}",
                f"{registration.maximum_mm:.4f}",
                f"{registration.uniform_scale:.6f}",
                f"{approximation.p95_mm:.6f}",
            )
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                route_table.setItem(row, column, item)
        route_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        metrics_layout.addWidget(route_table, 2)

        uncertainty_table = QtWidgets.QTableWidget(3, 4)
        uncertainty_table.setHorizontalHeaderLabels(["Uncertainty", "Mean", "P95", "Maximum"])
        uncertainty_items = (
            ("RMS from consensus", result.uncertainty.rms_from_consensus),
            ("Maximum from consensus", result.uncertainty.maximum_from_consensus),
            ("Maximum pairwise", result.uncertainty.maximum_pairwise),
        )
        for row, (name, image) in enumerate(uncertainty_items):
            values = np.asarray(sitk.GetArrayViewFromImage(image))
            finite = values[np.isfinite(values)]
            cells = (name, f"{np.mean(finite):.3f}", f"{np.percentile(finite, 95):.3f}", f"{np.max(finite):.3f}")
            for column, value in enumerate(cells):
                uncertainty_table.setItem(row, column, QtWidgets.QTableWidgetItem(value))
        uncertainty_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        metrics_layout.addWidget(uncertainty_table, 1)
        splitter.addWidget(metrics)
        splitter.setSizes([590, 210])
        root.addWidget(splitter, 1)

        note_text = (
            "Primary implementation: FConsensus(x) = x + mean(Fi(x) - x), equal weight for all four references. "
            if is_k04
            else "General route: Landmark (Skull-all) Rigid initialization to J0476M, followed by BRAINSFit refinement. "
        )
        note = QtWidgets.QLabel(
            note_text + "An Atlas-grid inverse is emitted only when round-trip QC passes."
        )
        note.setWordWrap(True)
        root.addWidget(note)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _linked_slice_changed(
        self,
        views: Mapping[str, OverlaySliceView],
        orientation: str,
        value: int,
    ) -> None:
        axis = {"Sagittal": 0, "Coronal": 1, "Axial": 2}[orientation]
        self.index_xyz[axis] = value
        for view in views.values():
            view.set_state(self.index_xyz, {}, "")
