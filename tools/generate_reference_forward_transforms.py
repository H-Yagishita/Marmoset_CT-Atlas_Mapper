"""Generate point-forward CT -> BMA 2.0 transforms for all reference CTs."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import SimpleITK as sitk


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from marmoset_atlas_mapper.landmarks import load_slicer_markups


REFERENCES = ("HJ0285F", "HH0424M", "J0476M", "J0477M")


def invert_reference_transform(reference_id: str) -> tuple[Path, float]:
    source = ROOT / "data" / "transforms" / f"{reference_id}_CT_to_BMA2_Atlas_ANTs.h5"
    output = ROOT / "data" / "transforms" / f"{reference_id}_CT_to_BMA2_PointTransform.h5"
    landmarks_path = next((ROOT / "data" / "reference").glob(f"{reference_id}_Landmarks.mrk.json"))

    source_transform = sitk.CompositeTransform(sitk.ReadTransform(str(source)))
    if source_transform.GetNumberOfTransforms() != 3:
        raise RuntimeError(f"{reference_id}: expected two affine transforms and one displacement field.")
    affine0 = source_transform.GetNthTransform(0)
    affine1 = source_transform.GetNthTransform(1)
    displacement = sitk.DisplacementFieldTransform(source_transform.GetNthTransform(2))
    inverse_field = sitk.InvertDisplacementField(
        displacement.GetDisplacementField(),
        maximumNumberOfIterations=50,
        maxErrorToleranceThreshold=0.01,
        meanErrorToleranceThreshold=0.001,
        enforceBoundaryCondition=True,
    )
    forward = sitk.CompositeTransform(
        [sitk.DisplacementFieldTransform(inverse_field), affine1.GetInverse(), affine0.GetInverse()]
    )

    landmarks = load_slicer_markups(landmarks_path)
    errors = []
    for label in (f"LM{index:02d}" for index in range(1, 9)):
        reference_point = np.asarray(landmarks[label], dtype=float)
        atlas_point = forward.TransformPoint(tuple(reference_point))
        roundtrip_point = source_transform.TransformPoint(atlas_point)
        errors.append(float(np.linalg.norm(np.asarray(roundtrip_point) - reference_point)))
    maximum_error = max(errors)
    if maximum_error > 0.05:
        raise RuntimeError(f"{reference_id}: round-trip validation failed ({maximum_error:.6f} mm).")

    sitk.WriteTransform(forward, str(output))
    return output, maximum_error


def main() -> int:
    for reference_id in REFERENCES:
        output, maximum_error = invert_reference_transform(reference_id)
        print(f"{reference_id}: {output.name}; max landmark round-trip error={maximum_error:.6f} mm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
