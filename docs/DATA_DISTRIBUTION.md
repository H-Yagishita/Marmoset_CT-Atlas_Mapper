# Reference-data distribution

The application source/executable and the large research data are distributed
separately. GitHub contains no CT, MRI, or H5 runtime data. The public data deposit
is still being prepared; no public download URL is available yet. After release,
users will download one versioned ZIP from the data repository and place its
extracted `data` folder beside the application executable.

## User installation

1. Download `MarmosetAtlasMapper_Data_v2.0.zip` from the Zenodo record linked
   in the GitHub README.
2. Extract the ZIP. Its top-level content is the `data` folder.
3. Copy `data` directly into the software folder.
4. Start the application, or click `Reference Data` -> `Check again` if it is
   already open.

```text
MarmosetAtlasMapper/
|-- MarmosetAtlasMapper.exe
|-- _internal/
|-- data/
|   |-- README.md
|   |-- PACKAGE_MANIFEST.json
|   |-- atlas/
|   |-- reference_v2/
|   `-- transforms_v2/
`-- README.md
```

Do not rename the `data`, `atlas`, `reference_v2`, or `transforms_v2` directories.
The application checks the required inventory before opening its main window.
An environment override, `MARM_ATLAS_RESOURCE_ROOT`, remains available for
development and automated testing, but it is not part of the public user flow.

When the software itself is run from an external or mapped Windows drive, the
six large HDF5 transforms are verified against catalog checksums and cached
under `%LOCALAPPDATA%\MarmosetAtlasMapper\transform_cache` before SimpleITK
opens them. CT/MRI images remain in the software `data` folder.

## Archive contents

The single ZIP contains:

- BMA 2.0 in vivo/ex vivo T2WI, Nissl, myelin, region label map, and color table;
- HH0312F, HH0424M, HH0428M, HJ0285F, J0476M, and J0477M CTs, MRI, and LM01-LM13 landmarks;
- the six validated `*_PointTransform.h5` forward transforms;
- data provenance/attribution and an internal per-file SHA-256 manifest.

The obsolete `*_Atlas_ANTs.h5` transforms, validation-workspace
intermediates, caches, and paper-analysis outputs are not included.

## Maintainer release procedure

Local test archives may be built before publication. Do not upload or publish
until redistribution permission for all six reference datasets, landmark
annotations, and derived transforms is documented.

```powershell
.venv\Scripts\python.exe tools\build_reference_data_packages.py `
  --resource-root "X:\path\to\04_Application" `
  --output-dir "X:\path\to\release-data-v2.0"
```

The tool produces:

- `MarmosetAtlasMapper_Data_v2.0.zip`;
- `MarmosetAtlasMapper_Data_v2.0_RELEASE_MANIFEST.json` containing archive size
  and SHA-256.

Upload the ZIP to Zenodo, record its DOI landing page, byte size, and SHA-256 in
`config/reference_data_catalog.json`, then test the documented extraction and
folder-copy workflow on a clean Windows machine.
