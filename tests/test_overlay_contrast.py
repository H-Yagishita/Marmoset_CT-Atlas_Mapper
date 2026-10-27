"""QC and Atlas viewer: independent RGB display contrast, no data mutation."""
import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
import SimpleITK as sitk
from PySide6 import QtWidgets

from marmoset_atlas_mapper.imaging import VolumeData
from marmoset_atlas_mapper.widgets import (
    AtlasLayerViewerDialog, MultiReferenceQualityCheckDialog, QualityCheckDialog,
)


def result(passed=True, inverse_passed=True):
    # Deliberately omit FRE/residual attributes: these belong to saved data,
    # not to the display contract.
    return SimpleNamespace(method="Rigid", registration_type="Landmark (Skull-base)",
        routes=[object()] * 6, landmark_subset=SimpleNamespace(labels=tuple(range(8))),
        qc=SimpleNamespace(passed=passed), inverse_qc=SimpleNamespace(passed=inverse_passed),
        inverse=object() if inverse_passed else None)


@pytest.fixture(params=["qc", "atlas"])
def viewer(request):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    image = sitk.GetImageFromArray(np.linspace(0., 1., 720).reshape(8, 9, 10))
    image.SetSpacing((0.1, 0.2, 0.3))
    volume = VolumeData.from_image(image)
    center = volume.index_to_physical((4, 4, 4))
    if request.param == "qc":
        dialog = MultiReferenceQualityCheckDialog(None, volume, volume,
            {f"Ref{i}": volume for i in range(6)}, result(), center)
        select = dialog.tabs.setCurrentIndex
        views = lambda: dialog.overlay_sets[dialog.tabs.currentIndex()]
    else:
        dialog = AtlasLayerViewerDialog(None, volume, {"MRI": volume, "Nissl": volume}, center)
        select = dialog.layer_combo.setCurrentIndex
        views = lambda: dialog.views
    yield SimpleNamespace(dialog=dialog, original=volume, views=views, select=select, app=app)
    dialog.close()
    dialog.deleteLater()
    app.processEvents()


def pixels(view):
    image = view.canvas._image
    return np.asarray([[image.pixelColor(x, y).getRgb()[:3]
        for x in range(image.width())] for y in range(image.height())])


def test_channel_changes_refresh_pixels_independently(viewer):
    dialog = viewer.dialog
    control = dialog.contrast
    original = viewer.original
    old_window = (original.window_min, original.window_max)
    old_array = original.array_zyx.copy()
    old_geometry = (original.image.GetOrigin(), original.image.GetSpacing(), original.image.GetDirection())
    before = {key: pixels(view) for key, view in viewer.views().items()}
    index = dialog.index_xyz.copy()
    control.green_control.level_spin.setValue(0.25)
    for key, view in viewer.views().items():
        after = pixels(view)
        np.testing.assert_array_equal(after[..., 0], before[key][..., 0])
        assert np.any(after[..., 1] != before[key][..., 1])
        assert not np.any(after[..., 2])
    green = {key: pixels(view) for key, view in viewer.views().items()}
    control.red_control.window_slider.setValue(2500)
    control.red_control.level_slider.setValue(6000)
    for key, view in viewer.views().items():
        after = pixels(view)
        np.testing.assert_array_equal(after[..., 1], green[key][..., 1])
        assert np.any(after[..., 0] != green[key][..., 0])
        np.testing.assert_array_equal(view.index_xyz, index)
    assert (original.window_min, original.window_max) == old_window
    np.testing.assert_array_equal(original.array_zyx, old_array)
    np.testing.assert_array_equal(sitk.GetArrayFromImage(original.image), old_array)
    assert old_geometry == (original.image.GetOrigin(), original.image.GetSpacing(), original.image.GetDirection())


def test_channel_reset_and_per_layer_persistence(viewer):
    c = viewer.dialog.contrast
    c.green_control.level_spin.setValue(0.2)
    c.red_control.level_spin.setValue(0.7)
    red_first = c.red_control.volume
    viewer.select(1)
    assert c.red_control.volume is not red_first
    assert c.green_control.volume.level == pytest.approx(0.2)
    c.red_control.level_spin.setValue(0.3)
    red_second = c.red_control.volume
    viewer.select(0)
    assert c.red_control.volume is red_first
    assert c.red_control.level_spin.value() == pytest.approx(0.7)
    c.red_control.reset_button.click()
    assert red_first.window_min == red_first.default_window_min
    assert c.green_control.volume.level == pytest.approx(0.2)
    viewer.select(1)
    assert c.red_control.level_spin.value() == pytest.approx(0.3)
    c.green_control.reset_button.click()
    assert c.green_control.volume.window_min == c.green_control.volume.default_window_min
    assert red_second.level == pytest.approx(0.3)


def test_no_fre_or_residual_tables_displayed(viewer):
    text = " ".join(label.text() for label in viewer.dialog.findChildren(QtWidgets.QLabel))
    assert "FRE" not in text and "residual" not in text.lower()
    assert "Yellow = agreement" not in text
    assert not viewer.dialog.findChildren(QtWidgets.QTableWidget)


@pytest.mark.parametrize("forward,inverse", [(False, False), (True, False)])
def test_qc_failures_remain_visible(forward, inverse):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    v = VolumeData.from_image(sitk.GetImageFromArray(np.arange(125.).reshape(5, 5, 5)))
    dialog = MultiReferenceQualityCheckDialog(None, v, v, {}, result(forward, inverse), (2, 2, 2))
    assert f"Forward QC: {'PASS' if forward else 'FAIL'}" in dialog.summary.text()
    assert "Inverse QC: FAIL" in dialog.summary.text()
    warning = dialog.findChild(QtWidgets.QLabel, "qc_output_warning")
    assert warning is not None and "was not saved" in warning.text()
    dialog.close()
    dialog.deleteLater()
    app.processEvents()


def test_legacy_qc_uses_the_same_contrast_controls():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    v = VolumeData.from_image(sitk.GetImageFromArray(np.arange(125.).reshape(5, 5, 5)))
    dialog = QualityCheckDialog(None, v, v, result(), (2, 2, 2), "Ref", None)
    assert len(dialog.overlay_views) == 3
    assert dialog.contrast.green_control.volume is not dialog.contrast.red_control.volume
    dialog.close()
    dialog.deleteLater()
    app.processEvents()
