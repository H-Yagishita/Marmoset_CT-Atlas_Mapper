# Package contents

The complete Windows package is a single ZIP file on Zenodo
(https://doi.org/10.5281/zenodo.23683937),
`MarmosetAtlasMapper_v1.00_Windows_Complete.zip`. It is about 4.0 GB and needs
about 4.5 GB after extraction. No other download is needed.

```text
MarmosetAtlasMapper/
|-- MarmosetAtlasMapper.exe
|-- _internal/                Python, Qt, and ANTs runtime
|-- data/
|   |-- atlas/                BMA 2.0
|   |-- reference_v2/         Reference CT and MR images, landmarks
|   |-- transforms_v2/        Reference CT-to-atlas transforms
|   |-- licenses/
|   `-- README.md
|-- docs/
|-- source/                   Source code of this release
|-- assets/
|-- THIRD_PARTY_LICENSES/
|-- THIRD_PARTY_SOURCES/      Qt and PySide source archives
|-- README.md
|-- START_HERE.md
|-- CHANGELOG.md
|-- CITATION.cff
|-- LICENSE
|-- THIRD_PARTY_NOTICES.md
`-- RELEASE_BUILD.json        Source commit and build information
```

Keep `data/` next to the executable and do not rename its subfolders. To use the
data from another location, set `MARM_ATLAS_RESOURCE_ROOT` to the folder that
contains `data/`.

## Data

- BMA 2.0: in vivo and ex vivo T2-weighted MR images, Nissl, myelin, region
  labels, and the color table.
- CT and MR images and landmarks LM01–LM13 of the six reference marmosets
  (HH0312F, HH0424M, HH0428M, HJ0285F, J0476M, J0477M), as used in the paper.
- One `*_PointTransform.h5` per reference, mapping CT points into BMA 2.0
  (CT-to-MR and MR-to-atlas registrations combined).

The transforms were converted from those used in the paper. After conversion, the
95th-percentile coordinate difference from the original was below 0.01 mm and the
round-trip error below 0.0014 mm for every reference. Checksums and these checks
are recorded in `data/reference_v2/PROVENANCE.json`.

Licenses are described in [data/README.md](../data/README.md) and
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## Checksums

`FILE_MANIFEST.json` (SHA-256 of every file in the ZIP) and `SHA256SUMS.txt`
(SHA-256 of the ZIP and accompanying files) are on the Zenodo record next to the
ZIP.

The GitHub repository has the code and configuration only; the image and
transform files are distributed on Zenodo.

## Transform cache

If the data are on a different drive from your Windows user folder, the large
HDF5 transforms are copied to
`%LOCALAPPDATA%\MarmosetAtlasMapper\transform_cache` before use, because HDF5
files on some external or network drives cannot be read reliably.
