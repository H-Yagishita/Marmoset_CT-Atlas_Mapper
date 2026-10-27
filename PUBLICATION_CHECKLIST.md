# Public-release checklist

## Metadata and permissions

- [x] Application and reference-data license: MIT, selected by Haruya Yagishita.
- [x] Software copyright: Copyright (c) 2026 Haruya Yagishita.
- [x] BMA 2.0 attribution and CC BY 4.0 license retained.
- [ ] Confirm institutional and third-party redistribution requirements.
- [ ] Confirm the final creator list, affiliations, and optional ORCIDs.
- [ ] Add the version DOI and any available manuscript citation.

## Package checks

- [ ] Build `MarmosetAtlasMapper_v1.00_Windows_Complete.zip` from the recorded source commit.
- [ ] Pass unit tests and Windows CI.
- [ ] Verify every archived file and the 31 required data files against their hashes.
- [ ] Test the extracted executable: startup, Japanese-path I/O, GUI, and ANTs.
- [ ] Save a run and reopen its images, landmarks, and viewer settings.
- [ ] Check the exact dependency inventory, license texts, source archives, and replacement instructions.
- [ ] Test on a clean Windows PC without Python, 3D Slicer, or ANTs installed.
- [ ] Review packaged provenance and logs for information that should not be public.

## Deposit

- [ ] Save a Zenodo draft for version 1.00 and reserve its DOI.
- [ ] Upload the complete ZIP, file manifest, checksums, and verification report.
- [ ] Verify the uploaded size and checksum.
- [ ] Cite the version DOI in the manuscript.
- [ ] Obtain author approval before publishing the record or making GitHub public.

This is a maintainer checklist. The release-specific verification report records
which technical checks have passed; unchecked items here should not be taken as
completed.
