from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

import numpy as np


@dataclass(frozen=True)
class LandmarkSubset:
    labels: tuple[str, ...]
    missing_by_dataset: dict[str, tuple[str, ...]]
    warnings: tuple[str, ...]


def _validate_geometry(points_by_label: Mapping[str, Iterable[float]], labels: tuple[str, ...], name: str) -> None:
    points = np.vstack([np.asarray(points_by_label[label], dtype=float) for label in labels])
    if points.shape != (len(labels), 3) or not np.all(np.isfinite(points)):
        raise ValueError(f"{name} contains an undefined or non-finite landmark coordinate.")
    centered = points - points.mean(axis=0)
    singular_values = np.linalg.svd(centered, compute_uv=False)
    if singular_values[0] <= np.finfo(float).eps or singular_values[1] / singular_values[0] < 1e-6:
        raise ValueError(f"Landmarks are collinear or coincident in {name}.")


def select_common_landmarks(
    target_points: Mapping[str, Iterable[float]],
    reference_points: Mapping[str, Mapping[str, Iterable[float]]],
    requested_labels: Iterable[str],
    *,
    allowed_labels: Iterable[str],
    minimum_count: int = 3,
    recommended_count: int = 5,
) -> LandmarkSubset:
    requested = tuple(str(label).strip() for label in requested_labels)
    if not requested:
        raise ValueError("No landmark labels were requested.")
    if len(set(requested)) != len(requested):
        raise ValueError("Requested landmark labels contain duplicates.")
    allowed = set(allowed_labels)
    unsupported = [label for label in requested if label not in allowed]
    if unsupported:
        raise ValueError("Unsupported landmark labels: " + ", ".join(unsupported))

    datasets: dict[str, Mapping[str, Iterable[float]]] = {"Target CT": target_points, **reference_points}
    missing: dict[str, tuple[str, ...]] = {}
    for name, points in datasets.items():
        absent = tuple(label for label in requested if label not in points)
        if absent:
            missing[name] = absent
    common = tuple(
        label for label in requested if all(label in points for points in datasets.values())
    )
    if len(common) < minimum_count:
        raise ValueError(
            f"Only {len(common)} common landmarks are available; at least {minimum_count} are required."
        )
    for name, points in datasets.items():
        _validate_geometry(points, common, name)

    warnings = []
    if len(common) < recommended_count:
        warnings.append(
            f"Only {len(common)} landmarks are used; {recommended_count} or more are recommended."
        )
    if missing:
        warnings.append("Missing/undefined landmarks were excluded using the common subset.")
    return LandmarkSubset(common, missing, tuple(warnings))
