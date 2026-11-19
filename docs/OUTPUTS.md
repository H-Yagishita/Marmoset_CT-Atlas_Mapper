# Outputs

Each run is saved in the output folder you choose. If that folder is not empty, a
timestamped subfolder is created. Input CT and landmark files are never modified.

| File or folder | Contents |
| --- | --- |
| `Target_CT_to_BMA_MultiRef_Nref6_Forward.h5` | Target-to-atlas point transform |
| `Target_CT_to_BMA_MultiRef_Nref6_Displacement.nrrd` | Averaged displacement field |
| `SingleReference/` | Target-to-atlas transform through each reference |
| `TargetCT_in_Reference/` | Target CT resampled into each reference CT, with coverage masks |
| `UsedLandmarks/` | Landmarks used for the target and each reference |
| `AtlasLayers_in_TargetCT/` | Atlas MRI, Nissl, myelin, and region labels in target CT space |
| `TargetCT_in_BMA2.0.nii.gz` | Target CT in atlas space (only if the inverse check passes) |
| `Inverse/` | Inverse transform, displacement field, and convergence mask |
| `MappedMarkups/` | Landmarks mapped to atlas space (Markups JSON and CSV) |
| `QC/` | Landmark residuals, check tables, and overlay images |
| `QC/Volumes/` | Volumes used to reopen the Quality Check views |
| `Uncertainty/` | Disagreement among the six references |
| `Run_Manifest.json`, `.csv` | Settings, provenance, and output paths |

ANTs runs use the prefix `Target_CT_to_BMA_ANTs_MultiRef_Nref6` and add an `ANTs/`
folder with the command, transforms, log, and input checksums for each reference.

**Open results** reads the manifest to restore a run without repeating the
registration, so keep the run folder together when you move it.

## Averaging the six references

Each reference gives a path from the target CT, through that reference's CT, to
BMA 2.0. All six are sampled on one grid in target space (0.5 mm spacing, 1.0 mm
padding) and their displacement vectors are averaged with equal weights. In other
words, the mapped position of each grid point is the mean of the six mapped
positions.

## Coordinates

Calculations use LPS physical coordinates in millimeters. The averaging grid is
axis-aligned in RAS and stored in ITK as the equivalent LPS geometry. Imported
Markups in RAS are converted to LPS; Markups and CSV files written by the app use
LPS. Images and displacement fields are interpolated linearly, and region labels
with nearest neighbor.

## Numerical checks

- **Forward:** the averaged field is compared with the original transforms. The
  95th-percentile difference must be below 0.05 mm.
- **Inverse:** to put the target CT into atlas space, the inverse mapping is
  solved on an atlas grid (affine start, then Newton iterations). It is saved only
  if the 95th-percentile round-trip error is below 0.25 mm with at least 30 valid
  points. If it fails, the forward results are still saved.

The thresholds are set in `config/reference_library.json`. Partial CT scans are
processed; regions outside the CT are set to zero in the atlas-space CT.

These checks only test numerical consistency. The landmark residuals and the
uncertainty maps are diagnostics and should not be read as the mapping error.
