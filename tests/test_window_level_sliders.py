"""Display contrast sliders: normalized CT, HU, session restore and no mutation."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
import SimpleITK as sitk
from PySide6 import QtWidgets

from marmoset_atlas_mapper.imaging import VolumeData
from marmoset_atlas_mapper.widgets import UNLABELED_VIEWS, VolumePanel


@pytest.fixture
def panel():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    widget = VolumePanel("Target CT", interactive=True, view_specs=UNLABELED_VIEWS,
                         window_level_controls=True)
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def make_volume(low=0.0, high=1.0):
    image = sitk.GetImageFromArray(np.linspace(low, high, 720).reshape(8, 9, 10))
    image.SetSpacing((0.1, 0.2, 0.3))
    image.SetOrigin((10.0, -5.0, 2.0))
    return VolumeData.from_image(image)


def expected_slider_value(control, kind, position):
    low, high = control._slider_ranges[kind]
    return round(low + (high - low) * position / control.SLIDER_STEPS, 6)


@pytest.mark.parametrize("bounds", [(0, 1), (-1024, 3071), (-0.5, 0.5), (0, 0.00001)])
def test_sliders_adapt_and_update_one_parameter_once(panel, bounds):
    control = panel.window_level_control
    assert not control.isEnabled()
    volume = make_volume(*bounds)
    panel.set_volume(volume)
    changes = []
    control.changed.connect(lambda: changes.append((volume.window, volume.level)))
    initial_level = volume.level
    expected_window = expected_slider_value(control, "window", 2500)
    control.window_slider.setValue(2500)
    assert volume.window == pytest.approx(expected_window, abs=1e-10)
    assert volume.level == pytest.approx(initial_level, abs=1e-10)
    assert control.window_spin.value() == pytest.approx(volume.window, abs=5.1e-7)
    assert len(changes) == 1
    expected_level = expected_slider_value(control, "level", 7000)
    control.level_slider.setValue(7000)
    assert volume.level == pytest.approx(expected_level, abs=1e-10)
    assert volume.window == pytest.approx(expected_window, abs=1e-10)
    assert len(changes) == 2
    control.window_slider.setValue(0)
    assert volume.window > 0
    assert volume.window == pytest.approx(control.MIN_WINDOW, abs=1e-10)
    assert len(changes) == 3


def test_manual_values_expand_ranges_without_clipping_or_quantization(panel):
    volume = make_volume()
    panel.set_volume(volume)
    control = panel.window_level_control
    changes = []
    control.changed.connect(lambda: changes.append(True))
    control.window_spin.setValue(123.456789)
    control.level_spin.setValue(-250.123456)
    assert volume.window == pytest.approx(123.456789)
    assert volume.level == pytest.approx(-250.123456)
    assert control.window_slider.value() == control.SLIDER_STEPS
    assert control.level_slider.value() == 0
    assert control._slider_ranges["window"][1] >= volume.window
    assert control._slider_ranges["level"][0] <= volume.level
    assert len(changes) == 2
    window = volume.window
    control.level_slider.setValue(2000)
    assert volume.window == pytest.approx(window)
    assert len(changes) == 3


def test_reset_restores_values_ranges_and_no_feedback_loop(panel):
    volume = make_volume()
    panel.set_volume(volume)
    control = panel.window_level_control
    initial = (volume.window, volume.level)
    ranges = control._slider_ranges.copy()
    control.window_spin.setValue(40)
    control.level_spin.setValue(-20)
    changes = []
    control.changed.connect(lambda: changes.append(True))
    control.reset_button.click()
    assert (volume.window, volume.level) == initial
    assert control._slider_ranges == ranges
    assert len(changes) == 1
    control.sync()
    assert len(changes) == 1


def test_new_ct_and_restored_values_resynchronize_sliders(panel):
    panel.set_volume(make_volume(-1024, 3071))
    control = panel.window_level_control
    control.window_spin.setValue(10000)
    volume = make_volume()
    panel.set_volume(volume)
    assert control._slider_ranges["window"][1] < 3.0
    volume.set_window_level(4.123456, 50.654321)
    changes = []
    control.changed.connect(lambda: changes.append(True))
    control.sync()
    assert changes == []
    assert control.window_spin.value() == pytest.approx(4.123456)
    assert control.level_spin.value() == pytest.approx(50.654321)
    assert control.window_slider.value() == control.SLIDER_STEPS
    assert control.level_slider.value() == control.SLIDER_STEPS


def test_sliders_refresh_all_views_without_modifying_data_or_landmarks(panel):
    volume = make_volume(-1024, 3071)
    panel.set_volume(volume)
    panel.set_points({"LM01": (10.3, -4.2, 2.9)}, "LM01")
    geometry = (volume.image.GetOrigin(), volume.image.GetSpacing(), volume.image.GetDirection())
    array = sitk.GetArrayFromImage(volume.image)
    display_array = volume.array_zyx.copy()
    index = panel.index_xyz.copy()
    before = {name: view.canvas._image.copy() for name, view in panel.views.items()}
    control = panel.window_level_control
    control.window_slider.setValue(1500)
    control.level_slider.setValue(6000)
    assert all(view.volume is volume for view in panel.views.values())
    assert all(view.canvas._image != before[name] for name, view in panel.views.items())
    np.testing.assert_array_equal(sitk.GetArrayFromImage(volume.image), array)
    np.testing.assert_array_equal(volume.array_zyx, display_array)
    assert (volume.image.GetOrigin(), volume.image.GetSpacing(), volume.image.GetDirection()) == geometry
    np.testing.assert_array_equal(panel.index_xyz, index)
    np.testing.assert_array_equal(panel.points_lps["LM01"], [10.3, -4.2, 2.9])
    assert list(panel.views) == ["Axial", "Sagittal", "Coronal"]


def test_constant_ct_keeps_valid_slider_ranges(panel):
    volume = make_volume(7, 7)
    panel.set_volume(volume)
    control = panel.window_level_control
    control.window_slider.setValue(0)
    control.level_slider.setValue(control.SLIDER_STEPS)
    assert np.isfinite([volume.window, volume.level]).all()
    assert volume.window > 0
    control.reset_button.click()
    assert volume.window == 1.0
