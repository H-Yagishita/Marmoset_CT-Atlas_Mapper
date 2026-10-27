# Outputs and coordinate conventions

Results are saved in the output folder selected at the start of a run. If that
folder is not empty, the app creates a timestamped subfolder. Original CT images
and landmark files are not overwritten.

## Main files

| File or folder | Contents |
| --- | --- |
| `Target_CT_to_BMA_MultiRef_Nref6_Forward.h5` | Target-to-atlas point transform |
| `Target_CT_to_BMA_MultiRef_Nref6_Displacement.nrrd` | Mean forward displacement field |
| `SingleReference/` | Six sampled target-to-atlas transforms, one per reference |
| `TargetCT_in_Reference/` | Target CT resampled into each reference CT space, with coverage masks |
| `UsedLandmarks/` | The landmark subset used for the target and each reference |
| `AtlasLayers_in_TargetCT/` | Atlas MRI, Nissl, myelin, and region labels in target CT space |
| `TargetCT_in_BMA2.0.nii.gz` | Target CT in atlas space, saved only when inverse QC passes |
| `Inverse/` | Inverse transform, displacement field, and convergence masks |
| `MappedMarkups/` | Registration landmarks mapped to atlas space, as Markups JSON and CSV |
| `QC/` | Landmark residuals, numerical QC tables, and overlay images |
| `QC/Volumes/` | Volumes used to reopen the interactive quality-check views |
| `Uncertainty/` | Measures of disagreement between the six reference mappings |
| `Run_Manifest.json` and `Run_Manifest.csv` | Run settings, provenance, and output paths |

ANTs runs use the prefix `Target_CT_to_BMA_ANTs_MultiRef_Nref6` and also save
per-reference commands, transforms, logs, and input hashes under `ANTs/`.

Keep the run folder intact when moving or sharing results. **Open results** uses
the manifest and QC volumes to restore the target CT, landmarks, contrast,
registration settings, and viewers without repeating the registration.

## How the mappings are combined

Each route maps a target CT point through a reference CT into BMA 2.0. The six
complete routes are sampled on the same target-space grid, with 0.5 mm spacing
and 1.0 mm padding. The forward displacement vectors are then averaged with
equal weights. This is equivalent to averaging the six mapped positions at
each grid point. It is not an average of image intensities or affine parameters.

The grid is axis-aligned in RAS coordinates and is represented in ITK with the
equivalent LPS origin and direction. Calculations use physical LPS coordinates
in millimetres. RAS Markups are converted on import; generated Markups and
coordinate CSV files use LPS. Displacement fields and continuous atlas images
are sampled with linear interpolation; region labels use nearest-neighbour
interpolation.

## Numerical quality checks

Forward QC compares the sampled fields with the original transform routes.
The configured 95th-percentile approximation-error limit is 0.05 mm.

To resample the target CT into atlas space, the app solves for the inverse
mapping on an atlas-space grid. It uses an affine initialization followed by
Newton iterations and records a convergence mask. The inverse is saved only
when the round-trip error passes QC: its 95th percentile must be below 0.25 mm,
with at least 30 valid overlap samples. These settings are recorded in
`config/reference_library.json`.

Atlas coverage is reported separately. It does not prevent processing of
partial CT scans. Areas outside the observed CT field of view remain zero in
the atlas-space CT. If inverse QC fails, the forward mapping and atlas layers
in target CT space remain available; the inverse transform and atlas-space CT
are not saved.

These checks assess numerical consistency, not anatomical correspondence.
Fiducial registration error (FRE) measures residual landmark mismatch after
registration. The uncertainty volumes measure disagreement between references.
Neither is a direct measurement of the mapping error for a new target animal.
