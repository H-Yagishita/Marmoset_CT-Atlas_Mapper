"""Small local integration smoke test for the discovered Slicer BRAINSFit CLI."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import SimpleITK as sitk

from marmoset_atlas_mapper.brainsfit_registration import run_brainsfit


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="marm_brainsfit_") as temporary:
        root = Path(temporary)
        grid = np.indices((24, 24, 24), dtype=float)
        radius = np.sqrt(sum((grid[axis] - 12.0) ** 2 for axis in range(3)))
        array = np.where(radius < 8.0, 900.0 - radius * 30.0, 0.0).astype(np.float32)
        image = sitk.GetImageFromArray(array)
        image.SetSpacing((0.5, 0.5, 0.5))
        moving = root / "moving.nii.gz"
        fixed = root / "fixed.nii.gz"
        sitk.WriteImage(image, str(moving))
        sitk.WriteImage(image, str(fixed))
        labels = ("LM01", "LM02", "LM03", "LM04")
        points = {
            "LM01": np.array([3.0, 3.0, 3.0]),
            "LM02": np.array([8.0, 3.0, 3.0]),
            "LM03": np.array([3.0, 8.0, 3.0]),
            "LM04": np.array([3.0, 3.0, 8.0]),
        }
        result, output, runtime = run_brainsfit(
            moving_ct=moving,
            fixed_ct=fixed,
            initial_matrix_lps=np.eye(4),
            method="Rigid",
            output_directory=root / "output",
            moving_landmarks=points,
            fixed_landmarks=points,
            labels=labels,
            progress=print,
        )
        if result.rms_mm > 0.05:
            raise RuntimeError(f"Unexpected identity smoke-test FRE: {result.rms_mm:.6f} mm")
        print(f"PASS: {runtime.slicer_launcher}; {output}; FRE={result.rms_mm:.6f} mm")


if __name__ == "__main__":
    main()
