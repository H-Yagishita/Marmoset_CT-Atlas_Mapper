# Public-release checklist

## Metadata and permissions

- [x] Application code and documentation: MIT. Reference data: CC BY 4.0.
- [x] Software copyright: Copyright (c) 2026 Haruya Yagishita.
- [x] BMA 2.0 attribution and CC BY 4.0 license retained.
- [x] Reference-data redistribution permission confirmed by Haruya Yagishita.
- [x] Reference-data rights holders: Haruya Yagishita, Yuji Nagai, Yuki Hori, Takafumi Minamimoto, and Yoshikazu Isomura.
- [ ] Confirm the final creator list, affiliations, and optional ORCIDs.
- [x] Reserved version DOI: 10.5281/zenodo.23683937.
- [ ] Add the publication date and manuscript citation when available.

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

- [x] Version DOI reserved by the author for the Zenodo draft.
- [ ] Upload the complete ZIP, file manifest, checksums, and verification report.
- [ ] Verify the uploaded size and checksum.
- [ ] Cite the version DOI in the manuscript.
- [ ] Obtain author approval before publishing the record or making GitHub public.

This is a maintainer checklist. The release-specific verification report records
which technical checks have passed; unchecked items here should not be taken as
completed.
