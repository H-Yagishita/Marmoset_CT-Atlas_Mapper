"""Target panel reordering must not change image geometry or interaction axes."""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
import SimpleITK as sitk
from PySide6 import QtWidgets

from marmoset_atlas_mapper.imaging import VolumeData
from marmoset_atlas_mapper.widgets import (
    REFERENCE_VIEWS,
    ORIENTATIONS,
    UNLABELED_VIEWS,
    VolumePanel,
    index_to_display_xy,
)


@pytest.fixture
def target_panel(tmp_path):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    image = sitk.GetImageFromArray(np.arange(9 * 8 * 7, dtype=np.float32).reshape(9, 8, 7))
    image.SetSpacing((0.3, 0.5, 0.7))
    image.SetOrigin((12.0, -8.0, 3.0))
    # Non-identity geometry ensures click tests use physical coordinates.
    angle = np.deg2rad(12.0)
    image.SetDirection((np.cos(angle), -np.sin(angle), 0.0,
                        np.sin(angle), np.cos(angle), 0.0, 0.0, 0.0, 1.0))
    path = tmp_path / "TargetCT.nrrd"
    sitk.WriteImage(image, str(path))
    volume = VolumeData.read(path)
    panel = VolumePanel("Target CT", interactive=True, view_specs=UNLABELED_VIEWS,
                        window_level_controls=True)
    panel.set_volume(volume)
    yield panel, volume, app
    panel.close()
    panel.deleteLater()
    app.processEvents()


def test_target_layout_matches_reference_without_relabeling_other_viewers(target_panel):
    panel, _, _ = target_panel
    expected = ["Axial", "Sagittal", "Coronal"]
    assert list(panel.views) == expected
    assert [view[0] for view in REFERENCE_VIEWS] == expected
    assert ORIENTATIONS == ("Axial", "Coronal", "Sagittal")
    layout = panel.layout().itemAt(1).layout()
    assert [layout.itemAt(i).widget().orientation for i in range(3)] == expected
    assert all(view.title.text() == "" for view in panel.views.values())
    assert all(labels == {} for _, _, labels in UNLABELED_VIEWS)


def test_target_slices_and_landmark_coordinates_are_unchanged(target_panel):
    panel, volume, _ = target_panel
    image = volume.image
    original_array = sitk.GetArrayFromImage(image)
    original_geometry = (image.GetOrigin(), image.GetSpacing(), image.GetDirection())
    index = np.array([2.0, 3.0, 4.0])
    point = volume.index_to_physical(index)
    panel.jump_to_physical(point)
    panel.set_points({"LM01": point}, "LM01")
    arr = volume.array_zyx
    expected = {"Axial": arr[4, :, :], "Sagittal": np.flipud(arr[:, :, 2]),
                "Coronal": np.flipud(arr[:, 3, :])}
    clicks = []
    panel.point_clicked.connect(clicks.append)
    for orientation, view in panel.views.items():
        np.testing.assert_array_equal(view._plane_and_xy()[0], expected[orientation])
        xy = index_to_display_xy(index, orientation, volume.display_image.GetSize())
        np.testing.assert_allclose(view._point_xy(index), xy)
        view.canvas.clicked.emit(*xy)
        np.testing.assert_allclose(clicks[-1], point, atol=1e-10)
        np.testing.assert_allclose(panel.index_xyz, index, atol=1e-10)
    np.testing.assert_array_equal(sitk.GetArrayFromImage(image), original_array)
    assert (image.GetOrigin(), image.GetSpacing(), image.GetDirection()) == original_geometry


@pytest.mark.parametrize("orientation,axis", [("Axial", 2), ("Sagittal", 0), ("Coronal", 1)])
def test_reordered_sliders_move_their_original_axes(target_panel, orientation, axis):
    panel, _, _ = target_panel
    expected = panel.index_xyz.copy()
    expected[axis] = 1
    panel.views[orientation].slider.setValue(1)
    np.testing.assert_allclose(panel.index_xyz, expected)
    for view in panel.views.values():
        np.testing.assert_allclose(view.index_xyz, expected)
