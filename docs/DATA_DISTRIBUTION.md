# Package contents

The complete Windows release is distributed as one file:
`MarmosetAtlasMapper_v1.00_Windows_Complete.zip`.

Extract the ZIP into a new folder. No separate data download is needed.

```text
MarmosetAtlasMapper/
|-- MarmosetAtlasMapper.exe
|-- _internal/
|-- data/
|   |-- atlas/
|   |-- reference_v2/
|   |-- transforms_v2/
|   `-- README.md
|-- source/
|-- docs/
|-- THIRD_PARTY_LICENSES/
|-- LICENSE
|-- CITATION.cff
`-- README.md
```

The `data` folder must stay beside the executable. Do not rename its
subfolders. The app checks that the required files are present at startup.
`MARM_ATLAS_RESOURCE_ROOT` can point to another folder containing `data/`
when running from source or testing a separate installation.

## Included data

- BMA 2.0 in vivo and ex vivo T2-weighted MRI, Nissl, myelin, region labels,
  and the region color table.
- CT, MRI, and LM01–LM13 landmarks for HH0312F, HH0424M, HH0428M, HJ0285F,
  J0476M, and J0477M.
- Six `*_PointTransform.h5` transforms mapping reference CT points into BMA 2.0.

The reference library uses the images and landmarks from the manuscript's
260918 analysis. Its CT-to-MRI and MRI-to-atlas transforms originate from the
260911 analysis. Exploratory landmark-optimization variants are not included.
The installed package has no dependency on those analysis folders.

`data/reference_v2/PROVENANCE.json` records input hashes and coordinate checks.
The point-forward transforms were checked against the manuscript's direct
mapping routes. For each reference, the 95th-percentile coordinate difference
was below 0.01 mm; the maximum pull/forward round-trip error was below 0.0014 mm.
These are transform-conversion checks, not estimates of anatomical accuracy.

Source files, data, and third-party software keep their respective licenses.
See [data licenses](../data/README.md) and [third-party notices](../THIRD_PARTY_NOTICES.md).

## Storage and verification

The Git repository contains code and configuration, not the large image and
transform files. The complete release includes a source snapshot and records
its Git commit in `RELEASE_BUILD.json`.

`FILE_MANIFEST.json` lists the files in the ZIP and their SHA-256 hashes.
`SHA256SUMS.txt` records the checksum of the ZIP and accompanying documents.
Both are supplied alongside the ZIP. The archive does not contain its own checksum.

When loading transforms from a different Windows drive, the app verifies and
caches the large HDF5 files under
`%LOCALAPPDATA%\MarmosetAtlasMapper\transform_cache`. Images remain in the selected
data folder. This avoids HDF5 read failures seen on some external and mapped drives.

The older `*_Atlas_ANTs.h5` files, analysis outputs, and local caches are not part
of the release. Maintainer instructions are in [ZENODO_RELEASE.md](ZENODO_RELEASE.md).
