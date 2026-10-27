# Package contents

The complete Windows package is distributed on Zenodo
(https://doi.org/10.5281/zenodo.23683937) as a single file,
`MarmosetAtlasMapper_v1.00_Windows_Complete.zip` (about 4.0 GB; allow about 4.5 GB
after extraction). No separate data download is needed.

```text
MarmosetAtlasMapper/
|-- MarmosetAtlasMapper.exe
|-- _internal/                Python, Qt, and ANTs runtime files
|-- data/
|   |-- atlas/                BMA 2.0
|   |-- reference_v2/         Reference CT and MR images, landmarks, provenance
|   |-- transforms_v2/        Reference CT-to-atlas transforms
|   |-- licenses/             Atlas and reference-data licenses
|   `-- README.md
|-- docs/
|-- source/                   Application source code for this release
|-- assets/                   Application icon
|-- THIRD_PARTY_LICENSES/
|-- THIRD_PARTY_SOURCES/      Qt and PySide source archives
|-- README.md
|-- START_HERE.md
|-- CHANGELOG.md
|-- CITATION.cff
|-- LICENSE
|-- THIRD_PARTY_NOTICES.md
`-- RELEASE_BUILD.json        Source commit and build record
```

Keep `data/` next to the executable and do not rename its subfolders; the app
checks at startup that the required files are present. When running from source or
testing another installation, `MARM_ATLAS_RESOURCE_ROOT` can point to a folder
that contains `data/`.

## Data

- BMA 2.0: in vivo and ex vivo T2-weighted MRI, Nissl, myelin, region labels, and
  the region color table.
- CT and MR images and landmarks LM01–LM13 of HH0312F, HH0424M, HH0428M, HJ0285F,
  J0476M, and J0477M.
- Six `*_PointTransform.h5` files that map reference CT points into BMA 2.0. Each
  combines the reference's CT-to-MRI and MRI-to-atlas registrations.

These are the reference images and landmarks used in the associated publication.
`data/reference_v2/PROVENANCE.json` records the input checksums and transform
checks. Each transform was compared with the original mapping route used in the
publication: the 95th-percentile coordinate difference was below 0.01 mm and the
maximum round-trip error was below 0.0014 mm for every reference. These values
verify the conversion of the transforms; they are not estimates of anatomical
accuracy.

See [data/README.md](../data/README.md) and
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) for licenses.

## Verification

`FILE_MANIFEST.json` lists every file in the ZIP with its SHA-256 checksum, and
`SHA256SUMS.txt` gives the checksums of the ZIP and the accompanying files. Both
files are provided alongside the ZIP on Zenodo. `RELEASE_BUILD.json` in the
package records the source commit and the version DOI.

The GitHub repository contains the code and configuration but not the large image
and transform files, which are distributed only in the complete package on Zenodo.

## Transform cache

When the data are on a different drive from the Windows user folder, the app
verifies the large HDF5 transforms and caches them in
`%LOCALAPPDATA%\MarmosetAtlasMapper\transform_cache`, because HDF5 files on some
external or network drives cannot be read reliably. Images are read from the data
folder without caching.
