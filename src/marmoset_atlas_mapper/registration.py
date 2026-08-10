from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

import numpy as np


@dataclass(frozen=True)
class RegistrationResult:
    method: str
    labels: tuple[str, ...]
    matrix_lps: np.ndarray
    transformed_moving: np.ndarray
    residual_vectors: np.ndarray
    residual_distances: np.ndarray

    @property
    def rms_mm(self) -> float:
        return float(np.sqrt(np.mean(self.residual_distances**2)))

    @property
    def mean_mm(self) -> float:
        return float(np.mean(self.residual_distances))

    @property
    def median_mm(self) -> float:
        return float(np.median(self.residual_distances))

    @property
    def maximum_mm(self) -> float:
        return float(np.max(self.residual_distances))

    @property
    def uniform_scale(self) -> float:
        return float(np.cbrt(np.linalg.det(self.matrix_lps[:3, :3])))


def apply_matrix(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=float)
    points = np.asarray(points, dtype=float)
    if matrix.shape != (4, 4):
        raise ValueError("Transform matrix must be 4x4.")
    if points.ndim == 1:
        points = points.reshape(1, 3)
    homogeneous = np.column_stack([points, np.ones(len(points), dtype=float)])
    return (matrix @ homogeneous.T).T[:, :3]


def rigid_matrix(moving: np.ndarray, fixed: np.ndarray) -> np.ndarray:
    """Return the least-squares proper rigid transform moving -> fixed."""
    moving = np.asarray(moving, dtype=float)
    fixed = np.asarray(fixed, dtype=float)
    if moving.shape != fixed.shape or moving.ndim != 2 or moving.shape[1] != 3:
        raise ValueError("Moving and fixed landmarks must be matching Nx3 arrays.")
    if len(moving) < 3:
        raise ValueError("At least three landmarks are required.")
    if not np.all(np.isfinite(moving)) or not np.all(np.isfinite(fixed)):
        raise ValueError("Landmark coordinates must be finite.")

    moving_center = moving.mean(axis=0)
    fixed_center = fixed.mean(axis=0)
    moving_centered = moving - moving_center
    fixed_centered = fixed - fixed_center
    if np.linalg.matrix_rank(moving_centered) < 2:
        raise ValueError("Moving landmarks are collinear or coincident.")
    if np.linalg.matrix_rank(fixed_centered) < 2:
        raise ValueError("Reference landmarks are collinear or coincident.")

    covariance = moving_centered.T @ fixed_centered
    u, _, vt = np.linalg.svd(covariance)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1, :] *= -1.0
        rotation = vt.T @ u.T
    translation = fixed_center - rotation @ moving_center

    matrix = np.eye(4, dtype=float)
    matrix[:3, :3] = rotation
    matrix[:3, 3] = translation
    return matrix


def similarity_matrix(moving: np.ndarray, fixed: np.ndarray) -> np.ndarray:
    """Return the least-squares proper similarity transform moving -> fixed."""
    moving = np.asarray(moving, dtype=float)
    fixed = np.asarray(fixed, dtype=float)
    if moving.shape != fixed.shape or moving.ndim != 2 or moving.shape[1] != 3:
        raise ValueError("Moving and fixed landmarks must be matching Nx3 arrays.")
    if len(moving) < 3:
        raise ValueError("At least three landmarks are required.")
    if not np.all(np.isfinite(moving)) or not np.all(np.isfinite(fixed)):
        raise ValueError("Landmark coordinates must be finite.")

    moving_center = moving.mean(axis=0)
    fixed_center = fixed.mean(axis=0)
    moving_centered = moving - moving_center
    fixed_centered = fixed - fixed_center
    if np.linalg.matrix_rank(moving_centered) < 2:
        raise ValueError("Moving landmarks are collinear or coincident.")
    if np.linalg.matrix_rank(fixed_centered) < 2:
        raise ValueError("Reference landmarks are collinear or coincident.")

    covariance = moving_centered.T @ fixed_centered / len(moving)
    u, singular_values, vt = np.linalg.svd(covariance)
    signs = np.ones(3, dtype=float)
    if np.linalg.det(vt.T @ u.T) < 0.0:
        signs[-1] = -1.0
    rotation = vt.T @ np.diag(signs) @ u.T
    moving_variance = float(np.mean(np.sum(moving_centered**2, axis=1)))
    if moving_variance <= np.finfo(float).eps:
        raise ValueError("Moving landmarks are coincident.")
    scale = float(np.dot(singular_values, signs) / moving_variance)
    if not np.isfinite(scale) or scale <= 0.0:
        raise ValueError("Similarity scale is invalid for the selected landmarks.")
    translation = fixed_center - scale * rotation @ moving_center

    matrix = np.eye(4, dtype=float)
    matrix[:3, :3] = scale * rotation
    matrix[:3, 3] = translation
    return matrix


def register_landmarks(
    moving_by_label: Mapping[str, Iterable[float]],
    fixed_by_label: Mapping[str, Iterable[float]],
    labels: Sequence[str],
    method: str = "Rigid",
) -> RegistrationResult:
    missing_moving = [label for label in labels if label not in moving_by_label]
    missing_fixed = [label for label in labels if label not in fixed_by_label]
    if missing_moving:
        raise ValueError(f"Missing user landmarks: {', '.join(missing_moving)}")
    if missing_fixed:
        raise ValueError(f"Missing reference landmarks: {', '.join(missing_fixed)}")

    moving = np.vstack([np.asarray(moving_by_label[label], dtype=float) for label in labels])
    fixed = np.vstack([np.asarray(fixed_by_label[label], dtype=float) for label in labels])
    normalized_method = method.strip().capitalize()
    if normalized_method == "Rigid":
        matrix = rigid_matrix(moving, fixed)
    elif normalized_method == "Similarity":
        matrix = similarity_matrix(moving, fixed)
    else:
        raise ValueError(f"Unsupported registration method: {method}")
    transformed = apply_matrix(matrix, moving)
    residual_vectors = transformed - fixed
    residual_distances = np.linalg.norm(residual_vectors, axis=1)
    return RegistrationResult(
        method=normalized_method,
        labels=tuple(labels),
        matrix_lps=matrix,
        transformed_moving=transformed,
        residual_vectors=residual_vectors,
        residual_distances=residual_distances,
    )
