from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

def smoke_test() -> int:
    import SimpleITK as sitk

    from marmoset_atlas_mapper.imaging import VolumeData
    from marmoset_atlas_mapper.landmarks import load_slicer_markups
    from marmoset_atlas_mapper.profile import load_profiles
    from marmoset_atlas_mapper.reference_library import load_reference_library
    from marmoset_atlas_mapper.transform_io import read_transform

    profiles = load_profiles()
    library = load_reference_library()
    if not profiles:
        raise RuntimeError("No atlas profiles found.")
    for profile in profiles:
        missing = profile.missing_files()
        if missing:
            raise FileNotFoundError("Missing profile files: " + ", ".join(map(str, missing)))
        VolumeData.read(profile.reference_ct)
        points = load_slicer_markups(profile.reference_landmarks)
        if any(label not in points for label in profile.registration_labels):
            raise RuntimeError(f"{profile.reference_id} registration landmarks are incomplete.")
        forward = read_transform(profile.reference_to_atlas_point_transform)
        del forward
    if len(library.references) != 6:
        raise RuntimeError("Nref=6 reference library must contain exactly six references.")
    if library.missing_files():
        raise FileNotFoundError("Nref=6 reference library is incomplete.")
    return 0


def gui_smoke_test(report_path: str) -> int:
    """Exercise the frozen GUI and native Qt plugins, not just the image core."""
    import json
    import traceback

    report = Path(report_path).resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    details = {"status": "Started", "executable": sys.executable}
    report.write_text(json.dumps(details, indent=2), encoding="utf-8")
    try:
        from PySide6 import QtCore, QtWidgets
        from marmoset_atlas_mapper import __version__
        from marmoset_atlas_mapper.main_window import MainWindow
        from marmoset_atlas_mapper.widgets import MultiReferenceQualityCheckDialog, AtlasLayerViewerDialog
        from types import SimpleNamespace

        application = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        application.setStyle("Fusion")
        window = MainWindow()
        window.setAttribute(QtCore.Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        window.show()
        application.processEvents()
        assert window.reference_volume is not None, "Reference CT did not load"
        assert window.landmark_table.columnCount() == 2
        assert len(window.reference_library.references) == 6
        assert len(window.reference_points) >= 13
        modes = [window.registration_type_combo.itemText(i) for i in range(window.registration_type_combo.count())]
        assert modes == ["Landmarks (skull base)", "Landmarks (total)", "ANTs registration"], modes
        window.registration_type_combo.setCurrentText("ANTs registration")
        assert len(window.registration_labels) == 13
        details["registration_modes"] = modes
        citation_group = next(group for group in window.findChildren(QtWidgets.QGroupBox)
                              if group.title() == "Atlas license and citation")
        citation_labels = citation_group.findChildren(QtWidgets.QLabel)
        citation_text = "\n".join(label.text() for label in citation_labels)
        assert "Atlas license: CC BY 4.0" in citation_text
        assert "https://doi.org/10.6084/m9.figshare.29992687" in citation_text
        assert f"Marmoset Atlas Mapper v{__version__}" in citation_text
        assert "forthcoming" not in citation_text.lower()
        assert "Software/paper citation" not in citation_text
        assert all(label.openExternalLinks() for label in citation_labels)
        details["citation_panel_checked"] = True
        details["citation_panel_html"] = citation_text
        # Also exercise normalized CT contrast and all three slice renderers.
        window.user_volume = window.reference_volume
        window.user_panel.set_volume(window.user_volume)
        target_panel_order = list(window.user_panel.views)
        assert target_panel_order == ["Axial", "Sagittal", "Coronal"]
        assert all(view.title.text() == "" for view in window.user_panel.views.values())
        window.user_panel.window_level_control.window_spin.setValue(0.6)
        window.user_panel.window_level_control.level_spin.setValue(0.35)
        application.processEvents()
        assert abs(window.user_volume.window - 0.6) < 1e-9
        contrast = window.user_panel.window_level_control
        contrast.window_slider.setValue(contrast.SLIDER_STEPS // 3)
        assert window.user_volume.window > 0 and window.user_volume.window != 0.6
        contrast.level_slider.setValue(contrast.SLIDER_STEPS // 4)
        assert window.user_volume.level != 0.35
        contrast.reset_button.click()
        assert window.user_volume.window_min == window.user_volume.default_window_min
        application.processEvents()
        assert window.grab().save(str(report.with_suffix(".png")))
        # Contrast changes are isolated from the source image and from the
        # other channel, including when both channels share the same voxels.
        volume = window.reference_volume
        original_range = (volume.window_min, volume.window_max)
        center = volume.index_to_physical(tuple(size // 2 for size in volume.display_image.GetSize()))
        qc_result = SimpleNamespace(method="Rigid", routes=[None] * 6,
            landmark_subset=SimpleNamespace(labels=tuple(range(8))),
            qc=SimpleNamespace(passed=True), inverse_qc=SimpleNamespace(passed=True), inverse=object())
        qc = MultiReferenceQualityCheckDialog(window, volume, volume,
            {entry.reference_id: volume for entry in window.reference_library.references}, qc_result, center)
        viewer = AtlasLayerViewerDialog(window, volume, {"MRI": volume, "Nissl": volume}, center)
        for dialog, select, views in (
            (qc, qc.tabs.setCurrentIndex, lambda: qc.overlay_sets[qc.tabs.currentIndex()]),
            (viewer, viewer.layer_combo.setCurrentIndex, lambda: viewer.views),
        ):
            dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DontShowOnScreen, True)
            dialog.show()
            application.processEvents()
            c = dialog.contrast
            c.green_control.level_spin.setValue(volume.level + volume.window * 0.1)
            green_level = c.green_control.volume.level
            c.red_control.window_slider.setValue(2500)
            red_window = c.red_control.volume.window
            select(1)
            c.red_control.level_slider.setValue(6000)
            select(0)
            assert abs(c.red_control.volume.window - red_window) < 1e-9
            assert c.green_control.volume.level == green_level
            c.red_control.reset_button.click()
            assert c.green_control.volume.level == green_level
            c.green_control.reset_button.click()
            assert all(not view.canvas._image.isNull() for view in views().values())
            assert (volume.window_min, volume.window_max) == original_range
            assert not dialog.findChildren(QtWidgets.QTableWidget)
            application.processEvents()
            suffix = "_qc.png" if dialog is qc else "_atlas.png"
            assert dialog.grab().save(str(report.with_name(report.stem + suffix)))
            dialog.close()
        details["overlay_contrast_checked"] = True
        details["fre_hidden_in_ui"] = True
        details.update(status="Passed", version=__version__, qt_version=QtCore.qVersion(),
                       qt_platform=application.platformName(), reference_count=6,
                       reference_image_rendered=True, window_level_checked=True)
        details["target_panel_order"] = target_panel_order
        details["window_level_sliders_checked"] = True
        window.close()
    except Exception:
        details.update(status="Failed", traceback=traceback.format_exc())
    report.write_text(json.dumps(details, indent=2), encoding="utf-8")
    return 0 if details["status"] == "Passed" else 1


if __name__ == "__main__":
    if "--io-smoke-test" in sys.argv:
        from marmoset_atlas_mapper.io_audit import audit
        raise SystemExit(audit(sys.argv[sys.argv.index("--io-smoke-test") + 1]))
    if "--workflow-audit" in sys.argv:
        from marmoset_atlas_mapper.application_audit import workflow_audit
        index = sys.argv.index("--workflow-audit")
        raise SystemExit(workflow_audit(sys.argv[index + 1], sys.argv[index + 2]))
    if "--gui-smoke-test" in sys.argv:
        index = sys.argv.index("--gui-smoke-test")
        raise SystemExit(gui_smoke_test(sys.argv[index + 1]))
    if "--ants-smoke-test" in sys.argv:
        from marmoset_atlas_mapper.ants_audit import audit
        raise SystemExit(audit(sys.argv[sys.argv.index("--ants-smoke-test") + 1]))
    if "--smoke-test" in sys.argv:
        raise SystemExit(smoke_test())
    from marmoset_atlas_mapper.main_window import run

    raise SystemExit(run())
