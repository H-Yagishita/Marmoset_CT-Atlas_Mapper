# Marmoset Atlas Mapper

Marmoset Atlas Mapper maps a marmoset CT image to the Brain/MINDS Marmoset
Brain Atlas 2.0 (BMA 2.0), without requiring an MRI of that animal. It registers
the target CT to six reference marmosets and averages the six mappings into
atlas space.

Version **1.00** is the first public release. The standalone Windows package
includes the executable, source code, atlas, reference images, landmarks, and
transforms. Python, 3D Slicer, and SlicerANTs do not need to be installed.

The software is intended for research. It has not been validated for diagnosis
or clinical use. This describes its intended use, not a restriction on the MIT
License.

## Getting started

1. Extract `MarmosetAtlasMapper_v1.00_Windows_Complete.zip` into a new folder.
2. Open `MarmosetAtlasMapper.exe`. Keep the `_internal` and `data` folders beside it.
3. Click **Load CT** and select a NIfTI or NRRD image (`.nii`, `.nii.gz`, `.nrrd`,
   or `.nhdr`). For detached NRRD files, keep the header and data file together.
4. Select a landmark in the table. Use the reference CT in the upper panel to
   locate the corresponding point, then click that point in the target CT below.
   You can also import landmarks from a Slicer Markups JSON file.
5. Select a registration type and transform, then click **Run registration**.
   Choose an output folder. If it already contains files, the app creates a new
   run subfolder.
6. Inspect the alignment in **Quality Check**. Results are saved automatically.
   Use **Open results** to return to a saved run.

The application uses a 64-bit Windows runtime. A local installation folder is
recommended. If Windows reports a missing Microsoft Visual C++ runtime, install
the current [Microsoft x64 redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).
Allow space for the extracted package, temporary files, and registration outputs;
the compressed ZIP size is not the total disk space required.

## Registration options

| Registration type | Landmarks | Registration to each reference CT |
| --- | --- | --- |
| Landmarks (skull base) | LM01–LM08 | Landmark-based rigid or similarity transform |
| Landmarks (total) | LM01–LM13 | Landmark-based rigid or similarity transform |
| ANTs registration | Available points from LM01–LM13 | Landmark initialization, followed by intensity-based rigid or similarity registration |

Rigid registration allows rotation and translation. Similarity registration also
allows a single, uniform scale factor. ANTs registration uses the CT images
without a bone mask.

At least three non-collinear landmarks shared by the target and all references
are required. Five or more are recommended. Landmarks are matched by label,
not by their order in the file. The same valid subset is used for all six references.

The references are HH0312F, HH0424M, HH0428M, HJ0285F, J0476M, and J0477M.
J0476M is shown as a placement guide; all six contribute equally to the mapping.
`Nref` denotes the number of reference marmosets, which is six in this version.

## Viewing and checking results

- **Window** and **Level** adjust display contrast without changing image values
  or registration. **Reset contrast** restores the automatic display range.
- In **Quality Check**, green shows the target CT and red shows the atlas MRI
  or a registered reference CT. Each channel has its own contrast controls.
- **Atlas Viewer** displays the atlas MRI, Nissl, myelin, and region-label layers
  in target CT space.
- **Open output folder** opens the saved files. **View → Processing log** shows
  progress and diagnostic messages.

A numerical QC pass checks the calculation of the transforms; it does not confirm
anatomical accuracy. Inspect each result. Landmark residuals and between-reference
disagreement are saved as diagnostics, not as estimates of the true localization
error. The target CT in atlas space is saved only if the inverse transform passes QC.

See the [output guide](docs/OUTPUTS.md) for file names, coordinate conventions,
and numerical QC details.

## Source code and development

The source repository is
[H-Yagishita/Marmoset_CT-Atlas_Mapper](https://github.com/H-Yagishita/Marmoset_CT-Atlas_Mapper).
Each complete package also contains the corresponding source under `source/`.

To run from source on Windows with Python 3.12:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Copy the complete package's `data` folder into the source directory, or set
`MARM_ATLAS_RESOURCE_ROOT` to the application folder that contains it. For ANTs,
prepare the [standalone runtime](docs/ANTS_REGISTRATION.md#building-the-standalone-runtime)
or set `MARM_ATLAS_ANTS` to an existing `antsRegistration.exe` from that runtime.
Then run:

```powershell
.venv\Scripts\python.exe app.py
```

To test or build the app, install `requirements-dev.txt` and run:

```powershell
.venv\Scripts\python.exe -m pytest -q
.\build_exe.ps1 -SkipData
```

The build requires the pinned ANTs runtime. It creates the application under
`dist/MarmosetAtlasMapper/`; the complete release adds the data library and source.
See [distribution details](docs/DATA_DISTRIBUTION.md) and the
[release checklist](PUBLICATION_CHECKLIST.md).

## License and citation

The original application code, documentation, and six-reference CT/MRI,
landmark, and transform data are distributed under the [MIT License](LICENSE).
Copyright (c) 2026 Haruya Yagishita.

BMA 2.0 is distributed under **CC BY 4.0** and requires attribution to its
creators. See [data attribution and licenses](data/README.md). Third-party
software retains its own license; see [third-party notices](THIRD_PARTY_NOTICES.md).

When reporting work that uses Marmoset Atlas Mapper, please cite the software
version and its version-specific archive DOI. Citation metadata are provided in
`CITATION.cff`; the archive record supplies the DOI. Please also cite BMA 2.0.
The software citation request does not add a condition to the MIT License.

## Support

Report problems through the repository's issue tracker. Include the app version,
Windows version, error message, and steps needed to reproduce the problem.
Remove private paths or unpublished data before attaching logs.
