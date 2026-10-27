import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import SimpleITK as sitk

from marmoset_atlas_mapper import ants_registration as ar
from marmoset_atlas_mapper.imaging import matrix_to_sitk_affine
from marmoset_atlas_mapper.registration import RegistrationResult, apply_matrix
from marmoset_atlas_mapper.reference_library import load_reference_library, ReferenceEntry, AtlasLayer
from marmoset_atlas_mapper.landmarks import write_slicer_markups
from marmoset_atlas_mapper.multi_reference_pipeline import run_multi_reference_registration
from marmoset_atlas_mapper.saved_qc import load_saved_qc_session


def test_command_has_isotropic_stages_no_mask_and_one_initial():
    runtime = ar.ANTsRuntime(Path("antsRegistration.exe"))
    p = ar.load_parameters()
    for method, stages in ar.STAGES.items():
        command = ar.build_command(runtime, "fixed", "moving", "initial", "out", method, p)
        assert command[0] == "antsRegistration.exe"
        assert "--launch" not in command and "Slicer.exe" not in command
        assert [command[i+1] for i,v in enumerate(command) if v == "--transform"] == [
            f"{stage}[0.1]" for stage in stages]
        assert command.count("--initial-moving-transform") == 1
        assert command[command.index("--initial-moving-transform")+1] == "initial"
        assert "--masks" not in command
        assert "ScaleVersor3D" not in str(command)
    p["gradient_step"] = float("nan")
    with pytest.raises(ValueError):
        ar.validate_parameters(p)


def write_runtime(root):
    exe = root / "bin/antsRegistration.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"test executable")
    (root / "Runtime.json").write_text(json.dumps({"executable": "bin/antsRegistration.exe",
        "files": {"bin/antsRegistration.exe": ar.sha256_file(exe)}}))
    return exe.resolve()


def test_discovery_and_missing_bundle(monkeypatch, tmp_path):
    monkeypatch.setattr(ar, "bundled_ants_root", lambda: tmp_path / "ants")
    monkeypatch.setenv("MARM_ATLAS_SLICER", str(tmp_path / "nonexistent/Slicer.exe"))
    monkeypatch.delenv("MARM_ATLAS_ANTS", raising=False)
    with pytest.raises(FileNotFoundError, match="Bundled ANTs"):
        ar.discover_ants_runtime()
    exe = write_runtime(tmp_path / "ants")
    assert ar.discover_ants_runtime() == ar.ANTsRuntime(exe)
    exe.write_bytes(b"truncated update")
    with pytest.raises(ValueError, match="verification failed"):
        ar.discover_ants_runtime()


def test_explicit_standalone_override_never_silently_falls_back(monkeypatch, tmp_path):
    exe = write_runtime(tmp_path / "ants")
    monkeypatch.setenv("MARM_ATLAS_ANTS", str(exe))
    assert ar.discover_ants_runtime() == ar.ANTsRuntime(exe)
    monkeypatch.setenv("MARM_ATLAS_ANTS", str(tmp_path / "missing.exe"))
    with pytest.raises(FileNotFoundError, match="MARM_ATLAS_ANTS"):
        ar.discover_ants_runtime()
    monkeypatch.setenv("MARM_ATLAS_ANTS", "relative.exe")
    with pytest.raises(FileNotFoundError):
        ar.discover_ants_runtime()


def test_frozen_bundle_and_no_private_qt_dll_path(monkeypatch, tmp_path):
    frozen = tmp_path / "_internal"
    monkeypatch.setattr(sys, "_MEIPASS", str(frozen), raising=False)
    assert ar.bundled_ants_root() == frozen / "ants"
    import os
    monkeypatch.setenv("PATH", os.pathsep.join([str(frozen), str(frozen / "PySide6"), "C:/Windows/System32"]))
    env = ar.child_environment(4, frozen / "ants/bin")
    parts = env["PATH"].split(os.pathsep)
    assert parts[0] == str(frozen / "ants/bin")
    assert str(frozen) not in parts and str(frozen / "PySide6") not in parts
    assert env["ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"] == "4"


def test_runtime_manifest_cannot_escape_directory(tmp_path):
    root = tmp_path / "ants"
    write_runtime(root)
    manifest = json.loads((root / "Runtime.json").read_text())
    outside = tmp_path / "outside.dll"
    outside.write_bytes(b"test")
    manifest["files"]["../outside.dll"] = ar.sha256_file(outside)
    (root / "Runtime.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="verification failed"):
        ar.verify_bundled_runtime(root)


def test_runtime_version_records_direct_invocation(monkeypatch, tmp_path):
    from types import SimpleNamespace
    exe = write_runtime(tmp_path / "ants")
    commands = []
    def fake_run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="ANTs Version: 2.6.5", stderr="")
    monkeypatch.setattr(ar.subprocess, "run", fake_run)
    result = ar.runtime_info(ar.ANTsRuntime(exe), 4)
    assert commands == [[str(exe), "--version"]]
    assert result["invocation"] == "standalone executable (no Slicer)"
    assert "slicer_launcher" not in result


@pytest.mark.parametrize("method,scale", [("Rigid",1.), ("Similarity",1.12)])
def test_pull_direction_including_center_rotation_and_scale(method, scale):
    t = sitk.Similarity3DTransform()
    t.SetCenter((11,-4,7))
    t.SetRotation((0.,0.,1.), .19)
    t.SetScale(scale)
    t.SetTranslation((2,-3,4))
    points = np.array([[2,5,-1],[0,0,0],[10,-20,3]], float)
    forward, qc = ar.forward_from_pull(t, t.GetInverse(), method, points)
    expected = np.array([t.GetInverse().TransformPoint(tuple(p)) for p in points])
    np.testing.assert_allclose(apply_matrix(forward, points), expected, atol=1e-9)
    assert qc["degrees_of_freedom"] == (6 if method == "Rigid" else 7)
    with pytest.raises(ValueError, match="disagreement"):
        ar.forward_from_pull(t, t, method, points)


@pytest.mark.parametrize("matrix,method", [
    (np.diag([1.1,1.,1.,1.]), "Similarity"),
    (np.diag([1.1,1.1,1.1,1.]), "Rigid"),
    (np.diag([-1.,1.,1.,1.]), "Rigid"),
])
def test_wrong_dof_and_reflections_fail(matrix, method):
    with pytest.raises(ValueError):
        ar.validate_model(matrix, method)


@pytest.mark.parametrize("code", [0,1])
def test_cli_exception_is_failure_even_when_exit_zero(tmp_path, code):
    cmd = [sys.executable, "-c", f"print('ITK ERROR: All samples map outside moving image buffer'); exit({code})"]
    with pytest.raises(RuntimeError, match="Full log"):
        ar._run_logged(cmd, tmp_path / "Console.log", ar.load_parameters(), None)
    assert "ITK ERROR" in (tmp_path / "Console.log").read_text()


def test_native_outputs_and_initial_pull_are_not_double_composed(tmp_path, monkeypatch):
    path = tmp_path / "CT.nrrd"
    sitk.WriteImage(sitk.Image([8]*3, sitk.sitkFloat32), str(path))
    original = path.read_bytes()
    monkeypatch.setenv("MARM_ATLAS_STATE_ROOT", str(tmp_path/"state"))
    initial = np.eye(4)
    initial[:3,3] = [1,2,3]
    final = initial.copy()
    final[0,3] += .4
    def fake_cli(command, log, parameters, progress):
        initial_path = command[command.index("--initial-moving-transform")+1]
        np.testing.assert_allclose(ar.linear_matrix(sitk.ReadTransform(initial_path)), np.linalg.inv(initial))
        prefix = command[command.index("--output")+1]
        sitk.WriteTransform(matrix_to_sitk_affine(np.linalg.inv(final)), prefix+"Composite.h5")
        sitk.WriteTransform(matrix_to_sitk_affine(final), prefix+"InverseComposite.h5")
        log.write_text("Completed")
    monkeypatch.setattr(ar, "_run_logged", fake_cli)
    points = {"LM01":np.array([0,0,0.]),"LM02":np.array([1,0,0.]),"LM03":np.array([0,1,0.])}
    result = ar.run_ants(moving_ct=path, fixed_ct=path, initial_matrix_lps=initial,
        method="Rigid", output_directory=tmp_path/"result", moving_landmarks=points,
        fixed_landmarks=points, labels=tuple(points), runtime=ar.ANTsRuntime(Path("a")),
        parameters=ar.load_parameters(), software={})
    np.testing.assert_allclose(result.matrix_lps, final)
    assert path.read_bytes() == original
    assert json.loads((tmp_path/"result/Registration.json").read_text())["status"] == "Completed"


def make_library(tmp_path):
    template = load_reference_library(validate_files=False)
    ct = tmp_path / "CT.nrrd"
    image = sitk.GetImageFromArray(np.arange(512, dtype=np.float32).reshape(8,8,8))
    sitk.WriteImage(image, str(ct))
    label = tmp_path / "Labels.nrrd"
    sitk.WriteImage(sitk.Cast(image > 0, sitk.sitkUInt16), str(label))
    ctbl = tmp_path / "Labels.ctbl"
    ctbl.write_text("0 Background 0 0 0 0\n1 Brain 255 0 0 255\n")
    points = {f"LM{i+1:02}":np.array(p, float) for i,p in enumerate(
        [(1,1,1),(5,1,1),(1,5,1),(1,1,5),(5,5,1),(5,1,5),(1,5,5),(5,5,5)])}
    references = []
    for i in range(6):
        matrix = np.eye(4)
        matrix[1,3] = i*.02
        forward = tmp_path / f"Forward{i}.h5"
        sitk.WriteTransform(matrix_to_sitk_affine(matrix), str(forward))
        markup = tmp_path / f"LM{i}.mrk.json"
        write_slicer_markups(markup, {k:v+[i*.01,0,0] for k,v in points.items()})
        references.append(ReferenceEntry(f"Ref{i}",ct,markup,forward))
    library = replace(template, atlas_reference=ct, atlas_label_map=label, atlas_color_table=ctbl,
        atlas_layers=(AtlasLayer("T2",ct,"linear"),AtlasLayer("Regions",label,"nearest")),
        references=tuple(references),consensus=replace(template.consensus,qc_sample_count=50),
        inverse=replace(template.inverse,minimum_roundtrip_sample_count=10))
    return library, points, ct


@pytest.mark.parametrize("method", ["Rigid","Similarity"])
def test_six_ants_routes_mean_full_chains_and_saved_qc(tmp_path, monkeypatch, method):
    library, points, ct = make_library(tmp_path)
    calls = []
    def fake_ants(**kw):
        i = int(kw["output_directory"].name[-2:])-1
        np.testing.assert_allclose(kw["initial_matrix_lps"][:3,3],[i*.01,0,0],atol=1e-10)
        assert kw["method"] == method
        matrix = np.eye(4)
        matrix[:3,3] = [i*.01,0,i*.01]
        moving = np.array([kw["moving_landmarks"][key] for key in kw["labels"]])
        fixed = np.array([kw["fixed_landmarks"][key] for key in kw["labels"]])
        transformed = apply_matrix(matrix, moving)
        residual = transformed-fixed
        kw["output_directory"].mkdir(parents=True)
        (kw["output_directory"]/"Registration.json").write_text('{"status":"Completed"}')
        calls.append(i)
        return RegistrationResult(method,kw["labels"],matrix,transformed,residual,np.linalg.norm(residual,axis=1))
    monkeypatch.setattr(ar,"run_ants",fake_ants)
    monkeypatch.setattr(ar,"runtime_info",lambda *a:{"version":"test"})
    results = []
    for name, refs in [("normal",library.references),("reverse",tuple(reversed(library.references)))]:
        output = tmp_path/name
        result = run_multi_reference_registration(target_ct_path=ct,target_landmarks=points,
            requested_labels=tuple(points)[:6],method=method,library=replace(library,references=refs),
            output_directory=output,registration_type=ar.REGISTRATION_TYPE,
            ants_runtime=ar.ANTsRuntime(Path("a")))
        assert result.qc.passed and result.inverse_qc.passed
        np.testing.assert_allclose(result.consensus_transform.TransformPoint((2,3,4)),[2.025,3.05,4.025],atol=1e-9)
        manifest=json.loads((output/"Run_Manifest.json").read_text())
        assert manifest["ReferenceCount"] == 6 and manifest["CTCTBackend"] == "ANTs"
        assert len(manifest["ANTsRouteReports"]) == 6
        assert len(list((output/"TargetCT_in_Reference").glob("*.nrrd"))) == 6
        restored = load_saved_qc_session(output)
        assert restored.result.registration_type == ar.REGISTRATION_TYPE
        assert len(restored.result.routes) == 6
        assert all(len(route.registration.residual_distances)==6 for route in restored.result.routes)
        results.append(sitk.GetArrayFromImage(result.consensus_field))
    assert calls == list(range(6))*2
    np.testing.assert_array_equal(*results)


def test_rejects_old_general_and_wrong_reference_count(tmp_path):
    library, points, ct = make_library(tmp_path)
    for registration_type, refs in [("General (BRAINSFit)",library.references),
                                    (ar.REGISTRATION_TYPE,library.references[:5])]:
        with pytest.raises(ValueError):
            run_multi_reference_registration(target_ct_path=ct,target_landmarks=points,
                requested_labels=tuple(points),method="Rigid",library=replace(library,references=refs),
                output_directory=tmp_path/"unused",registration_type=registration_type)
    old = tmp_path/"old"
    old.mkdir()
    (old/"Run_Manifest.json").write_text('{"RegistrationType":"General (BRAINSFit)"}')
    with pytest.raises(ValueError,match="no longer supported"):
        load_saved_qc_session(old)
