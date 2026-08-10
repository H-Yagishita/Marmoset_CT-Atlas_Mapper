from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import SimpleITK as sitk

from .transform_composition import transform_points
from .transform_io import read_transform


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: str | Path, rows: Sequence[Mapping[str, object]], fieldnames: Iterable[str]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = list(fieldnames)
    with destination.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: str | Path, payload: Mapping[str, object]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_transform_checked(
    path: str | Path,
    transform: sitk.Transform,
    check_points_lps: np.ndarray,
    tolerance_mm: float = 1e-8,
) -> float:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    expected = transform_points(transform, check_points_lps)
    sitk.WriteTransform(transform, str(destination))
    reloaded = read_transform(destination)
    actual = transform_points(reloaded, check_points_lps)
    maximum_error = float(np.max(np.linalg.norm(actual - expected, axis=1)))
    if not np.isfinite(maximum_error) or maximum_error > tolerance_mm:
        raise RuntimeError(
            f"Saved/reloaded transform changed coordinates by {maximum_error:.9f} mm: {destination}"
        )
    return maximum_error


def scalar_image_summary(image: sitk.Image) -> dict[str, float]:
    values = np.asarray(sitk.GetArrayViewFromImage(image), dtype=np.float64)
    finite = values[np.isfinite(values)]
    if finite.size != values.size or finite.size == 0:
        raise ValueError("Uncertainty image contains undefined/non-finite values.")
    return {
        "Mean_mm": float(np.mean(finite)),
        "Median_mm": float(np.median(finite)),
        "P95_mm": float(np.percentile(finite, 95)),
        "Maximum_mm": float(np.max(finite)),
    }
