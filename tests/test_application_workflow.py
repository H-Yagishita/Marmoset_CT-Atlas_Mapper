"""Qt signal/button tests on disposable scalar volumes and a six-route library."""
import json
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import numpy as np
import pytest
import SimpleITK as sitk
from PySide6 import QtCore, QtWidgets, QtTest
from marmoset_atlas_mapper import main_window as mw
from marmoset_atlas_mapper.landmarks import write_slicer_markups, load_slicer_markups
from marmoset_atlas_mapper.reference_library import load_reference_library, ReferenceEntry, AtlasLayer
from marmoset_atlas_mapper.profile import load_profiles
from marmoset_atlas_mapper.imaging import VolumeData
from marmoset_atlas_mapper.multi_reference_pipeline import run_multi_reference_registration
from marmoset_atlas_mapper.widgets import MultiReferenceQualityCheckDialog, AtlasLayerViewerDialog, OverlaySliceView
from marmoset_atlas_mapper.saved_qc import load_saved_qc_session
from marmoset_atlas_mapper.widgets import ImageCanvas
from marmoset_atlas_mapper.native_io import write_image


@pytest.fixture
def ui(tmp_path, monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    ct = tmp_path / 'CT.nrrd'
    image = sitk.GetImageFromArray(np.arange(1000, dtype=np.float32).reshape(10,10,10))
    sitk.WriteImage(image, str(ct))
    points = {f'LM{i+1:02}': np.array(p, float) for i,p in enumerate([
        (1,1,1),(7,1,1),(1,7,1),(1,1,7),(7,7,1),(7,1,7),(1,7,7),(7,7,7),
        (4,4,1),(4,4,7),(2,4,4),(6,4,4),(4,4,8)])}
    marks=tmp_path/'Landmarks.mrk.json'
    write_slicer_markups(marks,points)
    forward=tmp_path/'Forward.h5'
    sitk.WriteTransform(sitk.AffineTransform(3),str(forward))
    labels=tmp_path/'Labels.nrrd'
    sitk.WriteImage(sitk.Cast(image>100,sitk.sitkUInt16),str(labels))
    ctbl=tmp_path/'labels.ctbl'
    ctbl.write_text('0 Background 0 0 0 0\n1 Brain 255 0 0 255\n')
    template=load_reference_library(validate_files=False)
    refs=tuple(ReferenceEntry(r.reference_id,ct,marks,forward) for r in template.references)
    library=replace(template,references=refs,atlas_reference=ct,atlas_label_map=labels,atlas_color_table=ctbl,
        atlas_layers=(AtlasLayer('T2',ct,'linear'),AtlasLayer('Labels',labels,'nearest')),
        consensus=replace(template.consensus,qc_sample_count=50),
        inverse=replace(template.inverse,minimum_roundtrip_sample_count=10))
    profile=replace(next(p for p in load_profiles() if p.reference_id=='J0476M'),reference_ct=ct,
        reference_landmarks=marks,reference_to_atlas_point_transform=forward,atlas_reference=ct,
        atlas_label_map=labels,atlas_color_table=ctbl,atlas_layers=library.atlas_layers)
    monkeypatch.setattr(mw,'load_profiles',lambda:[profile])
    monkeypatch.setattr(mw,'load_reference_library',lambda:library)
    errors=[]
    monkeypatch.setattr(QtWidgets.QMessageBox,'critical',lambda *a:errors.append(str(a[-1])))
    monkeypatch.setattr(QtWidgets.QMessageBox,'information',lambda *a:None)
    monkeypatch.setattr(QtWidgets.QMessageBox,'question',lambda *a:QtWidgets.QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QtWidgets.QFileDialog,'getOpenFileName',lambda *a:(str(ct),''))
    window=mw.MainWindow()
    app.processEvents()
    window.load_ct_button.click()
    monkeypatch.setattr(QtWidgets.QFileDialog,'getOpenFileName',lambda *a:(str(marks),''))
    window.import_button.click()
    yield SimpleNamespace(w=window,app=app,ct=ct,points=points,marks=marks,library=library,root=tmp_path,errors=errors,patch=monkeypatch)
    window.current_output_directory=None
    window.close()
    app.processEvents()


def test_load_import_save_place_clear_and_types(ui):
    w=ui.w
    assert len(w.user_points)==13 and w.register_button.isEnabled()
    assert w.landmark_table.rowCount()==8
    for kind in ['Landmarks (total)','ANTs registration','Landmarks (skull base)']:
        w.registration_type_combo.setCurrentText(kind)
        assert w.landmark_table.rowCount()==(8 if kind.endswith('(skull base)') else 13)
    for method in ['Similarity','Rigid']: w.method_combo.setCurrentText(method)
    w._select_landmark('LM02')
    w._clear_selected()
    assert 'LM02' not in w.user_points
    w.user_panel.views['Axial'].canvas.clicked.emit(3.,4.)
    np.testing.assert_allclose(w.user_points['LM02'],[3,4,w.user_panel.index_xyz[2]])
    w.landmark_visibility_button.click()
    assert all(not v.points_visible for v in w.user_panel.views.values())
    saved=ui.root/'Export.mrk.json'
    ui.patch.setattr(QtWidgets.QFileDialog,'getSaveFileName',lambda *a:(str(saved),''))
    w.save_markups_button.click()
    assert len(load_slicer_markups(saved))==13
    w._clear_all()
    assert not w.user_points and not w.register_button.isEnabled()
    assert not ui.errors


def test_loading_second_ct_clears_landmark_overlays(ui):
    ui.patch.setattr(QtWidgets.QFileDialog,'getOpenFileName',lambda *a:(str(ui.ct),''))
    ui.w.load_ct_button.click()
    assert not ui.w.user_points
    assert not ui.w.user_panel.points_lps
    assert all(not v.points_lps for v in ui.w.user_panel.views.values())


def test_invalid_import_and_cancel_preserve_workspace(ui):
    invalid=ui.root/'wrong.mrk.json'
    write_slicer_markups(invalid,{'P1':(1,2,3)})
    ui.patch.setattr(QtWidgets.QFileDialog,'getOpenFileName',lambda *a:(str(invalid),''))
    ui.w.import_button.click()
    assert len(ui.w.user_points)==13 and len(ui.errors)==1
    ui.patch.setattr(QtWidgets.QFileDialog,'getOpenFileName',lambda *a:('',''))
    ui.w.load_ct_button.click()
    ui.w.import_button.click()
    ui.patch.setattr(QtWidgets.QFileDialog,'getExistingDirectory',lambda *a:'')
    ui.w.open_saved_qc_button.click()
    ui.w.register_button.click()
    assert len(ui.w.user_points)==13


def test_vector_and_4d_inputs_rejected():
    for image in [sitk.Image([3,3,3,2],sitk.sitkFloat32),sitk.Image([3,3,3],sitk.sitkVectorFloat32,3)]:
        with pytest.raises(ValueError): VolumeData.from_image(image)


@pytest.mark.parametrize('method',['Rigid','Similarity'])
@pytest.mark.parametrize('kind',['Landmarks (skull base)','Landmarks (total)'])
def test_run_all_landmark_modes_restore_and_view(ui,method,kind):
    w=ui.w
    w.registration_type_combo.setCurrentText(kind)
    w.method_combo.setCurrentText(method)
    output=ui.root/'result'
    output.mkdir()
    ui.patch.setattr(QtWidgets.QFileDialog,'getExistingDirectory',lambda *a:str(output))
    ui.patch.setattr(MultiReferenceQualityCheckDialog,'exec',lambda self:0)
    w.register_button.click()
    assert not ui.errors
    assert w.qc_session is not None
    assert len(w.multi_result.routes)==6
    assert len(w.multi_result.landmark_subset.labels)==(8 if kind.endswith('(skull base)') else 13)
    w._select_landmark('LM04')
    w.user_panel.views['Axial'].slider.setValue(7)
    w.landmark_visibility_button.click()
    w.layer_combo.setCurrentText('Labels')
    w.user_panel.window_level_control.window_spin.setValue(123)
    w._write_workspace_state()
    manifest=json.loads((output/'Run_Manifest.json').read_text())
    assert len(manifest['TargetLandmarks'])==13
    assert manifest['Workspace']['SelectedLandmark']=='LM04'
    w._invalidate_registration()
    w.open_saved_qc_button.click()
    assert not ui.errors
    assert w.current_output_directory==output
    assert len(w.user_points)==13
    assert w.selected_label=='LM04' and w.landmark_table.currentRow()==3
    assert w.user_panel.index_xyz[2]==7 and w.user_volume.window==123
    assert not w.landmark_visibility_button.isChecked()
    assert w.layer_combo.currentText()=='Labels'
    assert w.multi_result is None and w._get_user_to_atlas() is not None
    w.qc_button.click()
    visited=[]
    def visit(dialog):
        for name in dialog.layers:
            dialog.layer_combo.setCurrentText(name)
            for view in dialog.views.values():
                view.slider.setValue(2)
                assert view.canvas._image is not None
            visited.append(name)
        return 0
    ui.patch.setattr(AtlasLayerViewerDialog,'exec',visit)
    w.atlas_viewer_button.click()
    assert visited==['T2','Labels'] and not ui.errors


def test_busy_guard_failure_retry_and_nonempty_output(ui):
    w=ui.w
    output=ui.root/'existing'
    output.mkdir()
    (output/'keep.txt').write_text('keep')
    ui.patch.setattr(QtWidgets.QFileDialog,'getExistingDirectory',lambda *a:str(output))
    observed=[]
    def fail(**kw):
        observed.append(kw['output_directory'])
        assert not w.load_ct_button.isEnabled() and not w.register_button.isEnabled()
        w._run_registration()  # reentrant event must not start another calculation
        event=__import__('PySide6.QtGui',fromlist=['QCloseEvent']).QCloseEvent()
        w.closeEvent(event)
        assert not event.isAccepted()
        raise RuntimeError('injected computation failure')
    ui.patch.setattr(mw,'run_multi_reference_registration',fail)
    w.register_button.click()
    assert len(observed)==1 and Path(observed[0]).parent==output
    assert (output/'keep.txt').read_text()=='keep'
    assert w.load_ct_button.isEnabled() and w.register_button.isEnabled()
    assert w.qc_session is None and not w.qc_button.isEnabled()
    assert not w._busy and len(ui.errors)==1


def test_pipeline_will_not_overwrite_existing_results(ui):
    output=ui.root/'existing'
    output.mkdir()
    (output/'old.h5').write_text('preserve')
    with pytest.raises(FileExistsError):
        run_multi_reference_registration(target_ct_path=ui.ct,target_landmarks=ui.points,
            requested_labels=mw.SKULL_BASE_LABELS,method='Rigid',library=ui.library,output_directory=output)
    assert (output/'old.h5').read_text()=='preserve'


def make_result(ui, name='result', labels=mw.SKULL_BASE_LABELS, **kwargs):
    output=ui.root/name
    run_multi_reference_registration(target_ct_path=ui.ct,target_landmarks=ui.points,
        requested_labels=labels,method='Rigid',library=kwargs.get('library',ui.library),output_directory=output)
    return output


@pytest.mark.parametrize('key, display', [('MRI', 'MR image'), ('Atlas MRI', 'Atlas MR image')])
def test_saved_mr_layer_identifiers_survive_display_rename(ui, key, display):
    w = ui.w
    # Put the MR layer second so restoration cannot pass by selecting the default.
    library = replace(ui.library, atlas_layers=(
        ui.library.atlas_layers[1], AtlasLayer(key, ui.ct, 'linear')))
    w.reference_library = library
    w._load_profile()
    assert w.layer_combo.itemText(1) == display
    assert w.layer_combo.itemData(1).name == key
    output = make_result(ui, library=library)
    manifest_path = output / 'Run_Manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest['Workspace'] = {'AtlasLayer': key}
    manifest_path.write_text(json.dumps(manifest))
    existing_outputs = manifest['AutomaticOutputs']
    existing_qc = manifest['QCViewer']
    existing_files = sorted(str(path.relative_to(output)) for path in output.rglob('*') if path.is_file())
    ui.patch.setattr(QtWidgets.QFileDialog, 'getExistingDirectory', lambda *a: str(output))
    seen = []

    def inspect_qc(dialog):
        assert dialog.tabs.tabText(0) == 'Atlas MR image'
        assert dialog.overlays[0][0] == 'Atlas MRI'
        assert dialog.contrast.red_label.text() == 'Magenta · Atlas MR image'
        seen.append('qc')
        return 0

    def inspect_atlas(dialog):
        assert dialog.layer_combo.currentData() == key
        assert dialog.layer_combo.currentText() == display
        assert dialog.contrast.red_label.text() == f'Magenta · {display}'
        assert key in dialog.layers
        seen.append('atlas')
        return 0

    ui.patch.setattr(MultiReferenceQualityCheckDialog, 'exec', inspect_qc)
    ui.patch.setattr(AtlasLayerViewerDialog, 'exec', inspect_atlas)
    w.open_saved_qc_button.click()
    assert w.layer_combo.currentData().name == key
    assert w.layer_combo.currentText() == display
    w.qc_button.click()
    w.atlas_viewer_button.click()
    assert seen == ['qc', 'atlas'] and not ui.errors
    w._write_workspace_state()
    restored = json.loads(manifest_path.read_text())
    assert restored['Workspace']['AtlasLayer'] == key
    assert restored['AutomaticOutputs'] == existing_outputs
    assert restored['QCViewer'] == existing_qc
    assert sorted(str(path.relative_to(output)) for path in output.rglob('*') if path.is_file()) == existing_files


def test_open_second_result_is_atomic_and_does_not_modify_first(ui):
    a=make_result(ui,'A')
    b=make_result(ui,'B')
    w=ui.w
    for directory in (a,b):
        ui.patch.setattr(QtWidgets.QFileDialog,'getExistingDirectory',lambda *args,d=directory:str(d))
        w.open_saved_qc_button.click()
        assert not ui.errors
        assert w.current_output_directory==directory
        if directory==a:
            w._select_landmark('LM03')
            w._write_workspace_state()
            original=(a/'Run_Manifest.json').read_bytes()
    assert (a/'Run_Manifest.json').read_bytes()==original
    # Corrupt B's view settings. Opening it must keep the currently valid state.
    data=json.loads((b/'Run_Manifest.json').read_text())
    data['Workspace']={'TargetViewIndexXYZ':[0,float('nan'),1]}
    (b/'Run_Manifest.json').write_text(json.dumps(data))
    volume=w.user_volume
    w.open_saved_qc_button.click()
    assert len(ui.errors)==1 and w.user_volume is volume


def test_readonly_workspace_settings_do_not_crash_viewer(ui):
    directory=make_result(ui)
    ui.patch.setattr(QtWidgets.QFileDialog,'getExistingDirectory',lambda *a:str(directory))
    ui.w.open_saved_qc_button.click()
    def fail(*a,**kw): raise PermissionError('read only test')
    ui.patch.setattr(mw,'write_json',fail)
    ui.w.user_panel.window_level_control.window_spin.setValue(15)
    assert not ui.errors
    assert 'Could not save viewer settings' in ui.w.log_output.toPlainText()


def test_missing_forward_does_not_replace_loaded_workspace(ui):
    directory=make_result(ui)
    forward=next(directory.glob('*_Forward.h5'))
    forward.rename(forward.with_suffix('.unavailable'))
    ui.patch.setattr(QtWidgets.QFileDialog,'getExistingDirectory',lambda *a:str(directory))
    volume=ui.w.user_volume
    ui.w.open_saved_qc_button.click()
    assert len(ui.errors)==1 and ui.w.user_volume is volume
    assert ui.w.current_output_directory is None


@pytest.mark.parametrize('suffix',['.nii','.nii.gz','.nrrd','.nhdr'])
def test_image_formats_oblique_spacing_and_physical_coordinates(ui,suffix):
    image=sitk.ReadImage(str(ui.ct))
    angle=.23
    image.SetDirection((np.cos(angle),-np.sin(angle),0,np.sin(angle),np.cos(angle),0,0,0,1))
    image.SetOrigin((12,-100,53))
    image.SetSpacing((.1,.3,.8))
    path=ui.root/('日本語 CT'+suffix)
    write_image(image,path)
    volume=VolumeData.read(path)
    index=(2.,4.,6.)
    np.testing.assert_allclose(volume.physical_to_index(volume.index_to_physical(index)),index,atol=1e-5)
    np.testing.assert_allclose(volume.image.GetSpacing(),image.GetSpacing(),atol=1e-5)


def test_actual_mouse_click_uses_voxel_center(ui):
    canvas=ImageCanvas()
    canvas.resize(200,200)
    canvas.set_array(np.zeros((10,10),np.uint8))
    canvas.show()
    ui.app.processEvents()
    points=[]
    canvas.clicked.connect(lambda x,y:points.append((x,y)))
    QtTest.QTest.mouseClick(canvas,QtCore.Qt.MouseButton.LeftButton,pos=QtCore.QPoint(10,10))
    np.testing.assert_allclose(points[0],[0,0])
    assert canvas._to_widget(0,0)==QtCore.QPointF(10,10)
    canvas.close()


def test_qc_tabs_preserve_independent_slice_positions(ui):
    directory=make_result(ui)
    session=load_saved_qc_session(directory)
    dialog=MultiReferenceQualityCheckDialog(ui.w,session.target,session.atlas_in_target,
        session.warped_references,session.result,session.center_lps)
    a,b=dialog.overlay_sets[:2]
    a['Axial'].slider.setValue(8)
    b['Coronal'].slider.setValue(2)
    assert a['Axial'].index_xyz[2]==8
    assert b['Axial'].index_xyz[2]!=8
    for views in dialog.overlay_sets:
        for view in views.values(): assert view.canvas._image is not None
    dialog.close()


@pytest.mark.parametrize('count',[3,5])
def test_partial_landmarks_run_and_restore(ui,count):
    directory=make_result(ui,labels=tuple(ui.points)[:count])
    session=load_saved_qc_session(directory)
    assert len(session.result.landmark_subset.labels)==count
    assert len(session.result.routes)==6


def test_inverse_fail_keeps_forward_and_viewer_without_inverse_outputs(ui):
    library=replace(ui.library,inverse=replace(ui.library.inverse,minimum_roundtrip_sample_count=999))
    directory=make_result(ui,library=library)
    manifest=json.loads((directory/'Run_Manifest.json').read_text())
    assert not manifest['InverseGenerated']
    assert not list((directory/'Inverse').glob('*.h5'))
    assert not (directory/'TargetCT_in_BMA2.0.nii.gz').exists()
    session=load_saved_qc_session(directory)
    assert session.result.inverse is None and session.result.qc.passed


def test_log_can_be_reopened(ui):
    ui.w.log_dock.hide()
    ui.w.log_dock.toggleViewAction().trigger()
    assert not ui.w.log_dock.isHidden()


@pytest.mark.parametrize('legacy, expected, rows', [
    ('Landmark (Skull-base)', 'Landmarks (skull base)', 8),
    ('Landmark (Skull-all)', 'Landmarks (total)', 13),
])
def test_legacy_mode_restored_by_name_even_with_eight_points(ui, legacy, expected, rows):
    directory = make_result(ui)
    path = directory / 'Run_Manifest.json'
    manifest = json.loads(path.read_text())
    manifest['RegistrationType'] = legacy
    path.write_text(json.dumps(manifest))
    session = load_saved_qc_session(directory)
    assert session.result.registration_type == expected
    ui.patch.setattr(QtWidgets.QFileDialog, 'getExistingDirectory', lambda *a: str(directory))
    ui.w.open_saved_qc_button.click()
    assert not ui.errors
    assert ui.w.registration_type_combo.currentText() == expected
    assert ui.w.landmark_table.rowCount() == rows


def test_unicode_output_bundle_roundtrip(ui):
    directory=make_result(ui,name='日本語の結果')
    session=load_saved_qc_session(directory)
    assert session.result.qc.passed
    ui.patch.setattr(QtWidgets.QFileDialog,'getExistingDirectory',lambda *a:str(directory))
    ui.w.open_saved_qc_button.click()
    assert not ui.errors and ui.w.user_to_atlas is not None
