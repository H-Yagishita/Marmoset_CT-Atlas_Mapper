# Reference-data distribution

GitHub contains no CT, MRI, or H5 runtime data. For v0.3.2, the Windows application,
corresponding source and complete data library are being prepared as one Zenodo
ZIP. It is not published yet; no public record URL or DOI is available.
The software and datasets retain separate licenses even when packaged together.

## User installation

1. Download `MarmosetAtlasMapper_v0.3.2_Windows_Complete.zip` from the final
   Zenodo record once published.
2. Extract into a new folder, not an older installation.
3. Run `MarmosetAtlasMapper/MarmosetAtlasMapper.exe`. No merging of archives,
   Python installation or Slicer installation is needed.

```text
MarmosetAtlasMapper/
|-- MarmosetAtlasMapper.exe
|-- _internal/
|-- data/
|   |-- README.md
|   |-- atlas/
|   |-- reference_v2/
|   `-- transforms_v2/
|-- source/
`-- START_HERE.md
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

- the Windows application/runtime and exact corresponding source snapshot;
- BMA 2.0 in vivo/ex vivo T2WI, Nissl, myelin, region label map, and color table;
- HH0312F, HH0424M, HH0428M, HJ0285F, J0476M, and J0477M CTs, MRI, and LM01-LM13 landmarks;
- the six validated `*_PointTransform.h5` forward transforms;
- data provenance/attribution and an internal per-file SHA-256 manifest.

The obsolete `*_Atlas_ANTs.h5` transforms, validation-workspace
intermediates, caches, and paper-analysis outputs are not included.

## Maintainer release procedure

See [Zenodo preparation](ZENODO_RELEASE.md) for the current complete-package,
version-DOI, verification and publication-approval procedure. Keep checksums
outside the ZIP to avoid a self-referential archive checksum.

## Legacy data-only development helper

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

This helper produces data-only development archives; it is not the current
complete Windows distribution. Do not use its filename/manifest for v0.3.2.
