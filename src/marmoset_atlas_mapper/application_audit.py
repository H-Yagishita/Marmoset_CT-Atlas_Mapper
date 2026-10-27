"""Opt-in native-Qt packaged workflow check on a disposable saved result only."""
from pathlib import Path
import json
import traceback
from unittest.mock import patch
import numpy as np
import SimpleITK as sitk
from PySide6 import QtCore, QtWidgets
from . import __version__
from .main_window import MainWindow
from .widgets import MultiReferenceQualityCheckDialog, AtlasLayerViewerDialog
from .data_manager_dialog import ReferenceDataDialog
from .landmarks import load_slicer_markups
from .ants_audit import audit as ants_audit


def workflow_audit(result_directory, report_path):
    root=Path(result_directory).resolve()
    report=Path(report_path).resolve()
    report.parent.mkdir(parents=True,exist_ok=True)
    # This opt-in command modifies view settings. Require a clearly designated
    # audit fixture instead of accepting an arbitrary user's result directory.
    if 'debug_audit_20261006' not in root.parts:
        raise ValueError('Use a disposable debug_audit_20261006 result fixture.')
    details={'status':'Started','version':__version__,'checks':[]}
    report.write_text(json.dumps(details),encoding='utf-8')
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setStyle('Fusion')
    errors=[]
    window=None
    try:
        with patch.object(QtWidgets.QMessageBox,'critical',side_effect=lambda *a:errors.append(str(a[-1]))):
            window=MainWindow()
            window.setAttribute(QtCore.Qt.WidgetAttribute.WA_DontShowOnScreen,True)
            window.show()
            app.processEvents()
            assert window.reference_volume is not None
            details['checks'].append('native Qt startup + J0476M + six references')
            with patch.object(QtWidgets.QFileDialog,'getExistingDirectory',return_value=str(root)):
                window.open_saved_qc_button.click()
            assert not errors and window.qc_session is not None
            assert len(window.user_points)==13
            details['checks'].append('Open results + all 13 landmarks + FRE table + forward H5')
            window.grab().save(str(report.with_name(report.stem+'_main.png')))
            counts=[]
            def inspect_qc(dialog):
                dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DontShowOnScreen,True)
                dialog.show()
                app.processEvents()
                for views in dialog.overlay_sets:
                    for view in views.values():
                        value=min(view.slider.maximum(),view.slider.value()+1)
                        view.slider.setValue(value)
                        assert not view.canvas._image.isNull()
                counts.append(len(dialog.overlay_sets))
                dialog.grab().save(str(report.with_name(report.stem+'_qc.png')))
                dialog.close()
                return 0
            with patch.object(MultiReferenceQualityCheckDialog,'exec',inspect_qc):
                window.qc_button.click()
            assert counts==[7]
            details['checks'].append('QC all seven tabs, three linked slices per tab')
            layers=[]
            def inspect_viewer(dialog):
                dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DontShowOnScreen,True)
                dialog.show()
                for name in dialog.layers:
                    dialog.layer_combo.setCurrentText(name)
                    app.processEvents()
                    for view in dialog.views.values():
                        view.slider.setValue(max(view.slider.minimum(),view.slider.value()-1))
                        assert not view.canvas._image.isNull()
                    layers.append(name)
                dialog.grab().save(str(report.with_name(report.stem+'_atlas.png')))
                dialog.close()
                return 0
            with patch.object(AtlasLayerViewerDialog,'exec',inspect_viewer):
                window.atlas_viewer_button.click()
            assert len(layers)==len(window.reference_library.atlas_layers)
            details['checks'].append('Atlas viewer every MRI/label/Nissl/Myelin layer')
            details['atlas_layers']=layers
            window._select_landmark('LM05')
            window.landmark_visibility_button.setChecked(False)
            control=window.user_panel.window_level_control
            old=(window.user_volume.window,window.user_volume.level)
            control.window_spin.setValue(old[0]*.8)
            control.level_spin.setValue(old[1]+old[0]*.05)
            assert window.user_volume.window!=old[0]
            control.reset_button.click()
            window._write_workspace_state()
            with patch.object(QtWidgets.QFileDialog,'getExistingDirectory',return_value=str(root)):
                window.open_saved_qc_button.click()
            assert window.selected_label=='LM05' and not window.landmark_visibility_button.isChecked()
            details['checks'].append('Window/Level, Auto/Reset, landmark visibility, workspace round trip')
            export=report.with_name('audit_landmarks.mrk.json')
            with patch.object(QtWidgets.QFileDialog,'getSaveFileName',return_value=(str(export),'')):
                window.save_markups_button.click()
            assert len(load_slicer_markups(export))==13
            with patch.object(QtWidgets.QFileDialog,'getOpenFileName',return_value=(str(export),'')):
                window.import_button.click()
            details['checks'].append('Save and reimport landmarks')
            for kind in ['Landmark (Skull-all)','ANTs registration','Landmark (Skull-base)']:
                window.registration_type_combo.setCurrentText(kind)
                for method in ['Similarity','Rigid']: window.method_combo.setCurrentText(method)
            details['checks'].append('registration type/method controls and result invalidation')
            with patch.object(QtWidgets.QFileDialog,'getOpenFileName',return_value=(str(root/'QC/Volumes/TargetCT.nii.gz'),'')):
                # Resolve actual saved image filename, rather than assuming its extension.
                manifest=json.loads((root/'Run_Manifest.json').read_text())
                with patch.object(QtWidgets.QFileDialog,'getOpenFileName',return_value=(str(root/manifest['QCViewer']['TargetCT']),'')):
                    window.load_ct_button.click()
            assert not window.user_points and not window.user_panel.points_lps
            details['checks'].append('Load another CT clears all old overlays')
            dialog=ReferenceDataDialog(window,require_complete=False)
            assert dialog.data_ready
            for button in dialog.findChildren(QtWidgets.QPushButton):
                if button.text()=='Check again': button.click()
            assert dialog.data_ready
            dialog.close()
            details['checks'].append('Reference Data status + Check again')
            backend_report = report.with_name(report.stem + "_ants.json")
            assert ants_audit(backend_report) == 0, backend_report
            details["checks"].append("standalone ANTs Rigid + Similarity audit")
            assert not errors, errors
            details.update(status='Passed',qt_platform=app.platformName(),qt_version=QtCore.qVersion())
    except Exception:
        details.update(status='Failed',traceback=traceback.format_exc(),dialog_errors=errors)
    finally:
        if window is not None:
            window.close()
        report.write_text(json.dumps(details,indent=2,ensure_ascii=False),encoding='utf-8')
    return 0 if details['status']=='Passed' else 1
