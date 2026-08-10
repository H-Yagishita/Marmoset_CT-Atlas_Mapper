from __future__ import annotations

import gc
from pathlib import Path
from typing import Iterable

import numpy as np
import SimpleITK as sitk

from .brainsfit_registration import run_brainsfit
from .displacement_consensus import (
    calculate_uncertainty,
    create_target_ras_grid,
    displacement_transform,
    sample_forward_transform,
)
from .image_resampling import resample_atlas_to_target
from .landmark_registration import register_landmarks
from .landmark_validation import select_common_landmarks
from .landmarks import load_slicer_markups
from .multi_reference_pipeline import (
    MultiReferenceResult,
    ProgressCallback,
    ReferenceRoute,
    TransformQCError,
    _notify,
    _save_outputs,
)
from .reference_library import ReferenceLibrary
from .robust_inverse import RobustInverseResult, generate_robust_inverse
from .transform_composition import transform_points
from .transform_qc import evaluate_forward_fields, sample_target_points_lps
from .transform_io import read_transform


def run_general_registration(
    *,
    target_ct_path: str | Path,
    target_landmarks: dict[str, np.ndarray],
    requested_labels: Iterable[str],
    method: str,
    library: ReferenceLibrary,
    output_directory: str | Path,
    progress: ProgressCallback | None = None,
) -> MultiReferenceResult:
    """Landmark-rigid initialization to J0476M followed by BRAINSFit."""
    target_path = Path(target_ct_path)
    output = Path(output_directory)
    target_image = sitk.ReadImage(str(target_path))
    if target_image.GetDimension() != 3:
        raise ValueError("Target CT must be a 3D image.")
    reference = next(item for item in library.references if item.reference_id == "J0476M")
    reference_points = load_slicer_markups(reference.landmarks_path)
    subset = select_common_landmarks(
        target_landmarks,
        {reference.reference_id: reference_points},
        requested_labels,
        allowed_labels=library.allowed_labels,
        minimum_count=library.minimum_landmark_count,
        recommended_count=library.recommended_landmark_count,
    )
    _notify(progress, f"Using {len(subset.labels)} J0476M common landmarks: {', '.join(subset.labels)}")
    for warning in subset.warnings:
        _notify(progress, f"WARNING: {warning}")
    initial = register_landmarks(
        target_landmarks,
        reference_points,
        subset.labels,
        method="Rigid",
    )
    _notify(progress, f"J0476M landmark-rigid initialization: FRE RMS={initial.rms_mm:.3f} mm.")
    final_registration, brainsfit_path, runtime = run_brainsfit(
        moving_ct=target_path,
        fixed_ct=reference.ct_path,
        initial_matrix_lps=initial.matrix_lps,
        method=method,
        output_directory=output / "BRAINSFit",
        moving_landmarks=target_landmarks,
        fixed_landmarks=reference_points,
        labels=subset.labels,
        progress=progress,
    )
    _notify(
        progress,
        f"BRAINSFit {final_registration.method} completed; landmark check RMS="
        f"{final_registration.rms_mm:.3f} mm (not an optimization metric).",
    )
    target_to_reference = read_transform(brainsfit_path)
    reference_to_atlas = read_transform(reference.ct_to_atlas_forward_path)
    exact_route = sitk.CompositeTransform([reference_to_atlas, target_to_reference])
    grid = create_target_ras_grid(
        target_image,
        library.consensus.grid_spacing_mm,
        library.consensus.grid_padding_mm,
    )
    qc_points = sample_target_points_lps(
        target_image,
        library.consensus.qc_sample_count,
        library.consensus.random_seed,
    )
    field = sample_forward_transform(exact_route, grid)
    forward = displacement_transform(field)
    uncertainty = calculate_uncertainty({reference.reference_id: field}, field)
    exact_outputs = {reference.reference_id: transform_points(exact_route, qc_points)}
    qc = evaluate_forward_fields(
        target_image=target_image,
        grid=grid,
        exact_outputs_by_reference=exact_outputs,
        component_fields={reference.reference_id: field},
        consensus_field=field,
        qc_points_lps=qc_points,
        component_threshold_mm=library.qc.component_approximation_p95_max_mm,
        consensus_threshold_mm=library.qc.consensus_approximation_p95_max_mm,
    )
    if not qc.passed:
        raise TransformQCError(qc)
    atlas_reference = sitk.ReadImage(str(library.atlas_reference))
    _notify(progress, "Generating and validating explicit Atlas-grid inverse field.")
    inverse_candidate = generate_robust_inverse(
        forward_field=field,
        target_image=target_image,
        atlas_reference=atlas_reference,
        inverse_spacing_mm=library.inverse.grid_spacing_mm,
        inverse_padding_mm=library.inverse.grid_padding_mm,
        maximum_iterations=library.inverse.maximum_iterations,
        convergence_tolerance_mm=library.inverse.convergence_tolerance_mm,
        maximum_step_mm=library.inverse.maximum_step_mm,
        qc_sample_count=library.consensus.qc_sample_count,
        random_seed=library.consensus.random_seed,
        roundtrip_threshold_mm=library.qc.inverse_roundtrip_p95_max_mm,
        minimum_roundtrip_sample_count=library.inverse.minimum_roundtrip_sample_count,
    )
    inverse_result: RobustInverseResult | None = (
        inverse_candidate if inverse_candidate.qc.passed else None
    )
    if inverse_result is None:
        _notify(
            progress,
            "WARNING: inverse QC failed; inverse transform and Target CT in Atlas geometry will not be saved.",
        )
    atlas_in_target = resample_atlas_to_target(
        atlas_reference,
        target_image,
        forward,
        "linear",
    )
    result = MultiReferenceResult(
        target_ct_path=target_path,
        registration_type="General (BRAINSFit)",
        method=final_registration.method,
        landmark_subset=subset,
        grid=grid,
        routes=(ReferenceRoute(reference, final_registration, field),),
        consensus_field=field,
        consensus_transform=forward,
        uncertainty=uncertainty,
        qc=qc,
        inverse=inverse_result,
        inverse_qc=inverse_candidate.qc,
        atlas_reference_in_target=atlas_in_target,
        output_directory=output,
    )
    _save_outputs(
        result,
        library,
        target_landmarks,
        qc_points,
        progress,
        "General (BRAINSFit)",
    )
    _notify(
        progress,
        f"General registration output bundle saved: {output}; runtime={runtime.slicer_launcher.parent.name}.",
    )
    del exact_route
    gc.collect()
    return result
