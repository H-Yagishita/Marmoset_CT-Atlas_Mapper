from __future__ import annotations

import gc
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import SimpleITK as sitk

from .displacement_consensus import (
    GridGeometryRAS,
    UncertaintyFields,
    calculate_uncertainty,
    create_target_ras_grid,
    displacement_transform,
    equal_weight_consensus,
    sample_forward_transform,
)
from .image_resampling import resample_atlas_to_target, resample_target_to_atlas
from .imaging import read_color_table, resample_reference_into_user, sample_label
from .io_manifest import scalar_image_summary, sha256_file, write_csv, write_json, write_transform_checked
from .landmark_registration import RegistrationResult, register_landmarks
from .landmark_validation import LandmarkSubset, select_common_landmarks
from .landmarks import load_slicer_markups, write_slicer_markups
from .reference_library import ReferenceEntry, ReferenceLibrary
from .qc_images import write_multi_reference_qc_images, write_overlay_triplet
from .robust_inverse import InverseQCReport, RobustInverseResult, generate_robust_inverse
from .transform_composition import compose_target_to_atlas, transform_points
from .transform_qc import TransformQCReport, evaluate_forward_fields, sample_target_points_lps


ProgressCallback = Callable[[str], None]


@dataclass(frozen=True)
class ReferenceRoute:
    reference: ReferenceEntry
    registration: RegistrationResult
    displacement_field: sitk.Image


@dataclass(frozen=True)
class MultiReferenceResult:
    target_ct_path: Path
    registration_type: str
    method: str
    landmark_subset: LandmarkSubset
    grid: GridGeometryRAS
    routes: tuple[ReferenceRoute, ...]
    consensus_field: sitk.Image
    consensus_transform: sitk.DisplacementFieldTransform
    uncertainty: UncertaintyFields
    qc: TransformQCReport
    inverse: RobustInverseResult | None
    inverse_qc: InverseQCReport
    atlas_reference_in_target: sitk.Image
    output_directory: Path


class TransformQCError(RuntimeError):
    def __init__(self, report: TransformQCReport) -> None:
        super().__init__(
            "Forward consensus transform did not meet QC criteria: "
            f"consensus P95={report.consensus_approximation.p95_mm:.6f} mm."
        )
        self.report = report


def _notify(callback: ProgressCallback | None, message: str) -> None:
    if callback is not None:
        callback(message)


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")


def _write_displacement_field(path: Path, field: sitk.Image, field_type: str = "modeling") -> None:
    image = sitk.Image(field)
    image.SetMetaData("intent_code", "1006")
    image.SetMetaData("displacement field type", field_type)
    image.SetMetaData("measurement frame", "(1,0,0) (0,1,0) (0,0,1)")
    sitk.WriteImage(image, str(path), True)


def _save_outputs(
    result: MultiReferenceResult,
    library: ReferenceLibrary,
    target_points: dict[str, np.ndarray],
    qc_points_lps: np.ndarray,
    progress: ProgressCallback | None,
    registration_type: str,
) -> None:
    output = result.output_directory
    is_k04 = len(result.routes) == 4
    transform_stem = (
        "Target_CT_to_BMA_MultiRef_K04"
        if is_k04
        else "Target_CT_to_BMA_General_J0476M"
    )
    single_dir = output / "SingleReference"
    uncertainty_dir = output / "Uncertainty"
    qc_dir = output / "QC"
    qc_volume_dir = qc_dir / "Volumes"
    atlas_target_dir = output / "AtlasLayers_in_TargetCT"
    mapped_points_dir = output / "MappedMarkups"
    inverse_dir = output / "Inverse"
    for directory in (
        output, single_dir, uncertainty_dir, qc_dir, qc_volume_dir,
        atlas_target_dir, mapped_points_dir, inverse_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    target_image = sitk.ReadImage(str(result.target_ct_path))

    _notify(progress, f"Saving {len(result.routes)} complete forward route transform(s).")
    reload_errors: dict[str, float] = {}
    for route in result.routes:
        path = single_dir / f"Target_CT_to_BMA_via_{route.reference.reference_id}_Forward.h5"
        reload_errors[route.reference.reference_id] = write_transform_checked(
            path,
            displacement_transform(route.displacement_field),
            qc_points_lps,
        )

    consensus_h5 = output / f"{transform_stem}_Forward.h5"
    consensus_reload_error = write_transform_checked(
        consensus_h5,
        result.consensus_transform,
        qc_points_lps,
    )
    _write_displacement_field(
        output / f"{transform_stem}_Displacement.nrrd",
        result.consensus_field,
    )
    uncertainty_images = {
        "RMSFromConsensus": result.uncertainty.rms_from_consensus,
        "MaximumFromConsensus": result.uncertainty.maximum_from_consensus,
        "MaximumPairwise": result.uncertainty.maximum_pairwise,
    }
    uncertainty_paths = {
        "RMSFromConsensus": uncertainty_dir / "Uncertainty_RMS.nrrd",
        "MaximumFromConsensus": uncertainty_dir / "Uncertainty_Maximum.nrrd",
        "MaximumPairwise": uncertainty_dir / "Uncertainty_MaxPairwise.nrrd",
    }
    for name, image in uncertainty_images.items():
        sitk.WriteImage(image, str(uncertainty_paths[name]), True)

    _notify(progress, "Saving every configured Atlas layer in Target CT geometry (automatic 3B outputs).")
    atlas_layer_paths: dict[str, Path] = {}
    for layer in library.atlas_layers:
        layer_image = sitk.ReadImage(str(layer.path))
        mapped_layer = resample_atlas_to_target(
            layer_image,
            target_image,
            result.consensus_transform,
            layer.interpolation,
        )
        layer_path = atlas_target_dir / f"{_safe_name(layer.name)}_in_TargetCT.nii.gz"
        sitk.WriteImage(mapped_layer, str(layer_path), True)
        atlas_layer_paths[layer.name] = layer_path
        del layer_image, mapped_layer
        gc.collect()

    inverse_paths: dict[str, Path] = {}
    target_in_atlas_path: Path | None = None
    if result.inverse is not None:
        _notify(progress, "Inverse QC passed; saving robust inverse and automatic 3A Target CT output.")
        inverse_h5 = inverse_dir / f"BMA_to_Target_CT_{'MultiRef_K04' if is_k04 else 'General_J0476M'}_Inverse.h5"
        atlas_reference = sitk.ReadImage(str(library.atlas_reference))
        atlas_qc_points = sample_target_points_lps(
            atlas_reference,
            library.consensus.qc_sample_count,
            library.consensus.random_seed,
        )
        reload_errors["PrimaryInverse"] = write_transform_checked(
            inverse_h5,
            result.inverse.inverse_transform,
            atlas_qc_points,
        )
        inverse_field_path = inverse_dir / f"BMA_to_Target_CT_{'MultiRef_K04' if is_k04 else 'General_J0476M'}_InverseDisplacement.nrrd"
        convergence_grid_path = inverse_dir / "Inverse_ConvergenceMask_Grid.nrrd"
        convergence_atlas_path = inverse_dir / "Inverse_ConvergenceMask_in_BMA2.0.nii.gz"
        target_in_atlas_path = output / "TargetCT_in_BMA2.0.nii.gz"
        _write_displacement_field(inverse_field_path, result.inverse.inverse_field)
        sitk.WriteImage(result.inverse.convergence_mask, str(convergence_grid_path), True)
        target_in_atlas, native_mask = resample_target_to_atlas(
            target_image,
            atlas_reference,
            result.inverse.inverse_transform,
            result.inverse.convergence_mask,
        )
        sitk.WriteImage(native_mask, str(convergence_atlas_path), True)
        sitk.WriteImage(target_in_atlas, str(target_in_atlas_path), True)
        inverse_paths = {
            "InverseTransform": inverse_h5,
            "InverseDisplacement": inverse_field_path,
            "ConvergenceMaskGrid": convergence_grid_path,
            "ConvergenceMaskAtlas": convergence_atlas_path,
        }
        del atlas_reference, target_in_atlas, native_mask
        gc.collect()
    else:
        _notify(progress, "WARNING: automatic 3A output skipped because inverse QC did not pass.")

    _notify(progress, "Mapping registration landmarks to BMA 2.0 (automatic 3C output).")
    mapped_landmarks = {
        label: np.asarray(result.consensus_transform.TransformPoint(tuple(target_points[label])), dtype=float)
        for label in result.landmark_subset.labels
    }
    mapped_markup_path = mapped_points_dir / "RegistrationLandmarks_in_BMA2.0.mrk.json"
    mapped_csv_path = mapped_points_dir / "RegistrationLandmarks_in_BMA2.0.csv"
    write_slicer_markups(mapped_markup_path, mapped_landmarks, name="BMA2_RegistrationLandmarks")
    label_image = sitk.ReadImage(str(library.atlas_label_map))
    region_names = read_color_table(library.atlas_color_table)
    mapped_rows = []
    for label, point in mapped_landmarks.items():
        region_value = sample_label(label_image, point)
        mapped_rows.append(
            {
                "Label": label,
                "L_mm": float(point[0]),
                "P_mm": float(point[1]),
                "S_mm": float(point[2]),
                "RegionValue": region_value,
                "RegionName": region_names.get(region_value, "Outside atlas"),
            }
        )
    write_csv(
        mapped_csv_path,
        mapped_rows,
        ["Label", "L_mm", "P_mm", "S_mm", "RegionValue", "RegionName"],
    )
    del label_image

    fre_rows = []
    residual_rows = []
    for route in result.routes:
        registration = route.registration
        fre_rows.append(
            {
                "ReferenceID": route.reference.reference_id,
                "Method": registration.method,
                "LandmarkCount": len(registration.labels),
                "LandmarkLabels": ";".join(registration.labels),
                "FRE_RMS_mm": registration.rms_mm,
                "MeanResidual_mm": registration.mean_mm,
                "MedianResidual_mm": registration.median_mm,
                "MaximumResidual_mm": registration.maximum_mm,
                "UniformScale": registration.uniform_scale,
            }
        )
        for label, distance, vector in zip(
            registration.labels,
            registration.residual_distances,
            registration.residual_vectors,
        ):
            residual_rows.append(
                {
                    "ReferenceID": route.reference.reference_id,
                    "Label": label,
                    "Residual_mm": float(distance),
                    "dL_mm": float(vector[0]),
                    "dP_mm": float(vector[1]),
                    "dS_mm": float(vector[2]),
                }
            )
    write_csv(
        qc_dir / "Landmark_FRE.csv",
        fre_rows,
        [
            "ReferenceID", "Method", "LandmarkCount", "LandmarkLabels", "FRE_RMS_mm",
            "MeanResidual_mm", "MedianResidual_mm", "MaximumResidual_mm", "UniformScale",
        ],
    )
    write_csv(
        qc_dir / "Landmark_Residuals.csv",
        residual_rows,
        ["ReferenceID", "Label", "Residual_mm", "dL_mm", "dP_mm", "dS_mm"],
    )

    qc_rows = []
    for reference_id, stats in result.qc.component_approximation.items():
        qc_rows.append(
            {
                "Check": "ComponentRouteSamplingApproximation",
                "ReferenceID": reference_id,
                "Mean_mm": stats.mean_mm,
                "P95_mm": stats.p95_mm,
                "Maximum_mm": stats.maximum_mm,
                "ThresholdP95_mm": result.qc.component_threshold_mm,
                "Passed": stats.p95_mm < result.qc.component_threshold_mm,
            }
        )
    consensus_stats = result.qc.consensus_approximation
    qc_rows.append(
        {
            "Check": "ConsensusFieldApproximation",
            "ReferenceID": "K04" if is_k04 else "J0476M-General",
            "Mean_mm": consensus_stats.mean_mm,
            "P95_mm": consensus_stats.p95_mm,
            "Maximum_mm": consensus_stats.maximum_mm,
            "ThresholdP95_mm": result.qc.consensus_threshold_mm,
            "Passed": consensus_stats.p95_mm < result.qc.consensus_threshold_mm,
        }
    )
    write_csv(
        qc_dir / "Transform_QC.csv",
        qc_rows,
        ["Check", "ReferenceID", "Mean_mm", "P95_mm", "Maximum_mm", "ThresholdP95_mm", "Passed"],
    )
    inverse_qc = result.inverse_qc
    write_csv(
        qc_dir / "Inverse_QC.csv",
        [{
            "RoundTripMean_mm": inverse_qc.roundtrip.mean_mm,
            "RoundTripP95_mm": inverse_qc.roundtrip.p95_mm,
            "RoundTripMaximum_mm": inverse_qc.roundtrip.maximum_mm,
            "ThresholdP95_mm": inverse_qc.threshold_mm,
            "TargetSampleConverged": inverse_qc.converged_target_samples,
            "TargetSampleCount": inverse_qc.target_sample_count,
            "MinimumRoundTripSampleCount": inverse_qc.minimum_roundtrip_sample_count,
            "TargetSampleFraction": inverse_qc.target_sample_fraction,
            "AtlasCoverageFraction": inverse_qc.atlas_coverage_fraction,
            "InverseGenerated": result.inverse is not None,
            "Passed": inverse_qc.passed,
        }],
        [
            "RoundTripMean_mm", "RoundTripP95_mm", "RoundTripMaximum_mm", "ThresholdP95_mm",
            "TargetSampleConverged", "TargetSampleCount", "MinimumRoundTripSampleCount", "TargetSampleFraction",
            "AtlasCoverageFraction", "InverseGenerated", "Passed",
        ],
    )

    uncertainty_rows = []
    for name, image in uncertainty_images.items():
        uncertainty_rows.append({"Metric": name, **scalar_image_summary(image)})
    write_csv(
        uncertainty_dir / "Uncertainty_Summary.csv",
        uncertainty_rows,
        ["Metric", "Mean_mm", "Median_mm", "P95_mm", "Maximum_mm"],
    )

    _notify(progress, "Saving Atlas and route QC overlay images.")
    center_lps = np.mean(
        np.vstack([target_points[label] for label in result.landmark_subset.labels]),
        axis=0,
    )
    qc_image_paths = write_multi_reference_qc_images(
        target_image=target_image,
        atlas_in_target=result.atlas_reference_in_target,
        reference_images={
            route.reference.reference_id: sitk.ReadImage(str(route.reference.ct_path))
            for route in result.routes
        },
        registration_matrices_lps={
            route.reference.reference_id: route.registration.matrix_lps
            for route in result.routes
        },
        center_lps=center_lps,
        output_directory=qc_dir,
    )
    if target_in_atlas_path is not None:
        atlas_reference = sitk.ReadImage(str(library.atlas_reference))
        target_in_atlas = sitk.ReadImage(str(target_in_atlas_path))
        qc_image_paths.extend(
            write_overlay_triplet(
                atlas_reference,
                target_in_atlas,
                (0.0, 0.0, 0.0),
                qc_dir,
                "TargetCT_in_Atlas_QC",
            )
        )
        del atlas_reference, target_in_atlas
    _notify(progress, "Saving QC viewer volumes for reload without registration recomputation.")
    target_qc_path = qc_volume_dir / "TargetCT.nii.gz"
    atlas_qc_path = qc_volume_dir / "AtlasConsensus_in_TargetCT.nii.gz"
    sitk.WriteImage(target_image, str(target_qc_path), True)
    sitk.WriteImage(result.atlas_reference_in_target, str(atlas_qc_path), True)
    warped_reference_paths: dict[str, Path] = {}
    for route in result.routes:
        reference_image = sitk.ReadImage(str(route.reference.ct_path))
        warped_reference = resample_reference_into_user(
            reference_image,
            target_image,
            route.registration.matrix_lps,
        )
        path = qc_volume_dir / f"{route.reference.reference_id}_in_TargetCT.nii.gz"
        sitk.WriteImage(warped_reference, str(path), True)
        warped_reference_paths[route.reference.reference_id] = path
        del reference_image, warped_reference
        gc.collect()

    manifest_row = {
        "CreatedUTC": datetime.now(timezone.utc).isoformat(),
        "LibraryID": library.library_id,
        "LibrarySchemaVersion": library.schema_version,
        "TargetCT": str(result.target_ct_path.resolve()),
        "Method": result.method,
        "RegistrationType": result.registration_type,
        "ReferenceCount": len(result.routes),
        "References": ";".join(route.reference.reference_id for route in result.routes),
        "ConsensusMethod": library.consensus.method if is_k04 else "single_reference_BRAINSFit_route",
        "LandmarkCount": len(result.landmark_subset.labels),
        "LandmarkLabels": ";".join(result.landmark_subset.labels),
        "GridCoordinateSystem": "RAS axis-aligned (stored in ITK/LPS metadata)",
        "GridOriginRAS": ";".join(map(str, result.grid.origin_ras)),
        "GridSpacing_mm": ";".join(map(str, result.grid.spacing_mm)),
        "GridSize": ";".join(map(str, result.grid.size)),
        "ComponentApproximationP95Maximum_mm": max(
            item.p95_mm for item in result.qc.component_approximation.values()
        ),
        "ConsensusApproximationP95_mm": result.qc.consensus_approximation.p95_mm,
        "QCPassed": result.qc.passed,
        "InverseGenerated": result.inverse is not None,
        "InverseMethod": library.inverse.method,
        "InverseRoundTripP95_mm": result.inverse_qc.roundtrip.p95_mm,
        "InverseAtlasCoverageFraction": result.inverse_qc.atlas_coverage_fraction,
        "InverseQCPassed": result.inverse_qc.passed,
        "ConsensusForwardTransform": str(consensus_h5.resolve()),
        "ForwardTransform": str(consensus_h5.relative_to(output)),
        "QCImageCount": len(qc_image_paths),
    }
    write_csv(output / "Run_Manifest.csv", [manifest_row], manifest_row.keys())
    manifest_json = {
        **manifest_row,
        "ReferenceLibraryManifest": str(library.manifest_path),
        "ReferenceLibraryManifestSHA256": sha256_file(library.manifest_path),
        "TargetLandmarks": {label: np.asarray(target_points[label]).tolist() for label in result.landmark_subset.labels},
        "MissingLandmarksByDataset": {
            key: list(value) for key, value in result.landmark_subset.missing_by_dataset.items()
        },
        "Warnings": list(result.landmark_subset.warnings),
        "SavedReloadedMaximumError_mm": {
            **reload_errors,
            "PrimaryForward": consensus_reload_error,
        },
        "UncertaintyFiles": {key: str(value.resolve()) for key, value in uncertainty_paths.items()},
        "AutomaticOutputs": {
            "TargetCTInAtlas": str(target_in_atlas_path.relative_to(output)) if target_in_atlas_path else None,
            "AtlasLayersInTargetCT": {
                key: str(value.relative_to(output)) for key, value in atlas_layer_paths.items()
            },
            "RegistrationLandmarksInAtlas": str(mapped_markup_path.relative_to(output)),
            "RegistrationLandmarkTable": str(mapped_csv_path.relative_to(output)),
        },
        "InverseFiles": {key: str(value.relative_to(output)) for key, value in inverse_paths.items()},
        "QCViewer": {
            "TargetCT": str(target_qc_path.relative_to(output)),
            "AtlasConsensus": str(atlas_qc_path.relative_to(output)),
            "WarpedReferences": {
                key: str(value.relative_to(output)) for key, value in warped_reference_paths.items()
            },
            "CenterLPS": center_lps.tolist(),
        },
        "ForwardOnly": result.inverse is None,
        "QCImages": [str(path.resolve()) for path in qc_image_paths],
        "InversePolicy": (
            "Explicit Atlas-grid inverse saved only after convergence-mask and round-trip QC."
            if result.inverse is not None
            else "Inverse candidate failed QC; no inverse transform or 3A image was saved."
        ),
    }
    write_json(output / "Run_Manifest.json", manifest_json)


def run_multi_reference_registration(
    *,
    target_ct_path: str | Path,
    target_landmarks: dict[str, np.ndarray],
    requested_labels: Iterable[str],
    method: str,
    library: ReferenceLibrary,
    output_directory: str | Path,
    progress: ProgressCallback | None = None,
    registration_type: str = "Landmark (Skull-base)",
) -> MultiReferenceResult:
    target_path = Path(target_ct_path)
    output = Path(output_directory)
    _notify(progress, f"Loading Target CT: {target_path}")
    target_image = sitk.ReadImage(str(target_path))
    if target_image.GetDimension() != 3:
        raise ValueError("Target CT must be a 3D image.")

    references = tuple(sorted(library.references, key=lambda item: item.reference_id))
    reference_points = {
        reference.reference_id: load_slicer_markups(reference.landmarks_path)
        for reference in references
    }
    subset = select_common_landmarks(
        target_landmarks,
        reference_points,
        requested_labels,
        allowed_labels=library.allowed_labels,
        minimum_count=library.minimum_landmark_count,
        recommended_count=library.recommended_landmark_count,
    )
    _notify(progress, f"Using {len(subset.labels)} common landmarks: {', '.join(subset.labels)}")
    for warning in subset.warnings:
        _notify(progress, f"WARNING: {warning}")

    grid = create_target_ras_grid(
        target_image,
        library.consensus.grid_spacing_mm,
        library.consensus.grid_padding_mm,
    )
    _notify(
        progress,
        f"Created axis-aligned RAS grid: size={grid.size}, spacing={grid.spacing_mm}, origin={grid.origin_ras}",
    )
    qc_points = sample_target_points_lps(
        target_image,
        library.consensus.qc_sample_count,
        library.consensus.random_seed,
    )
    routes = []
    component_fields: dict[str, sitk.Image] = {}
    exact_outputs: dict[str, np.ndarray] = {}
    for index, reference in enumerate(references, start=1):
        _notify(progress, f"[{index}/4] Registering Target CT to {reference.reference_id} ({method}).")
        registration = register_landmarks(
            target_landmarks,
            reference_points[reference.reference_id],
            subset.labels,
            method=method,
        )
        exact_route = compose_target_to_atlas(
            registration.matrix_lps,
            reference.ct_to_atlas_forward_path,
        )
        exact_outputs[reference.reference_id] = transform_points(exact_route, qc_points)
        field = sample_forward_transform(exact_route, grid)
        component_fields[reference.reference_id] = field
        routes.append(ReferenceRoute(reference, registration, field))
        _notify(
            progress,
            f"[{index}/4] {reference.reference_id}: FRE RMS={registration.rms_mm:.3f} mm; route sampled.",
        )
        del exact_route
        gc.collect()

    _notify(progress, "Calculating equal-weight arithmetic mean of four forward displacement fields.")
    consensus_field = equal_weight_consensus(component_fields)
    consensus_transform = displacement_transform(consensus_field)
    uncertainty = calculate_uncertainty(component_fields, consensus_field)
    qc = evaluate_forward_fields(
        target_image=target_image,
        grid=grid,
        exact_outputs_by_reference=exact_outputs,
        component_fields=component_fields,
        consensus_field=consensus_field,
        qc_points_lps=qc_points,
        component_threshold_mm=library.qc.component_approximation_p95_max_mm,
        consensus_threshold_mm=library.qc.consensus_approximation_p95_max_mm,
    )
    _notify(
        progress,
        f"Consensus approximation P95={qc.consensus_approximation.p95_mm:.6f} mm; "
        f"QC={'PASS' if qc.passed else 'FAIL'}.",
    )
    if not qc.passed:
        raise TransformQCError(qc)

    atlas_reference = sitk.ReadImage(str(library.atlas_reference))
    _notify(progress, "Generating explicit inverse field on the Atlas grid (global-affine initialized Newton solver).")
    inverse_candidate = generate_robust_inverse(
        forward_field=consensus_field,
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
    inverse_qc = inverse_candidate.qc
    if inverse_qc.passed:
        inverse_result: RobustInverseResult | None = inverse_candidate
        _notify(
            progress,
            f"Inverse QC PASS: round-trip P95={inverse_qc.roundtrip.p95_mm:.4f} mm; "
            f"valid samples={inverse_qc.converged_target_samples}/{inverse_qc.target_sample_count}; "
            f"Atlas coverage={inverse_qc.atlas_coverage_fraction:.2%} (informational only).",
        )
    else:
        inverse_result = None
        _notify(
            progress,
            f"WARNING: inverse QC FAIL (round-trip P95={inverse_qc.roundtrip.p95_mm:.4f} mm; "
            f"valid samples={inverse_qc.converged_target_samples}, required="
            f"{inverse_qc.minimum_roundtrip_sample_count}); inverse/3A will not be saved.",
        )
    atlas_in_target = resample_atlas_to_target(
        atlas_reference,
        target_image,
        consensus_transform,
        "linear",
    )
    result = MultiReferenceResult(
        target_ct_path=target_path,
        registration_type=registration_type,
        method=method.strip().capitalize(),
        landmark_subset=subset,
        grid=grid,
        routes=tuple(routes),
        consensus_field=consensus_field,
        consensus_transform=consensus_transform,
        uncertainty=uncertainty,
        qc=qc,
        inverse=inverse_result,
        inverse_qc=inverse_qc,
        atlas_reference_in_target=atlas_in_target,
        output_directory=output,
    )
    _save_outputs(result, library, target_landmarks, qc_points, progress, registration_type)
    _notify(
        progress,
        f"K04 output bundle saved: {output} "
        f"(3A={'saved' if result.inverse is not None else 'skipped by inverse QC'}, 3B=all layers, 3C=landmarks).",
    )
    return result
