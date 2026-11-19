# Marmoset Atlas Mapper

Marmoset Atlas Mapper maps a CT image of a common marmoset onto the Brain/MINDS
Marmoset Brain Atlas 2.0 (BMA 2.0). No MRI of the animal is needed. The target CT
is registered to the CT images of six reference marmosets whose CT-to-atlas
transforms are already known, and the six resulting mappings are averaged.

The method is described in Yagishita et al. (2026; see [Citation](#citation)).
The software is for research use only.

## Download

The Windows package (application, BMA 2.0, reference data, and source code) is on
Zenodo: https://doi.org/10.5281/zenodo.23683937

Download `MarmosetAtlasMapper_v1.00_Windows_Complete.zip` (about 4 GB), extract
it, and run `MarmosetAtlasMapper.exe`. Python, 3D Slicer, and ANTs are not
required. If Windows reports a missing DLL, install the [Microsoft Visual C++
Redistributable
(x64)](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).

## Usage

1. **Load CT** and open the target CT (`.nii`, `.nii.gz`, `.nrrd`, or `.nhdr`).
2. Place the landmarks. Select a landmark in the table, find it on the reference
   CT (upper panel), and click the same point on the target CT (lower panel).
   Landmarks can also be imported from a 3D Slicer Markups JSON file.
3. Choose the registration type and transform, then **Run registration**.
4. Check the alignment in **Quality Check**. Results are saved to the output
   folder and can be reopened later with **Open results**.

| Registration type | Landmarks | Registration to each reference |
| --- | --- | --- |
| Landmarks (skull base) | LM01–LM08 | Landmark-based |
| Landmarks (total) | LM01–LM13 | Landmark-based |
| ANTs registration | Any of LM01–LM13 | Landmark initialization, then intensity-based |

Each type can use a rigid or a similarity (rigid + uniform scale) transform. At
least three landmarks are needed, and we recommend five or more. Landmarks are
matched by label, not by their order in the file. The skull-base and total sets
are the Bottom and Total sets in the paper.

The references are HH0312F, HH0424M, HH0428M, HJ0285F, J0476M, and J0477M, and
all six are weighted equally. J0476M is shown as the guide image for landmark
placement.

The quality checks in the app confirm that the transforms are numerically
consistent; they do not tell you whether the mapping is anatomically correct.
Always look at the overlays, particularly for CT scans with implants or a small
field of view.

More details:

- [docs/OUTPUTS.md](docs/OUTPUTS.md): output files, coordinates, and checks
- [docs/ANTS_REGISTRATION.md](docs/ANTS_REGISTRATION.md): ANTs settings
- [docs/DATA_DISTRIBUTION.md](docs/DATA_DISTRIBUTION.md): package contents

## Running from source

Requires Python 3.12 on Windows.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

The image and transform data are not in this repository. Copy the `data` folder
from the Zenodo package into the source folder, or set `MARM_ATLAS_RESOURCE_ROOT`
to the folder that contains it. ANTs registration also needs the standalone ANTs
runtime ([instructions](docs/ANTS_REGISTRATION.md#building-the-standalone-runtime)).

Tests and the Windows build:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
.\build_exe.ps1 -SkipData
```

## License

The code and documentation are under the [MIT License](LICENSE). The reference
data and BMA 2.0 are under CC BY 4.0 (see [data/README.md](data/README.md)), and
bundled third-party software keeps its own licenses (see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)).

## Citation

If you use this software, please cite:

1. Yagishita H, Kawabata M, Nagai Y, Hori Y, Hirayama Y, Ebina T, Sehara K,
   Oyama K, Matsuzaki M, Minamimoto T, Isomura Y. A CT-to-atlas mapping
   framework using skull-base landmarks in marmosets. *bioRxiv* (2026).
   https://doi.org/10.1101/TODO_BIORXIV_DOI
2. Yagishita H. Marmoset Atlas Mapper (version 1.00). Zenodo (2026).
   https://doi.org/10.5281/zenodo.23683937

If you use the reference data or BMA 2.0, please also credit them as described in
[data/README.md](data/README.md).

## Contact

Please report problems on the GitHub issue tracker.
