# Marmoset Atlas Mapper

A standalone Windows desktop application for landmark-based mapping between a
user marmoset CT and the Brain/MINDS BMA 2.0 atlas. Version 0.3.2 uses a six-reference
library (Nref=6): HH0312F, HH0424M, HH0428M, HJ0285F, J0476M, and J0477M.

This software was developed for research and has not been validated for
diagnostic or clinical use. This statement describes its intended use and
validation status; it does not add restrictions to the software license.

## 0.3.2 Unicode-path fix and complete-package preparation

Japanese/non-ASCII image and transform paths now use an ASCII temporary copy
that preserves the original file extension. Windows 8.3 file aliases are not
used, because they may truncate `.nii.gz` to `.GZ` and `.nrrd` to `.NRR`.
Voxel values, physical geometry, registration parameters, and existing results
are unchanged. Regression tests cover hosts both with and without short names.

A complete Windows ZIP, containing the application, corresponding source,
BMA 2.0 and the six-reference library, is being prepared for Zenodo. It has not
been published and no DOI has been assigned. See [Zenodo preparation](docs/ZENODO_RELEASE.md).

## Standalone ANTs (introduced in 0.3.1)

The Windows distribution now includes ANTs 2.6.5. Neither 3D Slicer nor
SlicerANTs is required. Registration parameters and six-reference consensus
are unchanged; the native ANTs/ITK build has changed, so floating-point results
need not match the earlier runtime exactly. Existing results are not recomputed.

ANTs replaces the former single-reference intensity backend. All current
registration modes use Nref=6; no BRAINSFit executable or result compatibility
is retained. Tests use disposable outputs; passing tests do not establish
anatomical accuracy or absence of all bugs.

## Current workflow

1. Load a User CT (`.nii`, `.nii.gz`, `.nrrd`, or `.nhdr`).
2. Use the fixed J0476M preview to identify landmarks and place corresponding
   landmarks in the Target CT. Correspondence is by label, never by JSON order.
3. Select a registration type:
   - `Landmark (Skull-base)`: LM01-LM08, six-reference consensus;
   - `Landmark (Skull-all)`: LM01-LM13, six-reference consensus;
   - `ANTs registration`: selected LM01-LM13 provide a Rigid initialization
     to each of the six references, followed by unmasked ANTs Rigid (6 DOF) or
     isotropic Similarity (7 DOF) intensity registration.
4. Choose Rigid or Similarity and run registration. At least three
   non-collinear common landmarks are required; five or more are recommended.
   Missing landmarks are excluded consistently from every applicable route.
5. All three modes construct six complete forward routes:
   `Target CT -> Reference CT -> BMA 2.0`. Each route is sampled on the same
   axis-aligned RAS displacement grid (0.5 mm spacing, 1.0 mm padding), and the
   six forward displacement vectors are averaged with equal weight.
6. Inspect the Quality Check window:
   - Atlas MRI and each transformed reference CT overlaid on the Target CT;
   - independently adjustable Red/Green overlay contrast;
   - saved forward/inverse QC and uncertainty diagnostics in the output folder.
7. The application automatically generates 3A, every configured 3B layer, and
   the registration-landmark 3C output. The Atlas viewer opens any saved layer
   in Target CT geometry without recomputing registration.

The lower dock shows a timestamped processing log and can be resized or hidden.
The Target CT panel has `Window` and `Level` sliders with numeric controls and an `Auto / Reset`
button. These change display contrast only, including for normalized CT intensities;
voxel values, physical geometry, landmarks, and registration are unchanged.
The display settings are saved with the workspace and restored by `Open results`.
Reference-wise FRE is retained in the saved numerical diagnostics, not displayed
in the results panel; there is no single-reference FRE warning, selection, or weighting.

For 3A, the application explicitly solves the inverse on an Atlas-space grid
using a global-affine initialization followed by vectorized Newton iterations.
It writes a convergence mask and evaluates forward-inverse round-trip error.
The inverse transform and Target-CT-in-Atlas image are written only when inverse
QC passes: round-trip P95 below 0.25 mm with at least the configured number of
valid overlap samples. Atlas coverage is saved as descriptive information only
and never gates partial-CT processing; unobserved regions remain zero in 3A.

## Nref=6 output set

The output directory is selected before registration. A successful run writes:

- `Target_CT_to_BMA_MultiRef_Nref6_Forward.h5`;
- `Target_CT_to_BMA_MultiRef_Nref6_Displacement.nrrd`;
- six sampled single-reference complete forward transforms in
  `SingleReference/`;
- Target CT resampled into every participating Reference CT geometry in
  `TargetCT_in_Reference/`, with observed-FOV masks in its `CoverageMasks/`
  subdirectory; these use exact inverses of the Rigid/Similarity transforms
  and are independent of Atlas inverse QC;
- the exact landmark subset used by the transform in `UsedLandmarks/` as both
  Slicer Markups JSON and LPS-coordinate CSV for the Target CT and every
  participating Reference CT;
- every configured Atlas MRI/Nissl/Myelin/Regions layer resampled into Target
  CT geometry in `AtlasLayers_in_TargetCT/`;
- when inverse QC passes, `TargetCT_in_BMA2.0.nii.gz`, an Atlas-to-Target
  inverse H5, inverse displacement field, and convergence masks in `Inverse/`;
- registration landmarks mapped into BMA 2.0 as Markups JSON and CSV in
  `MappedMarkups/`;
- landmark FRE/residual, forward-transform QC, and inverse QC CSV files in `QC/`;
- aspect-correct red/green forward and inverse QC overlay PNGs in `QC/`;
- reloadable QC volumes in `QC/Volumes/`;
- three uncertainty volumes and `Uncertainty_Summary.csv`;
- `Run_Manifest.csv` and `Run_Manifest.json`.

ANTs mode uses the prefix `Target_CT_to_BMA_ANTs_MultiRef_Nref6` and
retains per-reference initial transforms, native ANTs transforms, commands,
software/input hashes, final point-forward matrices and logs under `ANTs/`.
It uses the same consensus, inverse QC, saved workspace and automatic outputs.

`Open results` restores the Target CT, placed landmarks, registration mode,
transform method, QC state, Atlas layers, and interactive viewers without
recomputing registration. `Open Folder` opens the active output directory.
Saved four-reference results from the previous version can still be opened.
Old General/BRAINSFit results are not supported; open them with the backed-up old application.
Existing Landmark results remain readable.

All calculation-core coordinates are physical LPS coordinates in millimetres.
The sampling lattice is defined as an axis-aligned RAS grid and represented in
ITK using the equivalent LPS origin/direction. Slicer Markups saved as RAS are
converted on import; application-generated Markups are written as LPS.

## Run from source

On Windows:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

The prepared local checkout can also be started with `run_app.bat`. For ANTs
registration, prepare the native runtime as described in
[ANTs registration](docs/ANTS_REGISTRATION.md#building-the-standalone-runtime);
installing the Python requirements alone does not install ANTs.

On first launch, the application checks the library pinned in
`config/reference_data_catalog.json`. The complete Windows package is being
prepared for Zenodo; no public download URL or DOI is available yet.
For that package, extract `MarmosetAtlasMapper_v0.3.2_Windows_Complete.zip`
into a new folder and run `MarmosetAtlasMapper.exe`. All required data and
the native ANTs runtime are included; no split archives need to be merged.
Do not mix its `_internal` directory with an older release.

When running from source, install the Python dependencies and supply the same
data library: copy the complete package's `data` directory into the source root,
or select the complete application folder in the data-location dialog. ANTs
must also be prepared separately or selected with `MARM_ATLAS_ANTS` as below.

The final layout must be:

```text
MarmosetAtlasMapper/
|-- MarmosetAtlasMapper.exe
|-- _internal/
|-- data/
|   |-- atlas/
|   |-- reference_v2/
|   `-- transforms_v2/
`-- README.md
```

When an existing library is selected on a different Windows drive, the six
large HDF5 transforms are checksum-verified and cached locally before
SimpleITK opens them. This avoids HDF5 access violations seen on some external
or mapped drives; CT/MRI images themselves remain in the selected library.

The Zenodo landing-page URL remains blank until a real record is created.
Package checksums are distributed alongside the complete ZIP; an archive cannot
contain its own final checksum. Public distribution still requires the data
permissions and third-party license checks below.

## Build the portable application

Install `requirements-dev.txt` and prepare the pinned ANTs runtime using
[the runtime preparation instructions](docs/ANTS_REGISTRATION.md#building-the-standalone-runtime)
before building.

```powershell
.\build_exe.ps1
```

The portable application is created at
`dist\MarmosetAtlasMapper\MarmosetAtlasMapper.exe`. The command above retains a
local data-bundled development build. For a data-free development build use:

```powershell
.\build_exe.ps1 -SkipData
```

The data-free build displays the manual data-placement instructions on first launch. A
one-directory build is intentional because Qt and SimpleITK are too large for a
practical single-file EXE.

The maintained build specification validates Qt's Windows ICU API and excludes
conflicting build-host ICU DLLs. To verify a packaged build, set its reference
data location and run `MarmosetAtlasMapper.exe --gui-smoke-test <report.json>`.
This initializes the native Windows Qt platform, loads the reference CT, tests
contrast controls, and saves a rendered main-window image alongside the report.
The separate `--smoke-test` checks the image/transform core only.
When updating an installation, replace the `_internal` runtime directory as a
unit (retain a backup), rather than merging old and new DLL files.

## Reference-library configuration and provenance

The runtime library is defined in `config/reference_library.json`, while its
downloadable package version, filename, required file inventory, size, and
SHA-256 checksums are defined in `config/reference_data_catalog.json`. Runtime
paths are resolved from the application folder; processing modules do not hard-code
absolute paths or individual IDs. The manifests pin:

- six reference CTs, corresponding MRI, and LM01-LM13 landmarks;
- validated point-forward transforms from each reference CT to BMA 2.0;
- BMA 2.0 in vivo/ex vivo T2WI, Nissl, myelin, region label map, and color table;
- consensus/inverse grid parameters, deterministic QC sampling, thresholds,
  and provenance metadata.

The J0476M visual-preview profile is fixed in the user interface. ANTs mode
runs the bundled, checksum-verified Windows ANTs executable directly. No Slicer
installation or SlicerANTs extension is required. An explicit standalone runtime
override can be supplied using `MARM_ATLAS_ANTS` (absolute antsRegistration.exe
path); `MARM_ATLAS_SLICER` is no longer used. No implicit runtime or BRAINSFit
fallback is performed. Settings are in `config/ants_registration.json`; see
`docs/ANTS_REGISTRATION.md` for transform conventions and validation. The
current library is prepared with `tools/prepare_manuscript_reference_library.py`.
The exact CTs and fresh landmarks used by the 260918 manuscript analysis are
copied together with CT-to-MRI and MRI-to-Atlas transformations originating in
260911. Exploratory optimized landmark variants are not substituted. Inputs are
verified against the manuscript evaluation's SHA-256 manifest. No runtime path
points outside the installed software/data folder.

The original ITK pull transforms are converted to point-forward transforms and
verified against every intracranial grid point in the manuscript direct routes.
For all six references, the coordinate difference P95 is below 0.01 mm and the
maximum pull/forward round-trip error is below 0.0014 mm. Per-reference values
and source hashes are stored in `data/reference_v2/PROVENANCE.json`.

See `docs/DATA_DISTRIBUTION.md` for archive construction and release steps. The
legacy `*_Atlas_ANTs.h5` files are not required by the current forward consensus
pipeline and are excluded from the public reference-data packages.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Tests cover Rigid and Similarity recovery, label-order invariance,
missing/duplicate/collinear landmarks, identical and known-translation field
means, H5 save/reload coordinate preservation, point-wise arithmetic-mean
agreement, reference-order invariance, vector Atlas layers, and robust inverse
recovery for translation and rotation, six-reference output/reload, previous
four-reference result compatibility, and display-only Window/Level controls.

## Software license and citation

The original Marmoset Atlas Mapper application code and accompanying software
documentation, tests, and build tools are licensed under the [MIT License](LICENSE).
Copyright (c) 2026 Haruya Yagishita. Existing third-party notices and separately
specified licenses take precedence for their respective components.

The software license does not cover Atlas data, reference CT/MRI images,
landmark annotations, derived transforms, or manuscript/research-data packages.
See [data/README.md](data/README.md) for data-specific terms and
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for external components.

If you use Marmoset Atlas Mapper in research, please cite the software repository
and the version used:
https://github.com/H-Yagishita/Marmoset_CT-Atlas_Mapper.
The associated manuscript citation will be added when available. This citation
request is not an additional condition of the MIT License. Attribution
requirements of the Atlas and other third-party materials still apply.

The Windows build includes `LICENSE` and `THIRD_PARTY_NOTICES.md` beside the
executable. Third-party license files are also distributed with the runtime.

## Data licensing

Brain/MINDS BMA 2.0 data are licensed under CC BY 4.0. See `data/README.md`.
Distribution approval for the six reference CT/MRI datasets, landmarks, and derived
transforms is pending confirmation by the data owners; do not publish
`data/reference_v2` or `data/transforms_v2` until approval is recorded.

The large runtime datasets are ignored by Git. They will be archived with the
application and source in the complete Zenodo package, under their respective
licenses; they are not covered by the software's MIT License. Before publication, complete
`PUBLICATION_CHECKLIST.md`, including data permissions, dependency-license
compliance, archive DOI/URLs/checksums, and `CITATION.cff`.
