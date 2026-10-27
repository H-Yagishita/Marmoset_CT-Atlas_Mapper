# Outputs and coordinate conventions

Results are saved in the output folder chosen when a run starts. If the folder is
not empty, the app creates a timestamped subfolder. The original CT and landmark
files are never overwritten.

## Main files

| File or folder | Contents |
| --- | --- |
| `Target_CT_to_BMA_MultiRef_Nref6_Forward.h5` | Target-to-atlas point transform |
| `Target_CT_to_BMA_MultiRef_Nref6_Displacement.nrrd` | Mean forward displacement field |
| `SingleReference/` | The six target-to-atlas transforms, one per reference |
| `TargetCT_in_Reference/` | Target CT resampled into each reference CT space, with coverage masks |
| `UsedLandmarks/` | Landmarks used for the target and each reference |
| `AtlasLayers_in_TargetCT/` | Atlas MRI, Nissl, myelin, and region labels in target CT space |
| `TargetCT_in_BMA2.0.nii.gz` | Target CT in atlas space (saved only if the inverse check passes) |
| `Inverse/` | Inverse transform, displacement field, and convergence mask |
| `MappedMarkups/` | Landmarks mapped to atlas space, as Markups JSON and CSV |
| `QC/` | Landmark residuals, numerical check tables, and overlay images |
| `QC/Volumes/` | Volumes used to reopen the Quality Check views |
| `Uncertainty/` | Disagreement among the six reference mappings |
| `Run_Manifest.json`, `Run_Manifest.csv` | Run settings, provenance, and output paths |

ANTs runs use the prefix `Target_CT_to_BMA_ANTs_MultiRef_Nref6` and also save the
command, transforms, log, and input checksums for each reference under `ANTs/`.

Keep the run folder intact when moving or sharing it. **Open results** reads the
manifest and the saved volumes to restore the target CT, landmarks, contrast,
settings, and viewers without repeating the registration.

## How the six mappings are combined

Each reference provides a route from a target CT point, through that reference's
CT, into BMA 2.0. The six routes are sampled on the same target-space grid (0.5 mm
spacing, 1.0 mm padding), and their forward displacement vectors are averaged with
equal weights. This is equivalent to averaging the six mapped positions at each
grid point; image intensities and affine parameters are not averaged.

## Coordinates and interpolation

The grid is axis-aligned in RAS coordinates and is stored in ITK with the
equivalent LPS origin and direction. Calculations use physical LPS coordinates in
millimeters. Imported RAS Markups are converted to LPS; generated Markups and
coordinate CSV files use LPS. Displacement fields and continuous atlas images are
interpolated linearly, and region labels by nearest-neighbor interpolation.

## Numerical checks

- **Forward check**: the sampled fields are compared with the original transform
  routes. The 95th-percentile approximation error must be below 0.05 mm.
- **Inverse check**: to resample the target CT into atlas space, the app solves
  for the inverse mapping on an atlas-space grid (affine initialization followed
  by Newton iterations) and records a convergence mask. The inverse is saved only
  if the 95th-percentile round-trip error is below 0.25 mm with at least 30 valid
  samples. These limits are defined in `config/reference_library.json`.

Atlas coverage is reported but does not prevent processing of partial CT scans.
Areas outside the CT field of view are set to zero in the atlas-space CT. If the
inverse check fails, the forward mapping and the atlas layers in target CT space
are still saved, but the inverse transform and the atlas-space CT are not.

These checks test numerical consistency, not anatomical correspondence. The
landmark residual (fiducial registration error) measures the remaining landmark
mismatch after registration, and the uncertainty volumes measure disagreement
among references; neither directly measures the mapping error for a new animal.
