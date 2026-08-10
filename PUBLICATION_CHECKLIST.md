# Public-release checklist

## Blocking decisions and permissions

- [ ] Written redistribution approval for HH0424M, HJ0285F, J0476M, and J0477M
  CTs, landmark annotations, and derived point-forward transforms.
- [ ] Final software license selected and a root `LICENSE` added. A permissive
  research-software license such as BSD-3-Clause is a practical option, but the
  copyright holder must make this decision.
- [ ] Copyright holder and year confirmed.
- [ ] Author names, ORCIDs, title, repository URL, and paper/DOI entered in
  `CITATION.cff` after the publication record is available.
- [ ] Institutional policy/privacy review confirms that all imaging data are
  de-identified and suitable for public redistribution.

## Data release

- [ ] Build the single `MarmosetAtlasMapper_Data_v1.0.zip` archive using
  `tools/build_reference_data_packages.py`.
- [ ] Deposit the archive in a permanent DOI repository.
- [ ] Add its byte size, SHA-256 value, and Zenodo landing-page DOI to
  `config/reference_data_catalog.json`.
- [ ] Preserve BMA 2.0 attribution and CC BY 4.0 license text in the data
  deposit.

## Software release

- [ ] Replace "forthcoming" UI/README citation text.
- [ ] Review `THIRD_PARTY_NOTICES.md` against the exact binary dependency set.
- [ ] Publish sanitized paper-validation scripts separately or add their public
  versions; local scripts with absolute study paths are ignored by Git.
- [ ] Run tests and smoke test on a clean Windows machine.
- [ ] Test BRAINSFit discovery with the documented 3D Slicer version.
- [ ] Create a data-free executable using `build_exe.ps1 -SkipData` and verify
  the documented manual extraction, `data`-folder placement, and `Check again` flow.
- [ ] Tag the software release and archive the exact tag in Zenodo for a
  software DOI.
