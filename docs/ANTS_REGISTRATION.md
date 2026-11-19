# ANTs registration

With **ANTs registration**, the target CT is registered to each reference CT using
image intensities, starting from a landmark-based alignment. The Windows package
includes ANTs 2.6.5; 3D Slicer is not used.

## Procedure

1. A rigid transform from the target landmarks to each reference's landmarks is
   used as the starting point.
2. ANTs registers the two CT images in their original geometry, without a bone
   mask. **Rigid** has 6 degrees of freedom; **Similarity** adds a uniform scale
   stage (7 degrees of freedom).
3. The resulting transform is combined with the reference's CT-to-atlas
   transform, and the six results are averaged as described in
   [OUTPUTS.md](OUTPUTS.md).

If registration to any reference fails, the run stops; it does not average fewer
than six references.

## Parameters

Defined in `config/ants_registration.json`. These are the settings used in the
paper, except that the paper started from a manual alignment instead of landmarks.

| Setting | Value |
| --- | --- |
| Metric | Mutual information, 32 bins |
| Sampling | Regular, 25% |
| Gradient step | 0.1 |
| Iterations | 1000 × 500 × 250 × 100 |
| Convergence | 1e-6, window 10 |
| Smoothing | 3 × 2 × 1 × 0 voxels |
| Shrink factors | 8 × 4 × 2 × 1 |
| Winsorization | 0.005, 0.995 |
| Precision | Float |
| Random seed | 20260918 |
| Threads | 4 |

The display contrast has no effect on registration.

## Output and troubleshooting

`ANTs/Reference_01` to `Reference_06` each contain the initial transform, the ANTs
command and log, the final transforms, and `Registration.json` (parameters,
software version, input checksums, and matrices). Each transform is checked for
finite values, a positive determinant, and the requested model. These files are
kept when a run fails.

The CT images are copied to a temporary folder before registration. Paths with
Japanese characters work, but if ANTs cannot use the Windows temporary folder,
set `MARM_ATLAS_STATE_ROOT` to a writable folder with an ASCII-only path.

## Building the standalone runtime

Only needed when building from source. Download
`ants-2.6.5-windows-2022-X64-VS2019.zip` from the [ANTs v2.6.5
release](https://github.com/ANTsX/ANTs/releases/tag/v2.6.5), then run:

```powershell
.\.venv\Scripts\python.exe tools\prepare_standalone_ants.py <downloaded-zip>
.\build_exe.ps1 -SkipData
```

The script checks the archive's SHA-256
(`2cfb09f9bfd796720819054711f493abd750dd3245875caaa5d04000d3a98c3d`), copies the
executable and its runtime files, and downloads the ANTs license notices.
`Runtime.json` records their checksums, which are verified by the build and by
the app.

For development, `MARM_ATLAS_ANTS` can point to another `antsRegistration.exe`
from this runtime.

## Testing

`MarmosetAtlasMapper.exe --ants-smoke-test REPORT.json` registers a synthetic
image with a known rotation, translation, and scale, for both rigid and
similarity transforms.
