# Marmoset Atlas Mapper

A standalone Windows desktop application for landmark-based mapping between a
user marmoset CT and the Brain/MINDS BMA 2.0 atlas. The K04 reference library
contains HJ0285F, HH0424M, J0476M, and J0477M.

This is a local research prototype. It is not a medical device and is not for
diagnostic or clinical use.

## Current workflow

1. Load a User CT (`.nii`, `.nii.gz`, `.nrrd`, or `.nhdr`).
2. Use the fixed J0476M preview to identify landmarks and place corresponding
   landmarks in the Target CT. Correspondence is by label, never by JSON order.
3. Select a registration type:
   - `Landmark (Skull-base)`: LM01-LM08, four-reference K04 consensus;
   - `Landmark (Skull-all)`: LM01-LM13, four-reference K04 consensus;
   - `General (BRAINSFit)`: LM01-LM13 landmark-rigid initialization to J0476M,
     followed by BRAINSFit Rigid or Similarity intensity registration.
4. Choose Rigid or Similarity and run registration. At least three
   non-collinear common landmarks are required; five or more are recommended.
   Missing landmarks are excluded consistently from every applicable route.
5. Landmark modes construct four complete forward routes:
   `Target CT -> Reference CT -> BMA 2.0`. Each route is sampled on the same
   axis-aligned RAS displacement grid (0.5 mm spacing, 1.0 mm padding), and the
   four forward displacement vectors are averaged with equal weight.
6. Inspect the Quality Check window:
   - Atlas MRI and each transformed reference CT overlaid on the Target CT;
   - reference-wise FRE (placement QC, not an atlas-accuracy proxy);
   - component/consensus field approximation error;
   - RMS, maximum-from-consensus, and maximum-pairwise uncertainty.
7. The application automatically generates 3A, every configured 3B layer, and
   the registration-landmark 3C output. The Atlas viewer opens any saved layer
   in Target CT geometry without recomputing registration.

The lower dock shows a timestamped processing log and can be resized or hidden.
Reference-wise FRE is retained as a numerical landmark-placement QC measure;
there is no single-reference FRE warning, selection, or weighting.

For 3A, the application explicitly solves the inverse on an Atlas-space grid
using a global-affine initialization followed by vectorized Newton iterations.
It writes a convergence mask and evaluates forward-inverse round-trip error.
The inverse transform and Target-CT-in-Atlas image are written only when inverse
QC passes: round-trip P95 below 0.25 mm with at least the configured number of
valid overlap samples. Atlas coverage is saved as descriptive information only
and never gates partial-CT processing; unobserved regions remain zero in 3A.

## K04 output set

The output directory is selected before registration. A successful run writes:

- `Target_CT_to_BMA_MultiRef_K04_Forward.h5`;
- `Target_CT_to_BMA_MultiRef_K04_Displacement.nrrd`;
- four sampled single-reference complete forward transforms in
  `SingleReference/`;
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

General mode writes the corresponding primary forward transform as
`Target_CT_to_BMA_General_J0476M_Forward.h5`, retains the landmark-rigid initial
and BRAINSFit transform/report in `BRAINSFit/`, and produces the same automatic
Atlas-layer, inverse-when-valid, landmark, QC, viewer, and manifest outputs.

`Open results` restores the Target CT, placed landmarks, registration mode,
transform method, QC state, Atlas layers, and interactive viewers without
recomputing registration. `Open Folder` opens the active output directory.

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

The prepared local checkout can also be started with `run_app.bat`.

On first launch, the application checks for the version pinned in
`config/reference_data_catalog.json`. The large runtime data are downloaded
manually from the Zenodo link published in this README:

1. Download `MarmosetAtlasMapper_Data_v1.0.zip`.
2. Extract the ZIP; its top-level content is a folder named `data`.
3. Copy the extracted `data` folder directly beside `MarmosetAtlasMapper.exe`
   (or into the repository root when running from source).
4. Click `Check again` in the application, or restart it.

The final layout must be:

```text
MarmosetAtlasMapper/
|-- MarmosetAtlasMapper.exe
|-- _internal/
|-- data/
|   |-- atlas/
|   |-- reference/
|   `-- transforms/
`-- README.md
```

When an existing library is selected on a different Windows drive, the four
large HDF5 transforms are checksum-verified and cached locally before
SimpleITK opens them. This avoids HDF5 access violations seen on some external
or mapped drives; CT/MRI images themselves remain in the selected library.

The Zenodo landing-page URL and package checksum remain blank until
redistribution permission and the permanent data deposit are complete.

## Build the portable application

```powershell
.\build_exe.ps1
```

The portable application is created at
`dist\MarmosetAtlasMapper\MarmosetAtlasMapper.exe`. The command above retains a
local data-bundled development build. For the public, compact distribution use:

```powershell
.\build_exe.ps1 -SkipData
```

The data-free build displays the manual data-placement instructions on first launch. A
one-directory build is intentional because Qt and SimpleITK are too large for a
practical single-file EXE.

## Reference-library configuration and provenance

The runtime library is defined in `config/reference_library.json`, while its
downloadable package version, filename, required file inventory, size, and
SHA-256 checksums are defined in `config/reference_data_catalog.json`. Runtime
paths are resolved from the application folder; processing modules do not hard-code
absolute paths or individual IDs. The manifests pin:

- four reference CTs and their LM01-LM13 landmarks;
- validated point-forward transforms from each reference CT to BMA 2.0;
- BMA 2.0 in vivo/ex vivo T2WI, Nissl, myelin, region label map, and color table;
- consensus/inverse grid parameters, deterministic QC sampling, thresholds,
  and provenance metadata.

The J0476M visual-preview profile is fixed in the user interface. General mode
discovers an installed 3D Slicer/BRAINSFit runtime without storing an absolute
machine path; `MARM_ATLAS_SLICER` can explicitly point to `Slicer.exe`. The
forward transforms are generated by
`tools/generate_reference_forward_transforms.py`; maximum LM01-LM08
round-trip errors are below 0.0005 mm for all four references.

See `docs/DATA_DISTRIBUTION.md` for archive construction and release steps. The
four legacy `*_Atlas_ANTs.h5` files are not required by the current forward K04
pipeline and are excluded from the public reference-data packages.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Tests cover Rigid and Similarity recovery, label-order invariance,
missing/duplicate/collinear landmarks, identical and known-translation field
means, H5 save/reload coordinate preservation, point-wise arithmetic-mean
agreement, reference-order invariance, vector Atlas layers, and robust inverse
recovery for translation and rotation.

## Data licensing

Brain/MINDS BMA 2.0 data are licensed under CC BY 4.0. See `data/README.md`.
Distribution approval for the four reference CTs, landmarks, and derived
transforms is pending confirmation by the data owners; do not publish
`data/reference` or `data/transforms` until approval is recorded.

The large runtime datasets are ignored by Git and must be published as separate
versioned data assets. Before making this repository public, complete
`PUBLICATION_CHECKLIST.md`, including the project software license, copyright
holder, data permissions, archive DOI/URLs/checksums, and `CITATION.cff`.
