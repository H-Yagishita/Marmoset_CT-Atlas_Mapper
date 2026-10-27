# ANTs registration

Select **ANTs registration**, place or import the target landmarks, and choose
**Rigid** or **Similarity**. The app registers the CT to all six references and
averages their complete mappings into BMA 2.0.

The Windows package includes ANTs 2.6.5. It does not use 3D Slicer or SlicerANTs.
Keep `_internal/ants` with the rest of the application. The Microsoft Visual C++
x64 runtime is required if it is not already installed; the app does not install
dependencies at startup.

## Registration steps

1. Fit a rigid transform from the target landmarks to each reference CT.
   Use the same common landmark labels for all references.
2. Run ANTs on the original CT geometries, without a bone mask. Rigid uses one
   rigid stage (six degrees of freedom). Similarity uses a rigid stage followed
   by a similarity stage (seven degrees of freedom, including uniform scale).
3. Invert the complete ANTs composite transform to obtain the target-to-reference
   point transform. The landmark initialization is already included.
4. Compose each route with the reference CT-to-atlas transform. Sample all six
   routes on the same target-space grid and average their displacement vectors.
5. Save the transforms, mapped images, landmarks, and QC reports. If any route
   fails, the run stops rather than averaging fewer references.

ANTs uses fixed-to-moving transforms when resampling images. The saved
target-to-reference point transform uses the opposite direction. See
[OUTPUTS.md](OUTPUTS.md) for coordinate conventions and inverse QC.

## Parameters

The settings in `config/ants_registration.json` are:

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

These intensity-registration settings match those used in the manuscript.
The app uses landmark initialization rather than the manually saved initial
transforms used in that analysis. The standalone ANTs build also differs from
the earlier SlicerANTs build. Results may therefore differ numerically.
Previously saved results are not recalculated.

Window and level settings affect display only. No intensity normalization is
added by the app.

## Logs and checks

Each `ANTs/Reference_01` through `Reference_06` folder contains the initial
transform, command, console log, native composite transforms, final point
transform, and `Registration.json`. The main manifest identifies the reference
for each folder. Reports record parameters, software and input hashes,
coordinate conventions, and final matrices.

The app checks for finite transforms, a positive determinant, the requested
rigid or similarity model, forward/inverse agreement, and H5 save/reload
agreement. An ITK exception is treated as failure even if ANTs returns exit code
zero. Diagnostics are retained after a failed run.

CT images are staged in a temporary location without pre-resampling. Original
images and landmarks are not overwritten. Japanese image paths are supported.
If ANTs cannot use the Windows account's temporary path, set
`MARM_ATLAS_STATE_ROOT` to a writable ASCII-only folder.

## Building the standalone runtime

Download `ants-2.6.5-windows-2022-X64-VS2019.zip` from the
[official ANTs release](https://github.com/ANTsX/ANTs/releases/tag/v2.6.5), then run:

```powershell
.\.venv\Scripts\python.exe tools\prepare_standalone_ants.py <downloaded-zip>
.\build_exe.ps1 -SkipData
```

The preparation tool checks the archive SHA-256:
`2cfb09f9bfd796720819054711f493abd750dd3245875caaa5d04000d3a98c3d`.
It copies the executable and runtime files, checks dependencies, and retrieves
license notices from fixed upstream revisions. This network access occurs
during preparation, not when an end user starts the app.

The bundled `Runtime.json` records the checksums of the runtime and license
files. The build and the app verify them. ANTs runs in a separate process,
without the app's private Qt DLL directory in its search path.

For development, `MARM_ATLAS_ANTS` may specify an absolute path to a standalone
`antsRegistration.exe`. A broken override produces an error; the app does not
silently choose a different executable or fall back to Slicer.

## Testing

`MarmosetAtlasMapper.exe --ants-smoke-test REPORT.json` tests rigid and
similarity registration on a synthetic image with known rotation, translation,
and scale. The unit tests also cover transform direction, reference averaging,
and saved-result loading. These are software checks, not independent tests of
anatomical accuracy. Inspect the alignment for each new target.
