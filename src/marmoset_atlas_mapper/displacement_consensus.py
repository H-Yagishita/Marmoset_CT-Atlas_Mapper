from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Mapping

import numpy as np
import SimpleITK as sitk


LPS_RAS = np.diag([-1.0, -1.0, 1.0])
RAS_GRID_DIRECTION_IN_LPS = tuple(LPS_RAS.reshape(-1))


@dataclass(frozen=True)
class GridGeometryRAS:
    origin_ras: tuple[float, float, float]
    spacing_mm: tuple[float, float, float]
    size: tuple[int, int, int]

    @property
    def origin_lps(self) -> tuple[float, float, float]:
        return tuple((LPS_RAS @ np.asarray(self.origin_ras, dtype=float)).tolist())

    @property
    def direction_lps(self) -> tuple[float, ...]:
        return RAS_GRID_DIRECTION_IN_LPS

    @property
    def upper_ras(self) -> tuple[float, float, float]:
        origin = np.asarray(self.origin_ras)
        spacing = np.asarray(self.spacing_mm)
        return tuple((origin + spacing * (np.asarray(self.size) - 1)).tolist())


@dataclass(frozen=True)
class UncertaintyFields:
    rms_from_consensus: sitk.Image
    maximum_from_consensus: sitk.Image
    maximum_pairwise: sitk.Image


def image_bounds_ras(image: sitk.Image) -> tuple[np.ndarray, np.ndarray]:
    size = np.asarray(image.GetSize(), dtype=float)
    corners_lps = []
    for index in itertools.product(*[(-0.5, value - 0.5) for value in size]):
        corners_lps.append(image.TransformContinuousIndexToPhysicalPoint(tuple(index)))
    corners_ras = (LPS_RAS @ np.asarray(corners_lps, dtype=float).T).T
    return corners_ras.min(axis=0), corners_ras.max(axis=0)


def create_target_ras_grid(
    target_image: sitk.Image,
    spacing_mm: float = 0.5,
    padding_mm: float = 1.0,
) -> GridGeometryRAS:
    if spacing_mm <= 0.0 or padding_mm < 0.0:
        raise ValueError("Grid spacing must be positive and padding must be non-negative.")
    lower, upper = image_bounds_ras(target_image)
    origin = lower - padding_mm
    requested_upper = upper + padding_mm
    spacing = np.repeat(float(spacing_mm), 3)
    size = np.ceil((requested_upper - origin) / spacing).astype(int) + 1
    if np.any(size < 2):
        raise ValueError(f"Invalid consensus grid size: {tuple(size)}")
    return GridGeometryRAS(
        tuple(origin.tolist()),
        tuple(spacing.tolist()),
        tuple(int(value) for value in size),
    )


def sample_forward_transform(
    transform_lps: sitk.Transform,
    grid: GridGeometryRAS,
) -> sitk.Image:
    field = sitk.TransformToDisplacementField(
        transform_lps,
        sitk.sitkVectorFloat64,
        grid.size,
        grid.origin_lps,
        grid.spacing_mm,
        grid.direction_lps,
    )
    array = sitk.GetArrayViewFromImage(field)
    if array.ndim != 4 or array.shape[-1] != 3 or not np.all(np.isfinite(array)):
        raise ValueError("Sampled displacement field contains undefined/non-finite values.")
    return field


def displacement_transform(field: sitk.Image) -> sitk.DisplacementFieldTransform:
    if field.GetNumberOfComponentsPerPixel() != 3:
        raise ValueError("Expected a 3-component displacement field.")
    return sitk.DisplacementFieldTransform(sitk.Image(field))


def _check_field_geometry(fields: Mapping[str, sitk.Image]) -> list[str]:
    ids = sorted(fields)
    if not ids:
        raise ValueError("No component displacement fields were supplied.")
    first = fields[ids[0]]
    for reference_id in ids[1:]:
        field = fields[reference_id]
        if (
            field.GetSize() != first.GetSize()
            or not np.allclose(field.GetOrigin(), first.GetOrigin(), atol=1e-9)
            or not np.allclose(field.GetSpacing(), first.GetSpacing(), atol=1e-12)
            or not np.allclose(field.GetDirection(), first.GetDirection(), atol=1e-12)
        ):
            raise ValueError(f"Component field geometry differs for {reference_id}.")
    return ids


def equal_weight_consensus(fields: Mapping[str, sitk.Image]) -> sitk.Image:
    ids = _check_field_geometry(fields)
    arrays = [np.asarray(sitk.GetArrayViewFromImage(fields[reference_id]), dtype=np.float64) for reference_id in ids]
    mean = np.mean(np.stack(arrays, axis=0), axis=0, dtype=np.float64)
    if not np.all(np.isfinite(mean)):
        raise ValueError("Consensus displacement contains undefined/non-finite values.")
    output = sitk.GetImageFromArray(mean, isVector=True)
    output.CopyInformation(fields[ids[0]])
    return output


def _scalar_image(array_zyx: np.ndarray, reference: sitk.Image) -> sitk.Image:
    image = sitk.GetImageFromArray(np.asarray(array_zyx, dtype=np.float32))
    image.SetOrigin(reference.GetOrigin())
    image.SetSpacing(reference.GetSpacing())
    image.SetDirection(reference.GetDirection())
    return image


def calculate_uncertainty(fields: Mapping[str, sitk.Image], consensus: sitk.Image) -> UncertaintyFields:
    ids = _check_field_geometry(fields)
    consensus_array = np.asarray(sitk.GetArrayViewFromImage(consensus), dtype=np.float64)
    components = np.stack(
        [np.asarray(sitk.GetArrayViewFromImage(fields[reference_id]), dtype=np.float64) for reference_id in ids],
        axis=0,
    )
    deviations = np.linalg.norm(components - consensus_array[None, ...], axis=-1)
    rms = np.sqrt(np.mean(deviations**2, axis=0))
    maximum = np.max(deviations, axis=0)
    pairwise = np.zeros_like(rms)
    for first, second in itertools.combinations(range(len(ids)), 2):
        distance = np.linalg.norm(components[first] - components[second], axis=-1)
        pairwise = np.maximum(pairwise, distance)
    if not all(np.all(np.isfinite(value)) for value in (rms, maximum, pairwise)):
        raise ValueError("Uncertainty calculation produced undefined/non-finite values.")
    return UncertaintyFields(
        _scalar_image(rms, consensus),
        _scalar_image(maximum, consensus),
        _scalar_image(pairwise, consensus),
    )
