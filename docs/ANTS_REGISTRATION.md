# ANTs registration

Select **ANTs registration**, place or import the target landmarks, and choose
**Rigid** or **Similarity**. The app registers the target CT to each of the six
reference CTs and averages the six complete mappings into BMA 2.0.

The Windows package includes ANTs 2.6.5; 3D Slicer and SlicerANTs are not used.
Keep `_internal/ants` with the rest of the application. The Microsoft Visual C++
Redistributable (x64) must be installed; the app does not install it.

## Steps

1. A rigid transform is estimated from the target landmarks to the corresponding
   landmarks of each reference, using the same landmark labels for all references.
2. ANTs registers the CT images in their original geometry, without a bone mask.
   **Rigid** uses one rigid stage (6 degrees of freedom); **Similarity** adds a
   similarity stage (7 degrees of freedom, including uniform scale).
3. The ANTs composite transform, which includes the landmark initialization, is
   inverted to obtain the target-to-reference point transform.
4. Each route is combined with the reference's CT-to-atlas transform. The six
   routes are sampled on the same target-space grid and their displacement vectors
   are averaged.
5. Transforms, mapped images, landmarks, and check reports are saved. If any route
   fails, the run stops instead of averaging fewer references.

ANTs resampling uses fixed-to-moving transforms, whereas the saved point
transforms map target to reference. See [OUTPUTS.md](OUTPUTS.md) for coordinate
conventions and the inverse check.

## Parameters

Set in `config/ants_registration.json`:

| Setting | Value |
| --- | --- |
| Metric | Mutual information, 32 bins |
| Sampling | Regular, 25% |
| Gradient step | 0.1 |
| Iterations | 1000 × 500 × 250 × 100 |
| Convergence | Threshold 1e-6; window 10 |
| Smoothing | 3 × 2 × 1 × 0 voxels |
| Shrink factors | 8 × 4 × 2 × 1 |
| Winsorization quantiles | 0.005 and 0.995 |
| Precision | Float |
| Random seed | 20260918 |
| Threads per job | 4 |

These are the intensity-based registration settings used in the associated
publication. The initialization differs: the app initializes ANTs from the
landmarks, whereas the publication used manual initial alignment. No additional
intensity normalization is applied, and the display contrast does not affect
registration.

## Logs and checks

The folders `ANTs/Reference_01` to `Reference_06` each contain the initial
transform, the ANTs command and console log, the composite and final point
transforms, and `Registration.json`, which records the parameters, software
version, input checksums, coordinate conventions, and final matrices. The run
manifest identifies the reference corresponding to each folder.

The app checks that each transform is finite, has a positive determinant, and
matches the requested model, and that the forward and inverse transforms and the
saved H5 files agree. An ITK exception is treated as a failure even if ANTs exits
with code zero. Diagnostics are kept after a failed run.

CT images are copied to a temporary folder without resampling; the originals are
not modified. Paths containing Japanese characters are supported. If ANTs cannot
use the Windows temporary folder, set `MARM_ATLAS_STATE_ROOT` to a writable folder
whose path contains only ASCII characters.

## Building the standalone runtime

This is needed only when building the app from source. Download
`ants-2.6.5-windows-2022-X64-VS2019.zip` from the [official ANTs
release](https://github.com/ANTsX/ANTs/releases/tag/v2.6.5), then run:

```powershell
.\.venv\Scripts\python.exe tools\prepare_standalone_ants.py <downloaded-zip>
.\build_exe.ps1 -SkipData
```

The tool checks the archive's SHA-256
(`2cfb09f9bfd796720819054711f493abd750dd3245875caaa5d04000d3a98c3d`), copies the
executable and its runtime files, checks their dependencies, and downloads the
license notices from fixed upstream revisions. Network access is required only for
this preparation, not when the app runs.

`Runtime.json` records the checksums of the runtime and license files; both the
build and the app verify them. ANTs runs as a separate process, without the app's
Qt DLL folder in its search path.

During development, `MARM_ATLAS_ANTS` can point to a standalone
`antsRegistration.exe`. If that path is invalid, the app reports an error rather
than using another executable.

## Testing

`MarmosetAtlasMapper.exe --ants-smoke-test REPORT.json` runs rigid and similarity
registration on a synthetic image with known rotation, translation, and scale. The
unit tests also cover transform direction, reference averaging, and loading of
saved results. These tests check the software, not anatomical accuracy; inspect
the alignment for every new target.
