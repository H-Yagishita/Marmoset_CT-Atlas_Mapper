"""The guide reference shown for landmark placement can be changed and is remembered."""
import os
from dataclasses import replace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import numpy as np
import pytest
import SimpleITK as sitk
from PySide6 import QtCore, QtWidgets

from marmoset_atlas_mapper import main_window as mw
from marmoset_atlas_mapper.landmarks import write_slicer_markups
from marmoset_atlas_mapper.profile import load_profiles
from marmoset_atlas_mapper.reference_library import AtlasLayer, ReferenceEntry, load_reference_library
from marmoset_atlas_mapper.widgets import REFERENCE_VIEWS


def _write_reference(root, reference_id, offset):
    ct = root / f"{reference_id}_CT.nrrd"
    image = sitk.GetImageFromArray(np.arange(1000, dtype=np.float32).reshape(10, 10, 10))
    image.SetOrigin((offset, 0.0, 0.0))
    sitk.WriteImage(image, str(ct))
    points = {f"LM{i:02d}": np.array([offset + 1 + (i % 7), 1 + (i % 5), 1 + (i % 3)], float)
              for i in range(1, 14)}
    marks = root / f"{reference_id}_Landmarks.mrk.json"
    write_slicer_markups(marks, points)
    return ct, marks, points


@pytest.fixture
def guide_setup(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    forward = tmp_path / "Forward.h5"
    sitk.WriteTransform(sitk.AffineTransform(3), str(forward))
    labels = tmp_path / "Labels.nrrd"
    sitk.WriteImage(sitk.Image(10, 10, 10, sitk.sitkUInt16), str(labels))
    ctbl = tmp_path / "labels.ctbl"
    ctbl.write_text("0 Background 0 0 0 0\n", encoding="utf-8")
    profiles, expected = [], {}
    templates = {p.reference_id: p for p in load_profiles()}
    for offset, reference_id in enumerate(("HH0312F", "J0476M")):
        ct, marks, points = _write_reference(tmp_path, reference_id, 50.0 * offset)
        expected[reference_id] = points
        profiles.append(replace(
            templates[reference_id], reference_ct=ct, reference_landmarks=marks,
            reference_to_atlas_point_transform=forward, atlas_reference=ct, atlas_label_map=labels,
            atlas_color_table=ctbl, atlas_layers=()))
    template = load_reference_library(validate_files=False)
    library = replace(
        template,
        references=tuple(ReferenceEntry(r.reference_id, profiles[0].reference_ct,
                                        profiles[0].reference_landmarks, forward) for r in template.references),
        atlas_layers=(AtlasLayer("T2", profiles[0].reference_ct, "linear"),))
    monkeypatch.setattr(mw, "load_profiles", lambda: profiles)
    monkeypatch.setattr(mw, "load_reference_library", lambda: library)
    errors = []
    monkeypatch.setattr(QtWidgets.QMessageBox, "critical", lambda *a: errors.append(str(a[-1])))
    settings = QtCore.QSettings(str(tmp_path / "settings.ini"), QtCore.QSettings.Format.IniFormat)
    windows = []

    def open_window():
        window = mw.MainWindow(settings)
        app.processEvents()
        windows.append(window)
        return window

    yield open_window, settings, expected, errors
    for window in windows:
        window.close()
    app.processEvents()


def _checked(window):
    return [action.data() for action in window.guide_actions.actions() if action.isChecked()]


def test_default_guide_is_j0476m(guide_setup):
    open_window, _, expected, errors = guide_setup
    window = open_window()
    assert window.profile.reference_id == "J0476M"
    assert _checked(window) == ["J0476M"]
    assert window.reference_panel.title() == "J0476M Reference CT"
    np.testing.assert_allclose(window.reference_points["LM01"], expected["J0476M"]["LM01"])
    assert not errors


def test_switching_guide_loads_its_ct_and_landmarks_and_is_remembered(guide_setup):
    open_window, settings, expected, errors = guide_setup
    window = open_window()
    selected = window.selected_label
    window.set_guide_reference("HH0312F")
    assert not errors
    assert window.profile.reference_id == "HH0312F"
    assert _checked(window) == ["HH0312F"]
    assert window.reference_panel.title() == "HH0312F Reference CT"
    assert "HH0312F" in window.guide_label.text()
    assert window.reference_volume.source_path.name == "HH0312F_CT.nrrd"
    for label, point in expected["HH0312F"].items():
        np.testing.assert_allclose(window.reference_points[label], point)
    assert window.selected_label == selected
    assert window.layer_combo.count() == 1
    settings.sync()
    assert settings.value(mw.GUIDE_REFERENCE_SETTING) == "HH0312F"
    assert open_window().profile.reference_id == "HH0312F"


def test_switching_guide_keeps_target_landmarks(guide_setup):
    open_window, _, _, _ = guide_setup
    window = open_window()
    window.user_points = {"LM01": np.array([1.0, 2.0, 3.0])}
    window.set_guide_reference("HH0312F")
    np.testing.assert_allclose(window.user_points["LM01"], [1.0, 2.0, 3.0])


def test_unknown_saved_guide_falls_back_to_default(guide_setup):
    open_window, settings, _, _ = guide_setup
    settings.setValue(mw.GUIDE_REFERENCE_SETTING, "NOPE")
    assert open_window().profile.reference_id == "J0476M"


def test_failed_guide_load_keeps_previous_guide(guide_setup):
    open_window, settings, _, errors = guide_setup
    window = open_window()
    broken = replace(window._find_profile("HH0312F"), reference_ct=window.profile.reference_ct.with_name("missing.nrrd"))
    window.profiles = [broken if p.reference_id == "HH0312F" else p for p in window.profiles]
    window.set_guide_reference("HH0312F")
    assert errors
    assert window.profile.reference_id == "J0476M"
    assert _checked(window) == ["J0476M"]
    assert settings.value(mw.GUIDE_REFERENCE_SETTING) is None


def test_reference_views_keep_anatomical_labels():
    assert [orientation for orientation, _, _ in REFERENCE_VIEWS] == ["Axial", "Sagittal", "Coronal"]
    assert all(labels for _, _, labels in REFERENCE_VIEWS)


def test_six_references_share_anatomical_orientation():
    """Anatomical axis labels are only valid if every reference is aligned with J0476M."""
    library = load_reference_library(validate_files=False)
    if library.missing_files():
        pytest.skip("Requires the local reference data library.")
    from marmoset_atlas_mapper.landmarks import load_slicer_markups
    from marmoset_atlas_mapper.registration import register_landmarks

    labels = [f"LM{i:02d}" for i in range(1, 14)]
    guide = next(r for r in library.references if r.reference_id == "J0476M")
    guide_points = load_slicer_markups(guide.landmarks_path)
    for reference in library.references:
        result = register_landmarks(load_slicer_markups(reference.landmarks_path), guide_points, labels, "Rigid")
        rotation = result.matrix_lps[:3, :3]
        angle = np.degrees(np.arccos(np.clip((np.trace(rotation) - 1.0) / 2.0, -1.0, 1.0)))
        assert angle < 20.0, (reference.reference_id, angle)
