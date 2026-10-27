from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np
import SimpleITK as sitk

from .transform_composition import transform_points
from .transform_io import read_transform
from .native_io import write_transform


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
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                         prefix=destination.name + ".", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(json.dumps(payload, indent=2, ensure_ascii=False))
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def prepare_output_directory(path: str | Path) -> Path:
    """Never mix a new run with earlier or partially written scientific outputs."""
    output = Path(path).resolve()
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise FileExistsError(f"Use a new or empty output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    return output


def write_transform_checked(
    path: str | Path,
    transform: sitk.Transform,
    check_points_lps: np.ndarray,
    tolerance_mm: float = 1e-8,
) -> float:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    expected = transform_points(transform, check_points_lps)
    write_transform(transform, destination)
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
