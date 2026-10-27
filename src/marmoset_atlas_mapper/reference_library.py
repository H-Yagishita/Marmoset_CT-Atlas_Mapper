from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import bundled_config_root, configured_resource_root


@dataclass(frozen=True)
class AtlasLayer:
    name: str
    path: Path
    interpolation: str


@dataclass(frozen=True)
class ReferenceEntry:
    reference_id: str
    ct_path: Path
    landmarks_path: Path
    ct_to_atlas_forward_path: Path


@dataclass(frozen=True)
class ConsensusSettings:
    method: str
    grid_spacing_mm: float
    grid_padding_mm: float
    qc_sample_count: int
    random_seed: int


@dataclass(frozen=True)
class InverseSettings:
    method: str
    grid_spacing_mm: float
    grid_padding_mm: float
    maximum_iterations: int
    convergence_tolerance_mm: float
    maximum_step_mm: float
    minimum_roundtrip_sample_count: int


@dataclass(frozen=True)
class QCCriteria:
    component_approximation_p95_max_mm: float
    consensus_approximation_p95_max_mm: float
    inverse_roundtrip_p95_max_mm: float
    fre_mean_rms_mm: float
    fre_minimum_rms_mm: float
    fre_maximum_rms_mm: float
    fre_condition: str


@dataclass(frozen=True)
class ReferenceLibrary:
    schema_version: int
    library_id: str
    atlas_id: str
    atlas_space: str
    atlas_reference: Path
    atlas_label_map: Path
    atlas_color_table: Path
    atlas_layers: tuple[AtlasLayer, ...]
    allowed_labels: tuple[str, ...]
    minimum_landmark_count: int
    recommended_landmark_count: int
    consensus: ConsensusSettings
    inverse: InverseSettings
    qc: QCCriteria
    references: tuple[ReferenceEntry, ...]
    manifest_path: Path

    def missing_files(self) -> list[Path]:
        paths = [self.atlas_reference, self.atlas_label_map, self.atlas_color_table]
        paths.extend(layer.path for layer in self.atlas_layers)
        for reference in self.references:
            paths.extend(
                [reference.ct_path, reference.landmarks_path, reference.ct_to_atlas_forward_path]
            )
        return sorted({path for path in paths if not path.is_file()})


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (root / path).resolve()


def load_reference_library(
    path: str | Path | None = None, *, validate_files: bool = True
) -> ReferenceLibrary:
    manifest_path = Path(path) if path is not None else bundled_config_root() / "reference_library.json"
    payload: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = configured_resource_root()
    atlas = payload["atlas"]
    landmarks = payload["landmarks"]
    consensus = payload["consensus"]
    inverse = payload["inverse"]
    qc = payload["qc"]
    fre = qc["fre_benchmark"]
    layers = tuple(
        AtlasLayer(name, _resolve(root, value["path"]), value["interpolation"])
        for name, value in atlas["layers"].items()
    )
    references = tuple(
        ReferenceEntry(
            reference_id=value["id"],
            ct_path=_resolve(root, value["ct"]),
            landmarks_path=_resolve(root, value["landmarks"]),
            ct_to_atlas_forward_path=_resolve(root, value["ct_to_atlas_forward"]),
        )
        for value in payload["references"]
    )
    expected_count = int(payload.get("expected_reference_count", 6))
    if expected_count < 1 or len(references) != expected_count:
        raise ValueError(f"This library requires Nref={expected_count}, found {len(references)}.")
    if len({item.reference_id for item in references}) != len(references):
        raise ValueError("Reference IDs must be unique.")
    library = ReferenceLibrary(
        schema_version=int(payload["schema_version"]),
        library_id=payload["library_id"],
        atlas_id=atlas["id"],
        atlas_space=atlas["space"],
        atlas_reference=_resolve(root, atlas["reference_image"]),
        atlas_label_map=_resolve(root, atlas["label_map"]),
        atlas_color_table=_resolve(root, atlas["color_table"]),
        atlas_layers=layers,
        allowed_labels=tuple(landmarks["allowed_labels"]),
        minimum_landmark_count=int(landmarks["minimum_count"]),
        recommended_landmark_count=int(landmarks["recommended_count"]),
        consensus=ConsensusSettings(
            method=consensus["method"],
            grid_spacing_mm=float(consensus["grid_spacing_mm"]),
            grid_padding_mm=float(consensus["grid_padding_mm"]),
            qc_sample_count=int(consensus["qc_sample_count"]),
            random_seed=int(consensus["random_seed"]),
        ),
        inverse=InverseSettings(
            method=inverse["method"],
            grid_spacing_mm=float(inverse["grid_spacing_mm"]),
            grid_padding_mm=float(inverse["grid_padding_mm"]),
            maximum_iterations=int(inverse["maximum_iterations"]),
            convergence_tolerance_mm=float(inverse["convergence_tolerance_mm"]),
            maximum_step_mm=float(inverse["maximum_step_mm"]),
            minimum_roundtrip_sample_count=int(inverse["minimum_roundtrip_sample_count"]),
        ),
        qc=QCCriteria(
            component_approximation_p95_max_mm=float(qc["component_approximation_p95_max_mm"]),
            consensus_approximation_p95_max_mm=float(qc["consensus_approximation_p95_max_mm"]),
            inverse_roundtrip_p95_max_mm=float(qc["inverse_roundtrip_p95_max_mm"]),
            fre_mean_rms_mm=float(fre["mean_rms_mm"]),
            fre_minimum_rms_mm=float(fre["minimum_rms_mm"]),
            fre_maximum_rms_mm=float(fre["maximum_rms_mm"]),
            fre_condition=fre["condition"],
        ),
        references=references,
        manifest_path=manifest_path.resolve(),
    )
    missing = library.missing_files()
    if validate_files and missing:
        raise FileNotFoundError("Reference library is incomplete: " + ", ".join(map(str, missing)))
    return library
