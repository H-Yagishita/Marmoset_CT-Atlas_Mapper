from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import SimpleITK as sitk

from .displacement_consensus import UncertaintyFields
from .imaging import VolumeData
from .robust_inverse import InverseQCReport
from .transform_qc import ErrorStatistics


@dataclass(frozen=True)
class SavedQCSession:
    output_directory: Path
    target: VolumeData
    atlas_in_target: VolumeData
    warped_references: dict[str, VolumeData]
    result: SimpleNamespace
    center_lps: tuple[float, float, float]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _relative(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def load_saved_qc_session(directory: str | Path) -> SavedQCSession:
    root = Path(directory)
    manifest_path = root / "Run_Manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Run_Manifest.json was not found in {root}.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("ReferenceCount") not in {1, 4}:
        raise ValueError("The selected output is not a supported registration result.")

    viewer = manifest.get("QCViewer")
    if not isinstance(viewer, dict):
        raise ValueError("This result predates reloadable QC volumes and cannot be opened interactively.")
    target = VolumeData.read(_relative(root, viewer["TargetCT"]))
    atlas = VolumeData.read(_relative(root, viewer["AtlasConsensus"]))
    warped = {
        reference_id: VolumeData.read(_relative(root, path))
        for reference_id, path in viewer["WarpedReferences"].items()
    }

    component_rows = _read_csv(root / "QC" / "Transform_QC.csv")
    component_stats = {}
    consensus_stats = None
    for row in component_rows:
        stats = ErrorStatistics(float(row["Mean_mm"]), float(row["P95_mm"]), float(row["Maximum_mm"]))
        if row["Check"] == "ConsensusFieldApproximation":
            consensus_stats = stats
        else:
            component_stats[row["ReferenceID"]] = stats
    if consensus_stats is None:
        raise ValueError("Consensus QC row is missing.")
    qc = SimpleNamespace(
        passed=bool(manifest["QCPassed"]),
        consensus_approximation=consensus_stats,
        component_approximation=component_stats,
    )

    fre_by_reference = {row["ReferenceID"]: row for row in _read_csv(root / "QC" / "Landmark_FRE.csv")}
    labels = tuple(str(manifest["LandmarkLabels"]).split(";"))
    routes = []
    for reference_id in sorted(warped):
        row = fre_by_reference[reference_id]
        registration = SimpleNamespace(
            labels=labels,
            method=row["Method"],
            rms_mm=float(row["FRE_RMS_mm"]),
            mean_mm=float(row["MeanResidual_mm"]),
            maximum_mm=float(row["MaximumResidual_mm"]),
            uniform_scale=float(row["UniformScale"]),
        )
        routes.append(
            SimpleNamespace(
                reference=SimpleNamespace(reference_id=reference_id),
                registration=registration,
            )
        )

    uncertainty = UncertaintyFields(
        sitk.ReadImage(str(root / "Uncertainty" / "Uncertainty_RMS.nrrd")),
        sitk.ReadImage(str(root / "Uncertainty" / "Uncertainty_Maximum.nrrd")),
        sitk.ReadImage(str(root / "Uncertainty" / "Uncertainty_MaxPairwise.nrrd")),
    )
    inverse_rows = _read_csv(root / "QC" / "Inverse_QC.csv")
    inverse_qc = None
    if inverse_rows:
        row = inverse_rows[0]
        target_count = int(row["TargetSampleCount"])
        converged = int(row["TargetSampleConverged"])
        atlas_fraction = float(row["AtlasCoverageFraction"])
        # Counts are reconstructed only to preserve the saved fractions used by the dialog.
        atlas_count = 1_000_000
        inverse_qc = InverseQCReport(
            roundtrip=ErrorStatistics(
                float(row["RoundTripMean_mm"]),
                float(row["RoundTripP95_mm"]),
                float(row["RoundTripMaximum_mm"]),
            ),
            converged_target_samples=converged,
            target_sample_count=target_count,
            valid_inverse_voxels=0,
            inverse_voxel_count=1,
            valid_atlas_voxels=round(atlas_fraction * atlas_count),
            atlas_voxel_count=atlas_count,
            threshold_mm=float(row["ThresholdP95_mm"]),
            minimum_roundtrip_sample_count=int(row.get("MinimumRoundTripSampleCount", 30)),
        )
    result = SimpleNamespace(
        registration_type=manifest.get("RegistrationType", "K04 multi-reference"),
        method=manifest["Method"],
        landmark_subset=SimpleNamespace(labels=labels),
        routes=tuple(routes),
        qc=qc,
        uncertainty=uncertainty,
        inverse=(SimpleNamespace() if manifest.get("InverseGenerated") else None),
        inverse_qc=inverse_qc,
    )
    center = tuple(float(value) for value in viewer["CenterLPS"])
    return SavedQCSession(root, target, atlas, warped, result, center)
