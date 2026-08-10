from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import SimpleITK as sitk

from .displacement_consensus import GridGeometryRAS, create_target_ras_grid, displacement_transform
from .transform_qc import ErrorStatistics, error_statistics, sample_target_points_lps
from .transform_composition import transform_points


@dataclass(frozen=True)
class InverseQCReport:
    roundtrip: ErrorStatistics
    converged_target_samples: int
    target_sample_count: int
    valid_inverse_voxels: int
    inverse_voxel_count: int
    valid_atlas_voxels: int
    atlas_voxel_count: int
    threshold_mm: float
    minimum_roundtrip_sample_count: int

    @property
    def target_sample_fraction(self) -> float:
        return self.converged_target_samples / self.target_sample_count

    @property
    def inverse_valid_fraction(self) -> float:
        return self.valid_inverse_voxels / self.inverse_voxel_count

    @property
    def atlas_coverage_fraction(self) -> float:
        return self.valid_atlas_voxels / self.atlas_voxel_count

    @property
    def passed(self) -> bool:
        return bool(
            self.converged_target_samples >= self.minimum_roundtrip_sample_count
            and np.isfinite(self.roundtrip.p95_mm)
            and self.roundtrip.p95_mm < self.threshold_mm
        )


@dataclass(frozen=True)
class RobustInverseResult:
    grid: GridGeometryRAS
    inverse_field: sitk.Image
    inverse_transform: sitk.DisplacementFieldTransform
    convergence_mask: sitk.Image
    qc: InverseQCReport


class _FieldInterpolator:
    def __init__(self, field: sitk.Image) -> None:
        self.values = np.asarray(sitk.GetArrayViewFromImage(field), dtype=np.float64)
        if self.values.ndim != 4 or self.values.shape[-1] != 3:
            raise ValueError("Forward displacement field must contain 3-component vectors.")
        self.origin = np.asarray(field.GetOrigin(), dtype=np.float64)
        self.spacing = np.asarray(field.GetSpacing(), dtype=np.float64)
        self.direction = np.asarray(field.GetDirection(), dtype=np.float64).reshape(3, 3)
        self.size = np.asarray(field.GetSize(), dtype=int)

        du_dz, du_dy, du_dx = np.gradient(
            self.values,
            self.spacing[2],
            self.spacing[1],
            self.spacing[0],
            axis=(0, 1, 2),
            edge_order=1,
        )
        # Gq[..., component, image-axis] then convert q = D.T * physical.
        gradient_q = np.stack((du_dx, du_dy, du_dz), axis=-1)
        gradient_physical = np.einsum("...ca,ap->...cp", gradient_q, self.direction.T)
        self.jacobian_values = gradient_physical.reshape((*self.values.shape[:3], 9))

    def physical_to_index(self, points_lps: np.ndarray) -> np.ndarray:
        relative = np.asarray(points_lps, dtype=np.float64) - self.origin
        return (relative @ self.direction) / self.spacing

    def _interpolate_array(
        self,
        array_zyx_components: np.ndarray,
        points_lps: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        index = self.physical_to_index(points_lps)
        valid = np.all(index >= 0.0, axis=1) & np.all(index <= self.size - 1.0, axis=1)
        clipped = np.clip(index, 0.0, self.size - 1.0)
        lower = np.floor(clipped).astype(int)
        lower = np.minimum(lower, self.size - 2)
        fraction = clipped - lower
        x0, y0, z0 = lower.T
        wx, wy, wz = fraction.T

        output = np.zeros((len(points_lps), array_zyx_components.shape[-1]), dtype=np.float64)
        for dz in (0, 1):
            for dy in (0, 1):
                for dx in (0, 1):
                    weight = (
                        (wz if dz else 1.0 - wz)
                        * (wy if dy else 1.0 - wy)
                        * (wx if dx else 1.0 - wx)
                    )
                    output += array_zyx_components[z0 + dz, y0 + dy, x0 + dx] * weight[:, None]
        return output, valid

    def forward(self, points_lps: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        displacement, valid = self._interpolate_array(self.values, points_lps)
        return np.asarray(points_lps, dtype=np.float64) + displacement, valid

    def jacobian(self, points_lps: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        derivative, valid = self._interpolate_array(self.jacobian_values, points_lps)
        jacobian = derivative.reshape((-1, 3, 3))
        jacobian += np.eye(3, dtype=np.float64)[None, ...]
        return jacobian, valid


def _grid_points_lps(grid: GridGeometryRAS) -> np.ndarray:
    x, y, z = np.meshgrid(
        np.arange(grid.size[0], dtype=np.float64),
        np.arange(grid.size[1], dtype=np.float64),
        np.arange(grid.size[2], dtype=np.float64),
        indexing="xy",
    )
    # meshgrid(x,y,z,indexing=xy) returns (y,x,z); transpose to z,y,x for ITK arrays.
    index_xyz = np.stack((x, y, z), axis=-1).transpose(2, 0, 1, 3).reshape((-1, 3))
    direction = np.asarray(grid.direction_lps, dtype=np.float64).reshape(3, 3)
    return np.asarray(grid.origin_lps) + (index_xyz * np.asarray(grid.spacing_mm)) @ direction.T


def _fit_global_inverse_affine(interpolator: _FieldInterpolator) -> np.ndarray:
    fractions = np.linspace(0.05, 0.95, 6)
    indices = np.asarray(
        np.meshgrid(
            fractions * (interpolator.size[0] - 1),
            fractions * (interpolator.size[1] - 1),
            fractions * (interpolator.size[2] - 1),
            indexing="ij",
        )
    ).reshape(3, -1).T
    source = interpolator.origin + (indices * interpolator.spacing) @ interpolator.direction.T
    mapped, valid = interpolator.forward(source)
    if np.count_nonzero(valid) < 12:
        raise RuntimeError("Insufficient forward samples for inverse initialization.")
    design = np.column_stack((mapped[valid], np.ones(np.count_nonzero(valid))))
    coefficients, *_ = np.linalg.lstsq(design, source[valid], rcond=None)
    return coefficients


def _newton_inverse(
    interpolator: _FieldInterpolator,
    atlas_points_lps: np.ndarray,
    initialization: np.ndarray,
    *,
    maximum_iterations: int,
    convergence_tolerance_mm: float,
    maximum_step_mm: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    design = np.column_stack((atlas_points_lps, np.ones(len(atlas_points_lps))))
    estimate = design @ initialization
    finite = np.all(np.isfinite(estimate), axis=1)

    for _ in range(maximum_iterations):
        mapped, inside_field = interpolator.forward(estimate)
        residual = mapped - atlas_points_lps
        residual_norm = np.linalg.norm(residual, axis=1)
        active = finite & inside_field & (residual_norm > convergence_tolerance_mm)
        if not np.any(active):
            break
        active_indices = np.flatnonzero(active)
        jacobian, jacobian_valid = interpolator.jacobian(estimate[active_indices])
        determinant = np.linalg.det(jacobian)
        solvable = jacobian_valid & np.isfinite(determinant) & (np.abs(determinant) > 1e-8)
        finite[active_indices[~solvable]] = False
        if not np.any(solvable):
            break
        solve_indices = active_indices[solvable]
        step = np.linalg.solve(
            jacobian[solvable],
            residual[solve_indices, :, None],
        )[..., 0]
        step_norm = np.linalg.norm(step, axis=1)
        scale = np.minimum(1.0, maximum_step_mm / np.maximum(step_norm, 1e-12))
        estimate[solve_indices] -= step * scale[:, None]
        finite[solve_indices] &= np.all(np.isfinite(estimate[solve_indices]), axis=1)

    mapped, inside_field = interpolator.forward(estimate)
    residual_norm = np.linalg.norm(mapped - atlas_points_lps, axis=1)
    converged = finite & inside_field & np.isfinite(residual_norm) & (
        residual_norm <= convergence_tolerance_mm
    )
    return estimate, converged, residual_norm


def _image_from_flat_vectors(values: np.ndarray, grid: GridGeometryRAS) -> sitk.Image:
    array = np.asarray(values, dtype=np.float64).reshape((grid.size[2], grid.size[1], grid.size[0], 3))
    image = sitk.GetImageFromArray(array, isVector=True)
    image.SetOrigin(grid.origin_lps)
    image.SetSpacing(grid.spacing_mm)
    image.SetDirection(grid.direction_lps)
    return image


def _image_from_flat_mask(values: np.ndarray, grid: GridGeometryRAS) -> sitk.Image:
    array = np.asarray(values, dtype=np.uint8).reshape((grid.size[2], grid.size[1], grid.size[0]))
    image = sitk.GetImageFromArray(array)
    image.SetOrigin(grid.origin_lps)
    image.SetSpacing(grid.spacing_mm)
    image.SetDirection(grid.direction_lps)
    return image


def generate_robust_inverse(
    *,
    forward_field: sitk.Image,
    target_image: sitk.Image,
    atlas_reference: sitk.Image,
    inverse_spacing_mm: float = 0.5,
    inverse_padding_mm: float = 1.0,
    maximum_iterations: int = 20,
    convergence_tolerance_mm: float = 0.05,
    maximum_step_mm: float = 5.0,
    qc_sample_count: int = 300,
    random_seed: int = 260807,
    roundtrip_threshold_mm: float = 0.25,
    minimum_roundtrip_sample_count: int = 30,
) -> RobustInverseResult:
    interpolator = _FieldInterpolator(forward_field)
    inverse_grid = create_target_ras_grid(
        atlas_reference,
        inverse_spacing_mm,
        inverse_padding_mm,
    )
    atlas_points = _grid_points_lps(inverse_grid)
    initialization = _fit_global_inverse_affine(interpolator)
    inverse_points, converged, _ = _newton_inverse(
        interpolator,
        atlas_points,
        initialization,
        maximum_iterations=maximum_iterations,
        convergence_tolerance_mm=convergence_tolerance_mm,
        maximum_step_mm=maximum_step_mm,
    )
    inverse_displacement = inverse_points - atlas_points
    inverse_displacement[~converged] = 0.0
    inverse_field = _image_from_flat_vectors(inverse_displacement, inverse_grid)
    convergence_mask = _image_from_flat_mask(converged, inverse_grid)
    inverse_transform = displacement_transform(inverse_field)

    atlas_mask = sitk.Resample(
        convergence_mask,
        atlas_reference,
        sitk.Transform(3, sitk.sitkIdentity),
        sitk.sitkNearestNeighbor,
        0,
        sitk.sitkUInt8,
    )
    valid_atlas_voxels = int(np.count_nonzero(sitk.GetArrayViewFromImage(atlas_mask)))
    atlas_voxel_count = int(np.prod(atlas_reference.GetSize()))

    forward_transform = displacement_transform(forward_field)
    target_samples = sample_target_points_lps(target_image, qc_sample_count, random_seed)
    atlas_samples = transform_points(forward_transform, target_samples)
    recovered = transform_points(inverse_transform, atlas_samples)
    mask_values = sitk.GetArrayViewFromImage(convergence_mask)
    inverse_index = np.asarray(
        [convergence_mask.TransformPhysicalPointToContinuousIndex(tuple(point)) for point in atlas_samples]
    )
    nearest = np.rint(inverse_index).astype(int)
    size = np.asarray(convergence_mask.GetSize())
    inside = np.all(nearest >= 0, axis=1) & np.all(nearest < size, axis=1)
    sample_converged = np.zeros(len(target_samples), dtype=bool)
    valid_indices = np.flatnonzero(inside)
    if len(valid_indices):
        xyz = nearest[valid_indices]
        sample_converged[valid_indices] = mask_values[xyz[:, 2], xyz[:, 1], xyz[:, 0]] > 0
    errors = np.linalg.norm(recovered - target_samples, axis=1)
    errors[~sample_converged] = np.inf
    finite_errors = errors[np.isfinite(errors)]
    if finite_errors.size:
        stats = error_statistics(finite_errors)
    else:
        stats = ErrorStatistics(float("inf"), float("inf"), float("inf"))
    qc = InverseQCReport(
        roundtrip=stats,
        converged_target_samples=int(np.count_nonzero(sample_converged)),
        target_sample_count=len(target_samples),
        valid_inverse_voxels=int(np.count_nonzero(converged)),
        inverse_voxel_count=len(converged),
        valid_atlas_voxels=valid_atlas_voxels,
        atlas_voxel_count=atlas_voxel_count,
        threshold_mm=float(roundtrip_threshold_mm),
        minimum_roundtrip_sample_count=int(minimum_roundtrip_sample_count),
    )
    return RobustInverseResult(
        grid=inverse_grid,
        inverse_field=inverse_field,
        inverse_transform=inverse_transform,
        convergence_mask=convergence_mask,
        qc=qc,
    )
