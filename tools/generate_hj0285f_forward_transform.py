"""Generate the point-forward HJ0285F CT -> BMA 2.0 transform.

3D Slicer stores transforms in ITK files using resampling direction.  The
existing CT-to-BMA file therefore maps BMA physical points to HJ0285F CT when
read by SimpleITK.  This script inverts only the displacement field, inverts
the affine components exactly, and recomposes a point-forward transform.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import SimpleITK as sitk


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/transforms/HJ0285F_CT_to_BMA2_Atlas_ANTs.h5"
OUTPUT = ROOT / "data/transforms/HJ0285F_CT_to_BMA2_PointTransform.h5"


def main() -> int:
    composite = sitk.CompositeTransform(sitk.ReadTransform(str(SOURCE)))
    if composite.GetNumberOfTransforms() != 3:
        raise RuntimeError("Expected two affine transforms and one displacement field.")
    affine0 = composite.GetNthTransform(0)
    affine1 = composite.GetNthTransform(1)
    displacement = sitk.DisplacementFieldTransform(composite.GetNthTransform(2))
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

    # Slicer validation value, converted from RAS to LPS.
    bregma_ct_lps = np.array([31.909694816337236, 69.90474258324815, 1.7952003479003906])
    expected_atlas_lps = np.array([-0.3002787122928336, -0.9841086068501055, 9.486906482711724])
    actual_atlas_lps = np.asarray(forward.TransformPoint(tuple(bregma_ct_lps)))
    error_mm = float(np.linalg.norm(actual_atlas_lps - expected_atlas_lps))
    if error_mm > 0.01:
        raise RuntimeError(f"Bregma validation failed: {error_mm:.6f} mm")

    sitk.WriteTransform(forward, str(OUTPUT))
    print(f"Saved: {OUTPUT}")
    print(f"Bregma error: {error_mm:.6f} mm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
