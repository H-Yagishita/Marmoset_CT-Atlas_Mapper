from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Mapping

import numpy as np
import SimpleITK as sitk
from PySide6 import QtCore, QtGui, QtWidgets

from .imaging import VolumeData, normalize_to_uint8


ORIENTATIONS = ("Axial", "Coronal", "Sagittal")


def atlas_layer_display_name(name: str) -> str:
    """Keep saved layer identifiers separate from their image labels."""
    return {"MRI": "MR image", "Atlas MRI": "Atlas MR image"}.get(name, name)


# Dataset v2 uses the reoriented manuscript J0476M CT. VolumeData presents its
# voxels in LPS order. Keep the familiar horizontal/sagittal/coronal panel order,
# but do not reuse the old dataset's swapped anatomical labels.
J0476M_REFERENCE_VIEWS = (
    ("Axial", "Horizontal (Axial)", {"left": "R", "right": "L", "top": "A", "bottom": "P"}),
    ("Sagittal", "Sagittal", {"left": "A", "right": "P", "top": "D", "bottom": "V"}),
    ("Coronal", "Coronal", {"left": "R", "right": "L", "top": "D", "bottom": "V"}),
)
# Match the reference panel order without assigning anatomical labels to the target.
UNLABELED_VIEWS = tuple((orientation, "", {}) for orientation, _, _ in J0476M_REFERENCE_VIEWS)


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
            rect.left() + (image_x + 0.5) * rect.width() / max(self._image_size.width(), 1),
            rect.top() + (image_y + 0.5) * rect.height() / max(self._image_size.height(), 1),
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
        x = (position.x() - rect.left()) * self._image_size.width() / max(rect.width(), 1.0) - 0.5
        y = (position.y() - rect.top()) * self._image_size.height() / max(rect.height(), 1.0) - 0.5
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
        self.title.setStyleSheet("font-weight: 600; color: #25354a;")
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


class WindowLevelControl(QtWidgets.QWidget):
    """Display-only CT contrast; never modifies voxels or registration inputs."""
    changed = QtCore.Signal()
    SLIDER_STEPS = 10000
    MIN_WINDOW = 0.000001

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.volume = None
        self.window_spin = QtWidgets.QDoubleSpinBox()
        self.level_spin = QtWidgets.QDoubleSpinBox()
        for spin in (self.window_spin, self.level_spin):
            spin.setDecimals(6)
            spin.setKeyboardTracking(False)
            spin.setRange(-1e12, 1e12)
            spin.setMinimumWidth(110)
        self.window_spin.setMinimum(0.000001)
        self.window_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.level_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self._slider_ranges = {"window": (self.MIN_WINDOW, 2.0), "level": (-0.5, 1.5)}
        for name, slider in (("Window", self.window_slider), ("Level", self.level_slider)):
            slider.setRange(0, self.SLIDER_STEPS)
            slider.setPageStep(100)
            slider.setMinimumWidth(100)
            slider.setAccessibleName(name)
            slider.setToolTip(f"Drag to adjust {name.lower()}; use the number field for an exact value.")
        self.reset_button = QtWidgets.QPushButton("Reset contrast")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for label, slider, spin, kind in (
            ("Window:", self.window_slider, self.window_spin, "window"),
            ("Level:", self.level_slider, self.level_spin, "level"),
        ):
            layout.addWidget(QtWidgets.QLabel(label))
            layout.addWidget(slider, 1)
            layout.addWidget(spin)
            spin.valueChanged.connect(lambda value, k=kind: self._apply(k, value))
            slider.valueChanged.connect(lambda value, k=kind: self._apply_slider(k, value))
        layout.addWidget(self.reset_button)
        self.reset_button.clicked.connect(self._reset)
        self.setToolTip("Display contrast only. Supports both HU and normalized CT intensities.")
        self.setEnabled(False)

    def set_volume(self, volume: VolumeData) -> None:
        self.volume = volume
        self._reset_slider_ranges()
        self.setEnabled(True)
        self.sync()

    def _reset_slider_ranges(self) -> None:
        # The same robust intensity range used by Auto/Reset keeps normalized
        # CTs usable and prevents isolated bright metal voxels dominating the UI.
        low = float(self.volume.default_window_min)
        high = float(self.volume.default_window_max)
        span = max(high - low, self.MIN_WINDOW)
        self._slider_ranges = {
            "window": (self.MIN_WINDOW, min(max(2.0 * span, 2.0 * self.MIN_WINDOW), 1e12)),
            "level": (max(low - 0.5 * span, -1e12), min(high + 0.5 * span, 1e12)),
        }

    def _sync_sliders(self) -> None:
        for kind, slider, value in (
            ("window", self.window_slider, self.volume.window),
            ("level", self.level_slider, self.volume.level),
        ):
            low, high = self._slider_ranges[kind]
            # Manual values and restored sessions must never be clipped to the
            # initial slider range. Keep that range stable while dragging.
            low, high = min(low, value), max(high, value)
            self._slider_ranges[kind] = (low, high)
            position = int(round(self.SLIDER_STEPS * (value - low) / (high - low)))
            blocker = QtCore.QSignalBlocker(slider)
            slider.setValue(position)
            del blocker

    def sync(self) -> None:
        if self.volume is None:
            return
        for spin, value in ((self.window_spin, self.volume.window), (self.level_spin, self.volume.level)):
            blocker = QtCore.QSignalBlocker(spin)
            spin.setSingleStep(max(abs(self.volume.window) / 100.0, 0.000001))
            spin.setValue(value)
            del blocker
        self._sync_sliders()

    def _apply(self, kind: str, value: float) -> None:
        if self.volume is not None:
            window = value if kind == "window" else self.volume.window
            level = value if kind == "level" else self.volume.level
            self.volume.set_window_level(window, level)
            self.sync()
            self.changed.emit()

    def _apply_slider(self, kind: str, position: int) -> None:
        if self.volume is None:
            return
        low, high = self._slider_ranges[kind]
        value = low + (high - low) * position / self.SLIDER_STEPS
        spin = self.window_spin if kind == "window" else self.level_spin
        blocker = QtCore.QSignalBlocker(spin)
        spin.setValue(value)
        del blocker
        self._apply(kind, spin.value())

    def _reset(self) -> None:
        if self.volume is not None:
            self.volume.reset_window_level()
            self._reset_slider_ranges()
            self.sync()
            self.changed.emit()


class VolumePanel(QtWidgets.QGroupBox):
    point_clicked = QtCore.Signal(object)
    state_changed = QtCore.Signal()

    def __init__(
        self,
        title: str,
        *,
        interactive: bool,
        view_specs=None,
        window_level_controls: bool = False,
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
        layout = QtWidgets.QVBoxLayout(self)
        self.window_level_control = WindowLevelControl() if window_level_controls else None
        if self.window_level_control is not None:
            layout.addWidget(self.window_level_control)
            self.window_level_control.changed.connect(self.refresh)
        views_layout = QtWidgets.QHBoxLayout()
        layout.addLayout(views_layout, 1)
        for view in self.views.values():
            views_layout.addWidget(view, 1)
            view.slice_changed.connect(self._slice_changed)
            if interactive:
                view.index_clicked.connect(self._index_clicked)

    def set_volume(self, volume: VolumeData) -> None:
        self.volume = volume
        if self.window_level_control is not None:
            self.window_level_control.set_volume(volume)
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
        self.state_changed.emit()

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
        rgb[..., 2] = overlay_gray
        self.canvas.set_array(
            rgb,
            plane_pixel_spacing(self.orientation, self.volume.display_image.GetSpacing()),
        )
        self.canvas.set_overlays(crosshair, [])
        current_slice = int(round(self.index_xyz[self._axis()]))
        self.position_label.setText(f"{current_slice + 1} / {self.slider.maximum() + 1}")


class OverlayContrastControl(QtWidgets.QWidget):
    """Independent display windows for the two overlay channels."""

    changed = QtCore.Signal()

    def __init__(self, base: VolumeData, parent=None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        green_label = QtWidgets.QLabel("Green · Target CT")
        # Retain internal names used by existing QC automation; the channel is magenta.
        self.red_label = QtWidgets.QLabel("Magenta")
        self.green_control = WindowLevelControl()
        self.red_control = WindowLevelControl()
        for row, label, control, color in (
            (0, green_label, self.green_control, "#178340"),
            (1, self.red_label, self.red_control, "#a21caf"),
        ):
            label.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            label.setStyleSheet(f"color: {color}; font-weight: bold;")
            layout.addWidget(label, row, 0)
            layout.addWidget(control, row, 1)
            control.changed.connect(self.changed.emit)
            control.setToolTip("Display only; image data and transforms are unchanged.")
        layout.setColumnStretch(1, 1)
        self.green_control.set_volume(base)

    def set_red_volume(self, name: str, volume: VolumeData) -> None:
        self.red_label.setText(f"Magenta · {atlas_layer_display_name(name)}")
        self.red_control.set_volume(volume)


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
            raise ValueError("This result has no atlas layers to display.")
        self.setWindowTitle("Atlas Viewer")
        self.resize(1350, 720)
        # Share image buffers, but keep contrast local to this viewer. In
        # particular, using the same VolumeData for two channels stays safe.
        self.base = replace(base)
        self.layers = {name: replace(volume) for name, volume in layers.items()}
        self.index_xyz = base.physical_to_index(tuple(center_lps))
        root = QtWidgets.QVBoxLayout(self)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Atlas layer:"))
        self.layer_combo = QtWidgets.QComboBox()
        for name in self.layers:
            self.layer_combo.addItem(atlas_layer_display_name(name), name)
        if initial_layer in self.layers:
            self.layer_combo.setCurrentIndex(self.layer_combo.findData(initial_layer))
        row.addWidget(self.layer_combo, 1)
        root.addLayout(row)
        self.contrast = OverlayContrastControl(self.base)
        root.addWidget(self.contrast)
        self.views_host = QtWidgets.QWidget()
        self.views_layout = QtWidgets.QHBoxLayout(self.views_host)
        root.addWidget(self.views_host, 1)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.layer_combo.currentIndexChanged.connect(
            lambda index: self._set_layer(self.layer_combo.itemData(index))
        )
        self.views: dict[str, OverlaySliceView] = {}
        self._set_layer(self.layer_combo.currentData())
        self.contrast.changed.connect(self._refresh_contrast)

    def _set_layer(self, name: str) -> None:
        while self.views_layout.count():
            item = self.views_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.contrast.set_red_volume(name, self.layers[name])
        self.views = {
            orientation: OverlaySliceView(orientation, self.base, self.layers[name])
            for orientation in ORIENTATIONS
        }
        for view in self.views.values():
            view.title.setText("")
            view.set_state(self.index_xyz, {}, "")
            view.slice_changed.connect(self._slice_changed)
            self.views_layout.addWidget(view, 1)

    def _refresh_contrast(self) -> None:
        for view in self.views.values():
            view.refresh()

    def _slice_changed(self, orientation: str, value: int) -> None:
        axis = {"Sagittal": 0, "Coronal": 1, "Axial": 2}[orientation]
        self.index_xyz[axis] = value
        for view in self.views.values():
            view.set_state(self.index_xyz, {}, "")


class MultiReferenceQualityCheckDialog(QtWidgets.QDialog):
    """Display-only QC; numerical diagnostics remain in the saved results."""

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
        registration_type = getattr(result, "registration_type", "Registration")
        self.setWindowTitle(f"{registration_type} — Quality Check")
        self.resize(1480, 800)
        root = QtWidgets.QVBoxLayout(self)

        inverse_qc = getattr(result, "inverse_qc", None)
        inverse_generated = getattr(result, "inverse", None) is not None
        inverse_status = "Not checked" if inverse_qc is None else ("PASS" if inverse_qc.passed else "FAIL")
        qc_passed = result.qc.passed and (inverse_qc is None or inverse_qc.passed)
        self.summary = QtWidgets.QLabel(
            f"{result.method}  ·  Nref = {len(result.routes)}  ·  "
            f"Landmarks = {len(result.landmark_subset.labels)}  |  "
            f"Forward QC: {'PASS' if result.qc.passed else 'FAIL'}  ·  "
            f"Inverse QC: {inverse_status}"
        )
        self.summary.setStyleSheet(
            f"padding: 8px; background: {'#e4f6e9' if qc_passed else '#ffe1e1'}; color: #10233f;"
        )
        root.addWidget(self.summary)
        # Keep failed/missing outputs explicit without displaying FRE as an
        # atlas-accuracy score. The detailed QC values are saved to disk.
        if not result.qc.passed or not inverse_generated:
            messages = []
            if not result.qc.passed:
                messages.append("Forward transform QC failed.")
            if not inverse_generated:
                messages.append("The CT in atlas space was not saved because the inverse transform is unavailable.")
            warning = QtWidgets.QLabel(" ".join(messages))
            warning.setObjectName("qc_output_warning")
            warning.setWordWrap(True)
            warning.setStyleSheet("color: #a62727; padding: 4px;")
            root.addWidget(warning)

        self.base = replace(base)
        self.overlays = [
            ("Atlas MRI", replace(atlas_in_target)),
            *[(name, replace(volume)) for name, volume in sorted(warped_references.items())],
        ]
        self.contrast = OverlayContrastControl(self.base)
        root.addWidget(self.contrast)
        self.tabs = QtWidgets.QTabWidget()
        self.overlay_sets: list[dict[str, OverlaySliceView]] = []
        center_index = base.physical_to_index(tuple(center_lps))
        self.index_xyz = center_index.copy()
        for name, overlay in self.overlays:
            tab = QtWidgets.QWidget()
            layout = QtWidgets.QHBoxLayout(tab)
            views = {
                orientation: OverlaySliceView(orientation, self.base, overlay)
                for orientation in ORIENTATIONS
            }
            for view in views.values():
                view.set_state(center_index, {}, "")
                view.slice_changed.connect(
                    lambda orientation, value, current=views: self._linked_slice_changed(
                        current, orientation, value
                    )
                )
                layout.addWidget(view, 1)
            self.overlay_sets.append(views)
            self.tabs.addTab(tab, atlas_layer_display_name(name))
        root.addWidget(self.tabs, 1)
        self.tabs.currentChanged.connect(self._select_overlay)
        self.contrast.changed.connect(self._refresh_contrast)
        self._select_overlay(0)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _select_overlay(self, index: int) -> None:
        if index < 0:
            return
        name, volume = self.overlays[index]
        self.contrast.set_red_volume(name, volume)
        self._refresh_contrast()

    def _refresh_contrast(self) -> None:
        # Only redraw the visible tab during slider drags. Other tabs pick up
        # the shared green window on activation, with their own magenta window.
        index = self.tabs.currentIndex()
        if index >= 0:
            for view in self.overlay_sets[index].values():
                view.refresh()

    def _linked_slice_changed(
        self,
        views: Mapping[str, OverlaySliceView],
        orientation: str,
        value: int,
    ) -> None:
        axis = {"Sagittal": 0, "Coronal": 1, "Axial": 2}[orientation]
        self.index_xyz = next(iter(views.values())).index_xyz.copy()
        self.index_xyz[axis] = value
        for view in views.values():
            view.set_state(self.index_xyz, {}, "")
