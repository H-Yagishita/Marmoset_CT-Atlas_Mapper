# Public-release checklist

## Blocking decisions and permissions

- [ ] Written redistribution approval for HH0312F, HH0424M, HH0428M, HJ0285F,
  J0476M, and J0477M CT/MRI data, landmark annotations, and derived point-forward transforms.
- [x] MIT License selected for the original application software; root `LICENSE`
  added. Data and third-party components retain their separate terms.
- [x] Copyright notice confirmed by the author on 2026-10-23:
  Copyright (c) 2026 Haruya Yagishita.
- [ ] Author names, ORCIDs, title, repository URL, and paper/DOI entered in
  `CITATION.cff` after the publication record is available.
- [ ] Institutional policy/privacy review confirms that all imaging data are
  de-identified and suitable for public redistribution.

## Data release

- [ ] Build the single `MarmosetAtlasMapper_Data_v2.0.zip` archive using
  `tools/build_reference_data_packages.py`.
- [ ] Deposit the archive in a permanent DOI repository.
- [ ] Add its byte size, SHA-256 value, and Zenodo landing-page DOI to
  `config/reference_data_catalog.json`.
- [ ] Preserve BMA 2.0 attribution and CC BY 4.0 license text in the data
  deposit.

## Software release

- [ ] Add the manuscript citation when its publication record is available.
- [ ] Review `THIRD_PARTY_NOTICES.md` against the exact binary dependency set.
- [ ] Verify Qt/PySide6 license notices, corresponding-source provision, and
  library replacement/relinking requirements for the exact Windows bundle.
- [ ] Publish sanitized paper-validation scripts separately or add their public
  versions; local scripts with absolute study paths are ignored by Git.
- [ ] Run tests and smoke test on a clean Windows machine.
- [ ] Test the bundled ANTs runtime on a machine without 3D Slicer/SlicerANTs.
- [ ] Create a data-free executable using `build_exe.ps1 -SkipData` and verify
  the documented manual extraction, `data`-folder placement, and `Check again` flow.
- [ ] Tag the software release and archive the exact tag in Zenodo for a
  software DOI.
