from __future__ import annotations

import contextlib
import ctypes
import json
import os
from pathlib import Path
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass

import numpy as np
import SimpleITK as sitk

from .imaging import matrix_to_sitk_affine
from .io_manifest import sha256_file, write_json
from .paths import application_root, bundled_config_root, user_state_root
from .registration import RegistrationResult, apply_matrix
from .transform_io import read_transform

REGISTRATION_TYPE = "ANTs registration"
STAGES = {"Rigid": ("Rigid",), "Similarity": ("Rigid", "Similarity")}


@dataclass(frozen=True)
class ANTsRuntime:
    executable: Path

    def command(self, arguments):
        return [str(self.executable), *arguments]


def bundled_ants_root() -> Path:
    if getattr(sys, "_MEIPASS", None):
        return Path(sys._MEIPASS) / "ants"
    return application_root() / "runtime" / "ants"


def verify_bundled_runtime(root: Path) -> dict:
    """Fail closed if the versioned runtime is missing or was partially updated."""
    root = root.resolve()
    manifest = json.loads((root / "Runtime.json").read_text(encoding="utf-8"))
    if manifest.get("executable") != "bin/antsRegistration.exe" or not manifest.get("files"):
        raise ValueError("Invalid bundled ANTs runtime manifest.")
    if manifest["executable"] not in manifest["files"]:
        raise ValueError("ANTs executable is not covered by the runtime manifest.")
    for relative, digest in manifest["files"].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file() or sha256_file(path).lower() != digest.lower():
            raise ValueError(f"Bundled ANTs runtime verification failed: {relative}")
    return manifest


def discover_ants_runtime() -> ANTsRuntime:
    """Use bundled standalone ANTs, or one explicitly selected standalone binary.

    Never search Slicer, the working directory, or PATH for a fallback backend.
    """
    override = os.environ.get("MARM_ATLAS_ANTS")
    if override:
        executable = Path(override).expanduser()
        if not executable.is_absolute() or not executable.is_file():
            raise FileNotFoundError("MARM_ATLAS_ANTS must name an existing absolute standalone antsRegistration executable.")
        return ANTsRuntime(executable.resolve())
    root = bundled_ants_root()
    if not (root / "Runtime.json").is_file():
        raise FileNotFoundError(
            "Bundled ANTs is missing. Restore the complete Mapper distribution, "
            "or prepare runtime/ants when running from source. Slicer is not required."
        )
    manifest = verify_bundled_runtime(root)
    return ANTsRuntime((root / manifest["executable"]).resolve())


def load_parameters(path=None):
    path = Path(path) if path else bundled_config_root() / "ants_registration.json"
    parameters = json.loads(path.read_text(encoding="utf-8-sig"))
    validate_parameters(parameters)
    return parameters


def validate_parameters(p):
    if p["metric"] != "MI" or p["sampling_strategy"] != "Regular":
        raise ValueError("ANTs configuration requires MI / Regular sampling.")
    if not 0 < p["sampling_fraction"] <= 1 or not np.isfinite(p["gradient_step"]) or p["gradient_step"] <= 0:
        raise ValueError("Invalid ANTs sampling fraction or gradient step.")
    for key in ("histogram_bins", "convergence_window", "threads_per_job"):
        if not isinstance(p[key], int) or isinstance(p[key], bool) or p[key] < 1:
            raise ValueError(f"Invalid ANTs {key}.")
    if not isinstance(p["random_seed"], int) or p["random_seed"] < 0:
        raise ValueError("Invalid ANTs random seed.")
    iterations = p["iterations"].split("x")
    shrink = p["shrink"].split("x")
    sigmas = p["smoothing"].removesuffix("vox").split("x")
    if (not p["smoothing"].endswith("vox") or
        len({len(iterations), len(shrink), len(sigmas)}) != 1 or
        not all(re.fullmatch(r"[0-9]+", v) for v in iterations + shrink + sigmas) or
        min(map(int, shrink)) < 1 or sum(map(int, iterations)) < 1):
        raise ValueError("Invalid ANTs multi-resolution schedule.")
    if not 0 < float(p["convergence_threshold"]) < 1 or p["winsorize"] != "[0.005,0.995]":
        raise ValueError("Invalid ANTs convergence/winsorization setting.")
    if p["float"] is not True:
        raise ValueError("This configuration uses the validated float ANTs workflow.")


@contextlib.contextmanager
def clean_child_dll_directory():
    # Do not let the frozen Qt process's private DLLs contaminate native ANTs.
    frozen_root = getattr(sys, "_MEIPASS", None)
    if os.name == "nt" and frozen_root:
        ctypes.windll.kernel32.SetDllDirectoryW(None)
    try:
        yield
    finally:
        if os.name == "nt" and frozen_root:
            ctypes.windll.kernel32.SetDllDirectoryW(str(frozen_root))


def child_environment(threads, executable_directory=None):
    env = os.environ.copy()
    env["ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"] = str(threads)
    env["OMP_NUM_THREADS"] = str(threads)
    env["ITK_GLOBAL_DEFAULT_THREADER"] = "Platform"
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        root = os.path.normcase(os.path.abspath(frozen_root))
        env["PATH"] = os.pathsep.join(
            value for value in env.get("PATH", "").split(os.pathsep)
            if not os.path.normcase(os.path.abspath(value)).startswith(root + os.sep)
            and os.path.normcase(os.path.abspath(value)) != root
        )
    if executable_directory is not None:
        env["PATH"] = str(executable_directory) + os.pathsep + env.get("PATH", "")
    return env


def runtime_info(runtime, threads):
    with clean_child_dll_directory():
        result = subprocess.run(
            runtime.command(["--version"]), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
            env=child_environment(threads, runtime.executable.parent),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    if result.returncode or "ANTs Version" not in result.stdout:
        raise RuntimeError(f"Could not start standalone ANTs: {result.stdout}\n{result.stderr}")
    return {"executable": str(runtime.executable), "invocation": "standalone executable (no Slicer)",
            "version": result.stdout.strip(), "sha256": sha256_file(runtime.executable)}


def build_command(runtime, fixed, moving, initial_pull, prefix, method, p):
    if method not in STAGES:
        raise ValueError(f"Unsupported ANTs model: {method}")
    validate_parameters(p)
    args = ["--dimensionality", "3", "--use-histogram-matching", "0",
            "--winsorize-image-intensities", p["winsorize"], "--float", "1", "--verbose", "1",
            "--interpolation", "Linear", "--output", str(prefix),
            "--write-composite-transform", "1", "--collapse-output-transforms", "1",
            "--initial-moving-transform", str(initial_pull), "--random-seed", str(p["random_seed"])]
    for stage in STAGES[method]:
        args += ["--transform", f"{stage}[{p['gradient_step']}]",
                 "--metric", f"MI[{fixed},{moving},1,{p['histogram_bins']},Regular,{p['sampling_fraction']}]",
                 "--convergence", f"[{p['iterations']},{p['convergence_threshold']},{p['convergence_window']}]",
                 "--smoothing-sigmas", p["smoothing"], "--shrink-factors", p["shrink"]]
    return runtime.command(args)


def linear_matrix(transform):
    origin = np.asarray(transform.TransformPoint((0., 0., 0.)))
    matrix = np.eye(4)
    matrix[:3, 3] = origin
    matrix[:3, :3] = np.column_stack([
        np.asarray(transform.TransformPoint(tuple(axis))) - origin for axis in np.eye(3)])
    probes = np.random.default_rng(73).uniform(-100, 100, (20, 3))
    exact = np.asarray([transform.TransformPoint(tuple(p)) for p in probes])
    if not np.isfinite(matrix).all() or not np.allclose(apply_matrix(matrix, probes), exact, atol=1e-5, rtol=0):
        raise ValueError("ANTs did not produce a finite linear transform.")
    return matrix


def validate_model(matrix, method):
    if method not in STAGES or not np.isfinite(matrix).all() or np.linalg.det(matrix[:3, :3]) <= 1e-8:
        raise ValueError("Invalid/reflected ANTs transform.")
    singular = np.linalg.svd(matrix[:3, :3], compute_uv=False)
    if method == "Rigid" and not np.allclose(singular, 1, atol=1e-4, rtol=0):
        raise ValueError("ANTs Rigid contains scale/shear.")
    if method == "Similarity" and np.ptp(singular) / singular.mean() > 1e-4:
        raise ValueError("ANTs Similarity must have isotropic scale (7 DOF).")
    return {"degrees_of_freedom": 6 if method == "Rigid" else 7,
            "singular_values": singular.tolist(), "determinant": float(np.linalg.det(matrix[:3, :3]))}


def forward_from_pull(pull, native_inverse, method, check_points):
    # ANTs Composite maps fixed points -> moving points (image-resampling pull).
    # Our application always composes modeling/point transforms moving -> fixed.
    matrix = np.linalg.inv(linear_matrix(pull))
    model_qc = validate_model(matrix, method)
    inverse_matrix = linear_matrix(native_inverse)
    probes = np.vstack((check_points, np.zeros((1, 3)), np.eye(3)))
    error = np.linalg.norm(apply_matrix(matrix, probes) - apply_matrix(inverse_matrix, probes), axis=1).max()
    if not np.isfinite(error) or error > 0.001:
        raise ValueError(f"ANTs native forward/inverse disagreement: {error:.6g} mm.")
    return matrix, {**model_qc, "native_inverse_agreement_max_mm": float(error)}


def _run_logged(command, console_path, p, progress):
    with clean_child_dll_directory():
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            encoding="utf-8", errors="replace",
            env=child_environment(p["threads_per_job"], Path(command[0]).parent),
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    messages = queue.Queue()
    def reader():
        try:
            for line in process.stdout:
                messages.put(line)
        finally:
            messages.put(None)
    worker = threading.Thread(target=reader, daemon=True)
    worker.start()
    errors = []
    last_progress = 0.0
    try:
        with console_path.open("w", encoding="utf-8") as console:
            while True:
                try:
                    line = messages.get(timeout=0.2)
                except queue.Empty:
                    line = ""
                if line is None:
                    break
                if line:
                    console.write(line)
                    console.flush()
                    if re.search(r"ExceptionObject|Exception caught|ITK ERROR|All samples map outside|Too many samples map outside", line, re.I):
                        errors.append(line.strip())
                if progress and time.monotonic() - last_progress >= 1.0:
                    progress("ANTs: " + (line.strip()[-200:] if line.strip() else "registration running..."))
                    last_progress = time.monotonic()
        code = process.wait()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        worker.join(timeout=10)
        process.stdout.close()
    if code != 0 or errors:
        raise RuntimeError(f"ANTs registration failed (exit {code}).\n" + "\n".join(errors[-5:]) + f"\nFull log: {console_path}")
    return code


def _native_work_path(path):
    value = str(path)
    if os.name == "nt" and (not value.isascii() or any(c in value for c in ",[]")):
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.kernel32.GetShortPathNameW(value, buffer, len(buffer)):
            value = buffer.value
    if not value.isascii() or any(c in value for c in ",[]"):
        raise ValueError("ANTs requires a working directory without non-ASCII characters, commas or brackets. "
                         "Set MARM_ATLAS_STATE_ROOT to a suitable local folder.")
    return Path(value)


def run_ants(*, moving_ct, fixed_ct, initial_matrix_lps, method, output_directory,
             moving_landmarks, fixed_landmarks, labels, runtime, parameters, software, progress=None):
    method = method.strip().capitalize()
    validate_model(np.asarray(initial_matrix_lps), "Rigid")
    validate_parameters(parameters)
    if method not in STAGES:
        raise ValueError("ANTs supports Rigid or Similarity.")
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=False)
    report = {"status": "Running", "backend": "ANTs", "mask": "None", "method": method,
              "initialization": "Selected common landmarks; Rigid; independently for each reference",
              "parameters": parameters, "software": software,
              "inputs": {name: {"path": str(Path(path).resolve()), "sha256": sha256_file(path)}
                         for name, path in (("moving_ct", moving_ct), ("fixed_ct", fixed_ct))},
              "labels": list(labels), "initial_forward_matrix_lps": np.asarray(initial_matrix_lps).tolist()}
    write_json(output / "Registration.json", report)
    cache = user_state_root() / "ants_jobs"
    cache.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="run_", dir=cache) as temporary:
            work = _native_work_path(Path(temporary))
            for source, name in ((moving_ct, "moving"), (fixed_ct, "fixed")):
                image = sitk.ReadImage(str(source))
                if image.GetDimension() != 3 or image.GetNumberOfComponentsPerPixel() != 1:
                    raise ValueError("ANTs requires scalar 3D CT images.")
                if not np.isfinite(sitk.GetArrayViewFromImage(image)).all():
                    raise ValueError("CT contains nonfinite intensities.")
                # Preserve voxel values and physical geometry; no pre-resampling.
                sitk.WriteImage(image, str(work / f"{name}.nii.gz"), True)
            initial_pull = work / "Initial_FixedToMoving.tfm"
            sitk.WriteTransform(matrix_to_sitk_affine(np.linalg.inv(initial_matrix_lps)), str(initial_pull))
            shutil.copy2(initial_pull, output / initial_pull.name)
            prefix = work / "ANTs_"
            command = build_command(runtime, work / "fixed.nii.gz", work / "moving.nii.gz",
                                    initial_pull, prefix, method, parameters)
            write_json(output / "Command.json", {"argv": command, "temporary_inputs": True})
            _run_logged(command, output / "Console.log", parameters, progress)
            pull_path = work / "ANTs_Composite.h5"
            inverse_path = work / "ANTs_InverseComposite.h5"
            if not pull_path.is_file() or not inverse_path.is_file():
                raise RuntimeError("ANTs did not produce both composite transforms; see Console.log.")
            moving = np.vstack([moving_landmarks[label] for label in labels])
            fixed = np.vstack([fixed_landmarks[label] for label in labels])
            matrix, qc = forward_from_pull(read_transform(pull_path), read_transform(inverse_path), method, moving)
            for source in (pull_path, inverse_path):
                shutil.copy2(source, output / source.name)
            forward_path = work / "TargetCT_to_Reference_Forward.h5"
            sitk.WriteTransform(matrix_to_sitk_affine(matrix), str(forward_path))
            reloaded = linear_matrix(read_transform(forward_path))
            if not np.allclose(reloaded, matrix, atol=1e-8, rtol=0):
                raise ValueError("Saved/reloaded ANTs forward transform changed coordinates.")
            shutil.copy2(forward_path, output / forward_path.name)
        transformed = apply_matrix(matrix, moving)
        residuals = transformed - fixed
        result = RegistrationResult(method, labels, matrix, transformed, residuals, np.linalg.norm(residuals, axis=1))
        report.update(status="Completed", matrix_target_to_reference_lps=matrix.tolist(), qc=qc,
                      forward_transform="TargetCT_to_Reference_Forward.h5",
                      forward_transform_convention="Point/modeling LPS: Target CT -> Reference CT",
                      native_composite_convention="Pull LPS: Reference CT -> Target CT",
                      post_registration_landmark_rms_mm=result.rms_mm)
        write_json(output / "Registration.json", report)
        return result
    except Exception as exc:
        report.update(status="Failed", error=str(exc))
        write_json(output / "Registration.json", report)
        raise
