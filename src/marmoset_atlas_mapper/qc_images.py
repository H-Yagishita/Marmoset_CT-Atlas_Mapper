from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

import numpy as np
import SimpleITK as sitk
from .native_io import write_image

from .imaging import normalize_to_uint8, resample_reference_into_user


def _plane(array_zyx: np.ndarray, orientation: str, index_xyz: np.ndarray) -> np.ndarray:
    x, y, z = np.rint(index_xyz).astype(int)
    x = int(np.clip(x, 0, array_zyx.shape[2] - 1))
    y = int(np.clip(y, 0, array_zyx.shape[1] - 1))
    z = int(np.clip(z, 0, array_zyx.shape[0] - 1))
    if orientation == "Axial":
        return array_zyx[z, :, :]
    if orientation == "Coronal":
        return np.flipud(array_zyx[:, y, :])
    if orientation == "Sagittal":
        return np.flipud(array_zyx[:, :, x])
    raise ValueError(f"Unsupported orientation: {orientation}")


def _plane_spacing(orientation: str, spacing_xyz: Iterable[float]) -> tuple[float, float]:
    sx, sy, sz = (float(value) for value in spacing_xyz)
    if orientation == "Axial":
        return sx, sy
    if orientation == "Coronal":
        return sx, sz
    if orientation == "Sagittal":
        return sy, sz
    raise ValueError(f"Unsupported orientation: {orientation}")


def _window(array: np.ndarray) -> tuple[float, float]:
    finite = np.asarray(array[np.isfinite(array)], dtype=np.float64)
    if finite.size == 0:
        return 0.0, 1.0
    low, high = np.percentile(finite, [1.0, 99.5])
    if high <= low:
        low, high = float(finite.min()), float(finite.max())
    return float(low), float(high if high > low else low + 1.0)


def _write_aspect_correct_png(rgb: np.ndarray, spacing_xy: tuple[float, float], path: Path) -> None:
    image = sitk.GetImageFromArray(np.ascontiguousarray(rgb), isVector=True)
    image.SetSpacing(spacing_xy)
    isotropic = min(spacing_xy)
    size = image.GetSize()
    output_size = tuple(
        max(1, int(round((size[axis] - 1) * spacing_xy[axis] / isotropic)) + 1)
        for axis in range(2)
    )
    resized = sitk.Resample(
        image,
        output_size,
        sitk.Transform(2, sitk.sitkIdentity),
        sitk.sitkLinear,
        image.GetOrigin(),
        (isotropic, isotropic),
        image.GetDirection(),
        0,
        sitk.sitkVectorUInt8,
    )
    write_image(resized, path)


def write_overlay_triplet(
    base_image: sitk.Image,
    overlay_image: sitk.Image,
    center_lps: Iterable[float],
    output_directory: str | Path,
    prefix: str,
) -> list[Path]:
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    base = sitk.DICOMOrient(base_image, "LPS")
    overlay = sitk.DICOMOrient(overlay_image, "LPS")
    if overlay.GetSize() != base.GetSize():
        raise ValueError("QC overlay and Target CT must have identical geometry.")
    base_array = sitk.GetArrayViewFromImage(base)
    overlay_array = sitk.GetArrayViewFromImage(overlay)
    base_window = _window(base_array)
    overlay_window = _window(overlay_array)
    center_index = np.asarray(
        base.TransformPhysicalPointToContinuousIndex(tuple(float(value) for value in center_lps))
    )
    paths = []
    for orientation in ("Axial", "Coronal", "Sagittal"):
        base_gray = normalize_to_uint8(_plane(base_array, orientation, center_index), *base_window)
        overlay_gray = normalize_to_uint8(_plane(overlay_array, orientation, center_index), *overlay_window)
        rgb = np.zeros((*base_gray.shape, 3), dtype=np.uint8)
        rgb[..., 0] = overlay_gray
        rgb[..., 1] = base_gray
        rgb[..., 2] = overlay_gray
        path = output / f"{prefix}_{orientation}.png"
        _write_aspect_correct_png(rgb, _plane_spacing(orientation, base.GetSpacing()), path)
        paths.append(path)
    return paths


def write_multi_reference_qc_images(
    *,
    target_image: sitk.Image,
    atlas_in_target: sitk.Image,
    reference_images: Mapping[str, sitk.Image],
    registration_matrices_lps: Mapping[str, np.ndarray],
    center_lps: Iterable[float],
    output_directory: str | Path,
) -> list[Path]:
    paths = write_overlay_triplet(
        target_image,
        atlas_in_target,
        center_lps,
        output_directory,
        "AtlasConsensus_Overlay",
    )
    for reference_id in sorted(reference_images):
        warped = resample_reference_into_user(
            reference_images[reference_id],
            target_image,
            registration_matrices_lps[reference_id],
        )
        paths.extend(
            write_overlay_triplet(
                target_image,
                warped,
                center_lps,
                output_directory,
                f"{reference_id}_Overlay",
            )
        )
    return paths
