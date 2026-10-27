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

- [ ] Build and validate `MarmosetAtlasMapper_v0.3.2_Windows_Complete.zip`
  containing executable, source and reference/atlas data.
- [ ] Deposit the archive in a permanent DOI repository.
- [ ] Record ZIP size and SHA-256 in the external package manifest; add the
  real version DOI to the citation/README/catalog. Do not embed a ZIP's checksum
  inside that same ZIP.
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
- [ ] Rebuild the executable and verify the complete ZIP after extraction,
  including Japanese-path I/O, Qt startup and standalone ANTs.
- [ ] Cite the exact complete-package version DOI in the manuscript; keep its
  source commit and file hashes in the manifest. Publish only with author approval.
