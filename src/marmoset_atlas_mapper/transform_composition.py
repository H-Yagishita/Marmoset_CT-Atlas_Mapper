from __future__ import annotations

from pathlib import Path

import numpy as np
import SimpleITK as sitk

from .imaging import matrix_to_sitk_affine
from .transform_io import read_transform


def compose_target_to_atlas(
    target_to_reference_matrix_lps: np.ndarray,
    reference_to_atlas_forward_path: str | Path,
) -> sitk.CompositeTransform:
    """Compose Target CT -> Reference CT -> BMA2.0 in physical LPS coordinates."""
    target_to_reference = matrix_to_sitk_affine(target_to_reference_matrix_lps)
    reference_to_atlas = read_transform(reference_to_atlas_forward_path)
    # SimpleITK applies the last composite member first.
    return sitk.CompositeTransform([reference_to_atlas, target_to_reference])


def transform_points(transform: sitk.Transform, points_lps: np.ndarray) -> np.ndarray:
    points = np.asarray(points_lps, dtype=float)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("Expected an Nx3 point array.")
    output = np.asarray(
        [transform.TransformPoint(tuple(float(value) for value in point)) for point in points],
        dtype=float,
    )
    if not np.all(np.isfinite(output)):
        raise ValueError("Transform produced an undefined or non-finite point.")
    return output
