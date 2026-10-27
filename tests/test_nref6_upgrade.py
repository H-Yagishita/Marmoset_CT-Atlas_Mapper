import json
import os
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest
import SimpleITK as sitk
from PySide6.QtWidgets import QApplication

from marmoset_atlas_mapper.imaging import VolumeData
from marmoset_atlas_mapper.widgets import VolumePanel
from marmoset_atlas_mapper.reference_library import load_reference_library, ReferenceEntry, AtlasLayer
from marmoset_atlas_mapper.multi_reference_pipeline import run_multi_reference_registration, registration_output_stem
from marmoset_atlas_mapper.landmarks import write_slicer_markups
from marmoset_atlas_mapper.saved_qc import load_saved_qc_session


def test_window_level_is_display_only():
    image = sitk.GetImageFromArray(np.linspace(-1, 1, 125).reshape(5, 5, 5))
    image.SetSpacing((0.1, 0.2, 0.3))
    volume = VolumeData.from_image(image)
    old_array = volume.array_zyx.copy()
    old_range = (volume.window, volume.level)
    volume.set_window_level(0.25, -0.3)
    assert volume.window == pytest.approx(.25)
    assert volume.level == pytest.approx(-.3)
    np.testing.assert_array_equal(volume.array_zyx, old_array)
    np.testing.assert_array_equal(sitk.GetArrayFromImage(volume.image), old_array)
    assert volume.image.GetSpacing() == (0.1, 0.2, 0.3)
    volume.reset_window_level()
    assert (volume.window, volume.level) == old_range
    for window, level in [(0, 0), (-1, 0), (np.nan, 0), (1, np.inf)]:
        with pytest.raises(ValueError):
            volume.set_window_level(window, level)


def test_window_level_widget_refreshes_without_moving_landmarks():
    app = QApplication.instance() or QApplication([])
    panel = VolumePanel("Target CT", interactive=True, window_level_controls=True)
    control = panel.window_level_control
    assert not control.isEnabled()
    changes = []
    control.changed.connect(lambda: changes.append(True))
    volume = VolumeData.from_image(sitk.GetImageFromArray(np.arange(125.).reshape(5, 5, 5)))
    panel.set_volume(volume)
    panel.set_points({"LM01": (1, 2, 3)}, "LM01")
    before = panel.index_xyz.copy()
    assert changes == []
    control.window_spin.setValue(40)
    control.level_spin.setValue(-10)
    app.processEvents()
    assert volume.window == pytest.approx(40, abs=1e-10)
    assert volume.level == pytest.approx(-10, abs=1e-10)
    assert len(changes) == 2
    assert all(view.volume is volume for view in panel.views.values())
    np.testing.assert_array_equal(panel.index_xyz, before)
    np.testing.assert_array_equal(panel.points_lps["LM01"], [1, 2, 3])
    control.reset_button.click()
    assert volume.window_min == volume.default_window_min
    panel.close()


def test_output_names_distinguish_six_reference_consensus_backends():
    assert registration_output_stem(6, "Landmark (Skull-base)") == "Target_CT_to_BMA_MultiRef_Nref6"
    assert registration_output_stem(4, "Landmark (Skull-all)") == "Target_CT_to_BMA_MultiRef_Nref4"
    assert registration_output_stem(6, "ANTs registration") == "Target_CT_to_BMA_ANTs_MultiRef_Nref6"


def test_library_rejects_missing_reference(tmp_path):
    library = load_reference_library(validate_files=False)
    payload = json.loads(library.manifest_path.read_text())
    payload["references"].pop()
    path = tmp_path / "library.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="Nref=6"):
        load_reference_library(path, validate_files=False)


@pytest.mark.parametrize("reference_count,method", [(4, "Rigid"), (6, "Rigid"), (6, "Similarity")])
def test_consensus_output_and_saved_results_roundtrip(tmp_path, reference_count, method):
    template = load_reference_library(validate_files=False)
    ct = tmp_path / "CT.nrrd"
    image = sitk.GetImageFromArray(np.arange(512, dtype=np.float32).reshape(8, 8, 8))
    sitk.WriteImage(image, str(ct))
    label = tmp_path / "Labels.nrrd"
    sitk.WriteImage(sitk.Cast(image > 0, sitk.sitkUInt16), str(label))
    ctbl = tmp_path / "labels.ctbl"
    ctbl.write_text("0 Background 0 0 0 0\n1 Brain 255 0 0 255\n")
    points = {f"LM{i+1:02d}": np.asarray(p, dtype=float) for i, p in enumerate([
        (1,1,1), (5,1,1), (1,5,1), (1,1,5), (5,5,1), (5,1,5), (1,5,5), (5,5,5)
    ])}
    markups = tmp_path / "Landmarks.mrk.json"
    write_slicer_markups(markups, points)
    forward = tmp_path / "Forward.h5"
    sitk.WriteTransform(sitk.AffineTransform(3), str(forward))
    references = tuple(ReferenceEntry(f"Ref{i}", ct, markups, forward) for i in range(reference_count))
    library = replace(template, atlas_reference=ct, atlas_label_map=label, atlas_color_table=ctbl,
        atlas_layers=(AtlasLayer("T2", ct, "linear"), AtlasLayer("Regions", label, "nearest")),
        references=references, consensus=replace(template.consensus, qc_sample_count=50),
        inverse=replace(template.inverse, minimum_roundtrip_sample_count=10))
    output = tmp_path / "result"
    result = run_multi_reference_registration(target_ct_path=ct, target_landmarks=points,
        requested_labels=tuple(points), method=method, library=library, output_directory=output)
    assert result.qc.passed and result.inverse_qc.passed
    np.testing.assert_allclose(result.consensus_transform.TransformPoint((2,3,4)), (2,3,4), atol=1e-9)
    manifest = json.loads((output / "Run_Manifest.json").read_text())
    assert manifest["Nref"] == reference_count
    assert manifest["ReferenceCount"] == reference_count
    assert (output / f"Target_CT_to_BMA_MultiRef_Nref{reference_count}_Forward.h5").is_file()
    assert len(list((output / "SingleReference").glob("*.h5"))) == reference_count
    assert len(list((output / "TargetCT_in_Reference").glob("*.nrrd"))) == reference_count
    session = load_saved_qc_session(output)
    assert len(session.result.routes) == reference_count
    assert all(len(route.registration.residual_distances) == 8 for route in session.result.routes)
    # Hiding FRE in the viewer must not remove or alter the saved diagnostics.
    import csv
    with (output / "QC" / "Landmark_FRE.csv").open(encoding="utf-8-sig", newline="") as handle:
        summaries = list(csv.DictReader(handle))
    with (output / "QC" / "Landmark_Residuals.csv").open(encoding="utf-8-sig", newline="") as handle:
        residuals = list(csv.DictReader(handle))
    assert len(summaries) == reference_count
    assert len(residuals) == 8 * reference_count
    for route in result.routes:
        row = next(row for row in summaries if row["ReferenceID"] == route.reference.reference_id)
        assert float(row["FRE_RMS_mm"]) == pytest.approx(route.registration.rms_mm)
