from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import SimpleITK as sitk

from .displacement_consensus import GridGeometryRAS, displacement_transform, image_bounds_ras
from .transform_composition import transform_points


@dataclass(frozen=True)
class ErrorStatistics:
    mean_mm: float
    p95_mm: float
    maximum_mm: float


@dataclass(frozen=True)
class TransformQCReport:
    component_approximation: dict[str, ErrorStatistics]
    consensus_approximation: ErrorStatistics
    finite_displacements: bool
    finite_mapped_points: bool
    target_bounds_in_domain: bool
    component_threshold_mm: float
    consensus_threshold_mm: float

    @property
    def passed(self) -> bool:
        return bool(
            self.finite_displacements
            and self.finite_mapped_points
            and self.target_bounds_in_domain
            and all(
                value.p95_mm < self.component_threshold_mm
                for value in self.component_approximation.values()
            )
            and self.consensus_approximation.p95_mm < self.consensus_threshold_mm
        )


def error_statistics(errors_mm: np.ndarray) -> ErrorStatistics:
    errors = np.asarray(errors_mm, dtype=float)
    if errors.ndim != 1 or errors.size == 0 or not np.all(np.isfinite(errors)):
        raise ValueError("QC errors must be a finite non-empty vector.")
    return ErrorStatistics(
        float(np.mean(errors)),
        float(np.percentile(errors, 95)),
        float(np.max(errors)),
    )


def sample_target_points_lps(image: sitk.Image, count: int, seed: int) -> np.ndarray:
    if count < 1:
        raise ValueError("QC sample count must be positive.")
    rng = np.random.default_rng(seed)
    size = np.asarray(image.GetSize(), dtype=float)
    indices = rng.random((count, 3)) * np.maximum(size - 1.001, 0.0)
    return np.asarray(
        [image.TransformContinuousIndexToPhysicalPoint(tuple(index)) for index in indices],
        dtype=float,
    )


def target_bounds_within_grid(target_image: sitk.Image, grid: GridGeometryRAS, tolerance_mm: float = 1e-6) -> bool:
    target_lower, target_upper = image_bounds_ras(target_image)
    grid_lower = np.asarray(grid.origin_ras)
    grid_upper = np.asarray(grid.upper_ras)
    return bool(
        np.all(target_lower >= grid_lower - tolerance_mm)
        and np.all(target_upper <= grid_upper + tolerance_mm)
    )


def evaluate_forward_fields(
    *,
    target_image: sitk.Image,
    grid: GridGeometryRAS,
    exact_outputs_by_reference: Mapping[str, np.ndarray],
    component_fields: Mapping[str, sitk.Image],
    consensus_field: sitk.Image,
    qc_points_lps: np.ndarray,
    component_threshold_mm: float,
    consensus_threshold_mm: float,
) -> TransformQCReport:
    ids = sorted(component_fields)
    if ids != sorted(exact_outputs_by_reference):
        raise ValueError("Exact route outputs and component fields have different reference IDs.")
    component_stats: dict[str, ErrorStatistics] = {}
    finite_mapped = True
    for reference_id in ids:
        approximate = transform_points(displacement_transform(component_fields[reference_id]), qc_points_lps)
        exact = np.asarray(exact_outputs_by_reference[reference_id], dtype=float)
        finite_mapped = finite_mapped and bool(np.all(np.isfinite(exact)) and np.all(np.isfinite(approximate)))
        component_stats[reference_id] = error_statistics(np.linalg.norm(approximate - exact, axis=1))

    exact_mean = np.mean(
        np.stack([np.asarray(exact_outputs_by_reference[reference_id]) for reference_id in ids], axis=0),
        axis=0,
        dtype=np.float64,
    )
    consensus_output = transform_points(displacement_transform(consensus_field), qc_points_lps)
    finite_mapped = finite_mapped and bool(
        np.all(np.isfinite(exact_mean)) and np.all(np.isfinite(consensus_output))
    )
    consensus_stats = error_statistics(np.linalg.norm(consensus_output - exact_mean, axis=1))
    finite_fields = all(
        np.all(np.isfinite(sitk.GetArrayViewFromImage(field)))
        for field in [*component_fields.values(), consensus_field]
    )
    return TransformQCReport(
        component_approximation=component_stats,
        consensus_approximation=consensus_stats,
        finite_displacements=bool(finite_fields),
        finite_mapped_points=finite_mapped,
        target_bounds_in_domain=target_bounds_within_grid(target_image, grid),
        component_threshold_mm=float(component_threshold_mm),
        consensus_threshold_mm=float(consensus_threshold_mm),
    )
