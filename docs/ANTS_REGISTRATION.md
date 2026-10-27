# ANTs registration (0.3.1)

Select **ANTs registration** and **Rigid** or **Similarity**, place/import the
corresponding landmarks, and choose a new or empty output directory.
Windows ANTs 2.6.5 is bundled and invoked directly: no 3D Slicer, SlicerANTs,
Python installation, or shell-script interpreter is needed by the user.
Keep the complete distribution, including `_internal/ants`, together.
Microsoft Visual C++ 2015-2022 x64 runtime is a prerequisite if not already
installed. No dependencies are downloaded or installed at application startup.
An advanced explicit override, MARM_ATLAS_ANTS, accepts an absolute path to a
standalone antsRegistration executable. There is no PATH/Slicer/backend fallback.
MARM_ATLAS_SLICER is ignored. A broken explicit override is reported as an error.

The bundled Runtime.json pins the official archive checksum and every shipped
runtime/license file. These files are verified before registration. ANTs runs
in a separate process, with the app's private Qt DLL directory removed.

All six references participate: HH0312F, HH0424M, HH0428M, HJ0285F, J0476M,
J0477M. J0476M is only the fixed visual preview, not a privileged mapping route.
The same selected, valid common landmarks are used for every route (minimum
three non-collinear points). LM01-LM13 are available for initialization.

1. Fit a point-forward Rigid transform from Target CT landmarks to each reference.
2. Run unmasked intensity-based ANTs on the original physical image geometries.
   The initial transform is passed as fixed-to-moving, i.e. inverse of step 1.
   Rigid uses one Rigid stage (6 DOF). Similarity uses Rigid then Similarity
   (7 DOF: rotation, translation, one isotropic scale).
3. Invert the complete native ANTs Composite (fixed-to-moving image pull) to
   obtain the final Target-to-Reference point-forward matrix. Do not apply the
   landmark initial transform a second time.
4. Compose with each reference's CT-to-Atlas point-forward transform. Sample
   each complete route on the same Target-space grid and average the six
   displacement vectors with equal weights. This averages transformed positions,
   not affine parameters or CT pixel intensities.
5. Use the existing field approximation QC, explicit inverse solver/QC, all
   Atlas-layer outputs, Target CT in every Reference CT, UsedLandmarks, and viewer.
   A failed route aborts the run; it never silently becomes a five-reference mean.

Parameters: MI with 32 bins, Regular 0.25 sampling, gradient step 0.1,
iterations 1000x500x250x100, convergence 1e-6 / window 10,
smoothing 3x2x1x0 vox, shrink 8x4x2x1, winsorization [0.005,0.995],
float computations, seed 20260918, four threads per job.
These match the manuscript ANTs intensity settings, **but the app uses landmark
initialization, not the manuscript's manually saved initial transforms**.
No skull mask or intensity normalization is added. Window/Level is display-only.
Different ANTs/ITK versions and multithreaded reductions can affect numerical results.
The prior SlicerANTs build was 2.5.3.post10; the standalone update changes the
build, not the registration settings or reference selection. Previously generated
manuscript data and saved results are left unchanged.

## Building the standalone runtime

Download the official `ants-2.6.5-windows-2022-X64-VS2019.zip` from
https://github.com/ANTsX/ANTs/releases/tag/v2.6.5, then run:

```powershell
.\.venv\Scripts\python.exe tools\prepare_standalone_ants.py <downloaded-zip>
.\build_exe.ps1 -SkipData
```

The preparation tool verifies SHA256
`2cfb09f9bfd796720819054711f493abd750dd3245875caaa5d04000d3a98c3d`,
copies the executable and any included dependent DLLs, checks unresolved DLLs,
and retrieves ANTs/ITK license notices from fixed upstream revisions. This is a
build-time network operation only. The build refuses a missing or modified
runtime. Native runtime files are not rewritten by PyInstaller dependency scanning.

## Provenance / failure behavior

The main prefix is Target_CT_to_BMA_ANTs_MultiRef_Nref6.
ANTs/Reference_01 through Reference_06 contain the initial transform, command,
full Console.log, native Composite/InverseComposite, final point-forward H5,
and Registration.json. The main Run_Manifest.json maps reference IDs to these
reports. Reports include parameters, runtime version/hash, CT hashes, coordinate
conventions, final matrices, and post-registration landmark residuals.
The residual is a placement check, not the MI optimization metric or atlas accuracy.

Native images are losslessly staged to a temporary NIfTI location without
pre-resampling. Original CTs and landmarks are never overwritten.
Use an ASCII MARM_ATLAS_STATE_ROOT if the Windows account path has no usable
short-name equivalent. Per-route diagnostics remain after a failure.
Explicit ITK exceptions count as failure even if the native command returns zero.
The app checks positive determinant, Rigid/Similarity singular values,
native inverse agreement (0.001 mm), and H5 save/reload agreement.

BRAINSFit implementation and old General result-loading support have been removed.
Old result files remain untouched. Use the backed-up former application for them.
Landmark four-/six-reference saved results remain supported.

## Validation

Automated tests cover transform direction (including nonzero centers), 6/7 DOF,
native error handling, six complete-route arithmetic means, reference-order
invariance, saved-result reload, and rejection of incomplete reference libraries.
The opt-in command --ants-smoke-test REPORT.json creates a new disposable test
directory and exercises both models using a normalized asymmetric phantom with
known rotation, translation and scale. It also works in the packaged executable.
Real-reference execution tests use a reference CT as input, including the identity
route: these are software checks, not independent mapping-accuracy validation.
Inspect anatomical alignment in QC for each new subject.
