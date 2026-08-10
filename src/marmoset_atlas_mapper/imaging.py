from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np
import SimpleITK as sitk

from .landmarks import write_slicer_markups
from .registration import RegistrationResult
from .transform_io import read_transform


@dataclass
class VolumeData:
    source_path: Path
    image: sitk.Image
    display_image: sitk.Image
    array_zyx: np.ndarray
    window_min: float
    window_max: float

    @classmethod
    def read(cls, path: str | Path) -> "VolumeData":
        source = Path(path)
        image = sitk.ReadImage(str(source))
        return cls.from_image(image, source)

    @classmethod
    def from_image(cls, image: sitk.Image, source_path: str | Path = "<memory>") -> "VolumeData":
        source = Path(source_path)
        if image.GetDimension() != 3:
            raise ValueError(f"Expected a 3D image, got {image.GetDimension()}D: {source}")
        display_image = sitk.DICOMOrient(image, "LPS")
        array = sitk.GetArrayViewFromImage(display_image)
        finite = np.asarray(array[np.isfinite(array)], dtype=np.float64)
        if finite.size == 0:
            low, high = 0.0, 1.0
        else:
            low, high = np.percentile(finite, [1.0, 99.5])
            if not np.isfinite(low) or not np.isfinite(high) or high <= low:
                low, high = float(finite.min()), float(finite.max())
            if high <= low:
                high = low + 1.0
        return cls(source, image, display_image, array, float(low), float(high))

    def index_to_physical(self, index_xyz: Iterable[float]) -> np.ndarray:
        return np.asarray(self.display_image.TransformContinuousIndexToPhysicalPoint(tuple(index_xyz)), dtype=float)

    def physical_to_index(self, point_lps: Iterable[float]) -> np.ndarray:
        return np.asarray(self.display_image.TransformPhysicalPointToContinuousIndex(tuple(point_lps)), dtype=float)

    def contains_index(self, index_xyz: Iterable[float]) -> bool:
        index = np.asarray(tuple(index_xyz), dtype=float)
        size = np.asarray(self.display_image.GetSize(), dtype=float)
        return bool(np.all(index >= -0.5) and np.all(index <= size - 0.5))


def normalize_to_uint8(array: np.ndarray, low: float, high: float) -> np.ndarray:
    scaled = (np.asarray(array, dtype=np.float32) - low) / max(high - low, 1e-12)
    return np.ascontiguousarray(np.clip(scaled * 255.0, 0.0, 255.0).astype(np.uint8))


def matrix_to_sitk_affine(matrix_lps: np.ndarray) -> sitk.AffineTransform:
    matrix = np.asarray(matrix_lps, dtype=float)
    if matrix.shape != (4, 4):
        raise ValueError("Expected a 4x4 matrix.")
    transform = sitk.AffineTransform(3)
    transform.SetMatrix(tuple(matrix[:3, :3].reshape(-1)))
    transform.SetTranslation(tuple(matrix[:3, 3]))
    return transform


def compose_user_to_atlas(
    user_to_reference_matrix_lps: np.ndarray,
    reference_to_atlas_point_transform_path: str | Path,
) -> sitk.CompositeTransform:
    user_to_reference = matrix_to_sitk_affine(user_to_reference_matrix_lps)
    reference_to_atlas = read_transform(reference_to_atlas_point_transform_path)
    # SimpleITK composites apply the last transform first.
    return sitk.CompositeTransform([reference_to_atlas, user_to_reference])


def compose_atlas_to_user_for_resampling(
    user_to_reference_matrix_lps: np.ndarray,
    atlas_to_reference_resampling_transform_path: str | Path,
) -> sitk.CompositeTransform:
    """Create output-Atlas -> input-User transform required by image resampling."""
    reference_to_user = matrix_to_sitk_affine(user_to_reference_matrix_lps).GetInverse()
    atlas_to_reference = read_transform(atlas_to_reference_resampling_transform_path)
    return sitk.CompositeTransform([reference_to_user, atlas_to_reference])


def resample_reference_into_user(
    reference_image: sitk.Image,
    user_image: sitk.Image,
    user_to_reference_matrix_lps: np.ndarray,
) -> sitk.Image:
    return sitk.Resample(
        reference_image,
        user_image,
        matrix_to_sitk_affine(user_to_reference_matrix_lps),
        sitk.sitkLinear,
        0.0,
        sitk.sitkFloat32,
    )


def resample_atlas_layer_into_user(
    atlas_image: sitk.Image,
    user_image: sitk.Image,
    user_to_atlas: sitk.Transform,
    interpolation: str,
) -> sitk.Image:
    if interpolation == "nearest":
        interpolator = sitk.sitkNearestNeighbor
        pixel_id = atlas_image.GetPixelID()
    elif interpolation == "linear":
        interpolator = sitk.sitkLinear
        pixel_id = sitk.sitkFloat32
    else:
        raise ValueError(f"Unsupported interpolation: {interpolation}")
    return sitk.Resample(atlas_image, user_image, user_to_atlas, interpolator, 0.0, pixel_id)


def resample_user_ct_into_atlas(
    user_image: sitk.Image,
    atlas_reference_image: sitk.Image,
    atlas_to_user: sitk.Transform,
) -> sitk.Image:
    return sitk.Resample(
        user_image,
        atlas_reference_image,
        atlas_to_user,
        sitk.sitkLinear,
        0.0,
        sitk.sitkFloat32,
    )


def read_color_table(path: str | Path) -> dict[int, str]:
    labels: dict[int, str] = {}
    with Path(path).open("r", encoding="utf-8-sig", errors="replace") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            try:
                value = int(parts[0])
            except (ValueError, IndexError):
                continue
            labels[value] = parts[1].replace("_", " ") if len(parts) > 1 else str(value)
    return labels


def sample_label(image: sitk.Image, point_lps: Iterable[float]) -> int | None:
    point = tuple(float(value) for value in point_lps)
    try:
        index = image.TransformPhysicalPointToIndex(point)
    except RuntimeError:
        return None
    size = image.GetSize()
    if any(index[axis] < 0 or index[axis] >= size[axis] for axis in range(3)):
        return None
    return int(image[index])


def map_points_to_atlas(
    points_lps: Mapping[str, Iterable[float]],
    user_to_atlas: sitk.Transform,
) -> dict[str, np.ndarray]:
    return {
        label: np.asarray(user_to_atlas.TransformPoint(tuple(float(v) for v in point)), dtype=float)
        for label, point in points_lps.items()
    }


def save_registration_outputs(
    output_directory: str | Path,
    result: RegistrationResult,
    user_landmarks_lps: Mapping[str, Iterable[float]],
    mapped_atlas_lps: Mapping[str, Iterable[float]],
    atlas_labels: Mapping[str, tuple[int | None, str]],
    *,
    user_ct_path: str | Path,
    profile_id: str,
    reference_id: str,
    reference_to_atlas_transform_path: str | Path,
    atlas_to_reference_transform_path: str | Path,
) -> None:
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    sitk.WriteTransform(
        matrix_to_sitk_affine(result.matrix_lps),
        str(output / f"UserCT_to_{reference_id}_{result.method}.tfm"),
    )
    write_slicer_markups(output / "UserCT_Landmarks.mrk.json", user_landmarks_lps)
    write_slicer_markups(output / "UserCT_Landmarks_in_BMA2.mrk.json", mapped_atlas_lps, name="Atlas")

    with (output / "Landmark_QC.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Label", "Residual_mm", "dL_mm", "dP_mm", "dS_mm"])
        for label, distance, vector in zip(result.labels, result.residual_distances, result.residual_vectors):
            writer.writerow([label, float(distance), *[float(value) for value in vector]])

    with (output / "Landmarks_in_BMA2.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["Label", "L_mm", "P_mm", "S_mm", "RegionValue", "RegionName"])
        for label, point in mapped_atlas_lps.items():
            value, name = atlas_labels.get(label, (None, "Outside atlas"))
            writer.writerow([label, *[float(v) for v in point], value, name])

    manifest = {
        "application": "Marmoset Atlas Mapper",
        "profile": profile_id,
        "reference_id": reference_id,
        "user_ct": str(Path(user_ct_path).resolve()),
        "reference_to_atlas_point_transform": str(Path(reference_to_atlas_transform_path).resolve()),
        "atlas_to_reference_resampling_transform": str(Path(atlas_to_reference_transform_path).resolve()),
        "registration_method": result.method,
        "registration_landmarks": list(result.labels),
        "registration_landmark_count": len(result.labels),
        "coordinate_system": "LPS physical coordinates in mm",
        "matrix_user_ct_to_reference_lps": result.matrix_lps.tolist(),
        "qc": {
            "rms_mm": result.rms_mm,
            "mean_mm": result.mean_mm,
            "median_mm": result.median_mm,
            "maximum_mm": result.maximum_mm,
        },
    }
    (output / "registration_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
