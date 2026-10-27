# Marmoset Atlas Mapper

Marmoset Atlas Mapper is a Windows application that maps a CT image of a common
marmoset to the Brain/MINDS Marmoset Brain Atlas 2.0 (BMA 2.0) without requiring
MRI of that animal. The target CT is registered to the CT images of six reference
marmosets, each of which has a precomputed CT-to-atlas transform, and the six
resulting mappings are averaged with equal weights.

Version **1.00** is the first public release. The complete package (application,
data, and source code) is available from Zenodo
(https://doi.org/10.5281/zenodo.23683937), and the source code is maintained on
GitHub. The software is intended for research use and has not been validated for
diagnostic or clinical use.

## System requirements

- 64-bit Windows.
- About 4.5 GB of free disk space for the extracted package, plus space for
  temporary files and results.
- Microsoft Visual C++ Redistributable (x64). If Windows reports that it is
  missing, install the [latest
  version](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).

Python, 3D Slicer, and ANTs do not need to be installed.

## Quick start

1. Download `MarmosetAtlasMapper_v1.00_Windows_Complete.zip` from the Zenodo
   record and extract it into a new local folder.
2. Start `MarmosetAtlasMapper.exe`. Keep it in the same folder as `_internal` and
   `data`.
3. Click **Load CT** and select the target CT (`.nii`, `.nii.gz`, `.nrrd`, or
   `.nhdr`). For a detached-header NRRD (`.nhdr`), keep the header and data files
   in the same folder.
4. Place the landmarks. Select a landmark in the table, find it in the reference
   CT shown in the upper panel, and click the corresponding point in the target CT
   in the lower panel. Landmarks can also be imported from a 3D Slicer Markups
   JSON file.
5. Choose the registration type and transform (see below), then click **Run
   registration** and select an output folder. If the folder is not empty, a new
   subfolder is created for the run.
6. Check the alignment in **Quality Check**. Results are saved automatically; use
   **Open results** to reopen a saved run.

## Registration options

| Registration type | Landmarks used | Registration to each reference CT |
| --- | --- | --- |
| Landmarks (skull base) | LM01–LM08 | Landmark-based, rigid or similarity |
| Landmarks (total) | LM01–LM13 | Landmark-based, rigid or similarity |
| ANTs registration | Available landmarks among LM01–LM13 | Landmark initialization, then intensity-based rigid or similarity registration |

- **Rigid** allows rotation and translation. **Similarity** also allows one
  uniform scale factor.
- ANTs registration uses the entire CT images without a bone mask.
- At least three non-collinear landmarks shared by the target and all references
  are required; five or more are recommended. Landmarks are matched by label
  (e.g., `LM01`), not by their order in the file, and the same subset is used for
  all six references.

The skull-base and total sets correspond to the Bottom and Total landmark sets in
the associated publication (see [Citation](#citation)).

The six references are HH0312F, HH0424M, HH0428M, HJ0285F, J0476M, and J0477M. All
six contribute equally to the mapping. J0476M is also displayed as a guide for
landmark placement but receives no additional weight. `Nref6` in output file names
indicates that six references were used.

## Checking results

- **Window** and **Level** change the display contrast only; they do not change
  image values or the registration. **Reset contrast** restores the default range.
- In **Quality Check**, green shows the target CT and red shows the atlas MRI or a
  registered reference CT. Each channel has its own contrast controls.
- **Atlas Viewer** shows the atlas MRI, Nissl, myelin, and region labels in target
  CT space.
- **Open output folder** opens the saved files. **View → Processing log** shows
  progress and error messages.

The numerical quality checks assess the consistency of the transforms; they do not
confirm anatomical accuracy. Inspect every result visually, especially for CT
images with implants or limited coverage. Landmark residuals and the disagreement
among references are saved as diagnostics, not as estimates of the mapping error.
The target CT in atlas space is saved only if the inverse transform passes its
check.

See [docs/OUTPUTS.md](docs/OUTPUTS.md) for the output files, coordinate
conventions, and quality checks.

## Running from source

The source code is available at
[H-Yagishita/Marmoset_CT-Atlas_Mapper](https://github.com/H-Yagishita/Marmoset_CT-Atlas_Mapper);
the complete package also includes the source code of this release in `source/`.
With Python 3.12 on Windows:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Before starting the app, copy the `data` folder of the complete package into the
source folder, or set `MARM_ATLAS_RESOURCE_ROOT` to a folder that contains it.
ANTs registration also requires the standalone ANTs runtime (see
[docs/ANTS_REGISTRATION.md](docs/ANTS_REGISTRATION.md#building-the-standalone-runtime))
or the `MARM_ATLAS_ANTS` environment variable set to an `antsRegistration.exe`
from that runtime. Then start the app:

```powershell
.venv\Scripts\python.exe app.py
```

To run the tests and build the executable, install the packages listed in
`requirements-dev.txt` and run:

```powershell
.venv\Scripts\python.exe -m pytest -q
.\build_exe.ps1 -SkipData
```

The build is written to `dist/MarmosetAtlasMapper/` and does not include the
`data` folder. See [docs/DATA_DISTRIBUTION.md](docs/DATA_DISTRIBUTION.md) for the
contents of the complete package.

## Licenses

- Application code and documentation: [MIT License](LICENSE), Copyright (c) 2026
  Haruya Yagishita.
- Reference data of the six marmosets (CT and MR images, landmarks, and transforms
  in `data/reference_v2/` and `data/transforms_v2/`): CC BY 4.0 (see
  [data/README.md](data/README.md)).
- BMA 2.0: CC BY 4.0, with attribution to its creators (see
  [data/README.md](data/README.md)).
- Bundled third-party software: the respective licenses (see
  [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).

## Citation

If you use Marmoset Atlas Mapper, please cite both the software version and the
associated publication:

1. Yagishita H. Marmoset Atlas Mapper (version 1.00). Zenodo (2026).
   https://doi.org/10.5281/zenodo.23683937
2. Yagishita H, Kawabata M, Nagai Y, Hori Y, Hirayama Y, Ebina T, Sehara K,
   Oyama K, Matsuzaki M, Minamimoto T, Isomura Y. A CT-to-atlas mapping
   framework using skull-base landmarks in marmosets. *bioRxiv* (2026).
   https://doi.org/10.1101/TODO_BIORXIV_DOI

If you use the bundled reference data or BMA 2.0, also credit them as described
in [data/README.md](data/README.md). Citation metadata are provided in
[CITATION.cff](CITATION.cff).

## Support

Report problems through the GitHub issue tracker. Include the app version, the
Windows version, the error message, and the steps that reproduce the problem.
Remove private paths and unpublished data from any logs you attach.
