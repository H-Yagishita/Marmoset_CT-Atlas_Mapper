from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import SimpleITK as sitk

from .imaging import matrix_to_sitk_affine
from .registration import RegistrationResult, apply_matrix
from .transform_io import read_transform


ProgressCallback = Callable[[str], None]


@dataclass(frozen=True)
class BRAINSFitRuntime:
    slicer_launcher: Path
    brainsfit_executable: Path


def discover_brainsfit_runtime() -> BRAINSFitRuntime:
    """Find an installed Slicer/BRAINSFit without embedding a machine path."""
    candidates: list[Path] = []
    configured = os.environ.get("MARM_ATLAS_SLICER")
    if configured:
        candidates.append(Path(configured))
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.extend(
            sorted(
                (Path(local_app_data) / "slicer.org").glob("Slicer */Slicer.exe"),
                reverse=True,
            )
        )
    for launcher in candidates:
        if not launcher.is_file():
            continue
        cli_candidates = sorted(
            launcher.parent.glob("lib/Slicer-*/cli-modules/BRAINSFit.exe"),
            reverse=True,
        )
        if cli_candidates:
            return BRAINSFitRuntime(launcher.resolve(), cli_candidates[0].resolve())
    raise FileNotFoundError(
        "BRAINSFit was not found. Install 3D Slicer or set MARM_ATLAS_SLICER "
        "to the full path of Slicer.exe."
    )


def transform_to_matrix_lps(transform: sitk.Transform) -> np.ndarray:
    """Recover a homogeneous matrix from a verified linear ITK transform."""
    origin = np.asarray(transform.TransformPoint((0.0, 0.0, 0.0)), dtype=float)
    columns = []
    for axis in range(3):
        basis = np.zeros(3, dtype=float)
        basis[axis] = 1.0
        columns.append(np.asarray(transform.TransformPoint(tuple(basis)), dtype=float) - origin)
    matrix = np.eye(4, dtype=float)
    matrix[:3, :3] = np.column_stack(columns)
    matrix[:3, 3] = origin
    probes = np.asarray([[2.3, -1.2, 4.1], [-5.0, 2.0, 0.4]], dtype=float)
    exact = np.asarray([transform.TransformPoint(tuple(point)) for point in probes])
    if not np.allclose(apply_matrix(matrix, probes), exact, atol=1e-5):
        raise ValueError("BRAINSFit produced a non-linear transform; a linear result was required.")
    return matrix


def run_brainsfit(
    *,
    moving_ct: str | Path,
    fixed_ct: str | Path,
    initial_matrix_lps: np.ndarray,
    method: str,
    output_directory: str | Path,
    moving_landmarks: dict[str, np.ndarray],
    fixed_landmarks: dict[str, np.ndarray],
    labels: tuple[str, ...],
    progress: ProgressCallback | None = None,
) -> tuple[RegistrationResult, Path, BRAINSFitRuntime]:
    normalized = method.strip().capitalize()
    if normalized not in {"Rigid", "Similarity"}:
        raise ValueError(f"Unsupported BRAINSFit method: {method}")
    runtime = discover_brainsfit_runtime()
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    initial_path = output / "Target_CT_to_J0476M_LandmarkRigid_Initial.h5"
    final_path = output / f"Target_CT_to_J0476M_BRAINSFit_{normalized}.h5"
    report_path = output / "BRAINSFit_MetricReport.csv"
    sitk.WriteTransform(matrix_to_sitk_affine(initial_matrix_lps), str(initial_path))
    transform_type = "Rigid" if normalized == "Rigid" else "Rigid,ScaleVersor3D"
    command = [
        str(runtime.slicer_launcher),
        "--launch",
        str(runtime.brainsfit_executable),
        "--fixedVolume", str(Path(fixed_ct)),
        "--movingVolume", str(Path(moving_ct)),
        "--initialTransform", str(initial_path),
        "--initializeTransformMode", "Off",
        "--transformType", transform_type,
        "--linearTransform", str(final_path),
        "--maskProcessingMode", "ROIAUTO",
        "--ROIAutoClosingSize", "0.9",
        "--ROIAutoDilateSize", "0.9",
        "--costMetric", "MMI",
        "--samplingPercentage", "0.02",
        "--logFileReport", str(report_path),
    ]
    if progress:
        progress(
            f"BRAINSFit runtime: {runtime.slicer_launcher.parent.name}; "
            f"stages={transform_type}, sampling=2%, mask=ROIAUTO."
        )
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creation_flags,
    )
    assert process.stdout is not None
    for line in process.stdout:
        message = line.strip()
        if message and progress:
            progress(f"BRAINSFit: {message}")
    return_code = process.wait()
    if return_code != 0 or not final_path.is_file():
        raise RuntimeError(f"BRAINSFit failed with exit code {return_code}.")
    final_transform = read_transform(final_path)
    matrix = transform_to_matrix_lps(final_transform)
    moving = np.vstack([moving_landmarks[label] for label in labels])
    fixed = np.vstack([fixed_landmarks[label] for label in labels])
    transformed = apply_matrix(matrix, moving)
    residual_vectors = transformed - fixed
    result = RegistrationResult(
        method=normalized,
        labels=labels,
        matrix_lps=matrix,
        transformed_moving=transformed,
        residual_vectors=residual_vectors,
        residual_distances=np.linalg.norm(residual_vectors, axis=1),
    )
    return result, final_path, runtime
