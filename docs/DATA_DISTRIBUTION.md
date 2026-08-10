# Reference-data distribution

The application source/executable and the large research data are published
separately. GitHub contains no CT, MRI, or H5 runtime data. Users download one
versioned ZIP from the data repository and place its extracted `data` folder
beside the application executable.

## User installation

1. Download `MarmosetAtlasMapper_Data_v1.0.zip` from the Zenodo record linked
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
|   |-- reference/
|   `-- transforms/
`-- README.md
```

Do not rename the `data`, `atlas`, `reference`, or `transforms` directories.
The application checks the required inventory before opening its main window.
An environment override, `MARM_ATLAS_RESOURCE_ROOT`, remains available for
development and automated testing, but it is not part of the public user flow.

When the software itself is run from an external or mapped Windows drive, the
four large HDF5 transforms are verified against catalog checksums and cached
under `%LOCALAPPDATA%\MarmosetAtlasMapper\transform_cache` before SimpleITK
opens them. CT/MRI images remain in the software `data` folder.

## Archive contents

The single ZIP contains:

- BMA 2.0 in vivo/ex vivo T2WI, Nissl, myelin, region label map, and color table;
- HH0424M, HJ0285F, J0476M, and J0477M CTs and LM01-LM13 landmarks;
- the four validated `*_PointTransform.h5` forward transforms;
- data provenance/attribution and an internal per-file SHA-256 manifest.

The obsolete `*_Atlas_ANTs.h5` transforms, reference MRI, validation-workspace
intermediates, caches, and paper-analysis outputs are not included.

## Maintainer release procedure

Do not build or publish the archive until redistribution permission for all
four reference datasets, landmark annotations, and derived transforms is
documented.

```powershell
.venv\Scripts\python.exe tools\build_reference_data_packages.py `
  --resource-root "X:\path\to\04_Application" `
  --output-dir "X:\path\to\release-data-v1.0"
```

The tool produces:

- `MarmosetAtlasMapper_Data_v1.0.zip`;
- `MarmosetAtlasMapper_Data_v1.0_RELEASE_MANIFEST.json` containing archive size
  and SHA-256.

Upload the ZIP to Zenodo, record its DOI landing page, byte size, and SHA-256 in
`config/reference_data_catalog.json`, then test the documented extraction and
folder-copy workflow on a clean Windows machine.
