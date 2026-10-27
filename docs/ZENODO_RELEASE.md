# Zenodo complete-package preparation

Status: unpublished preparation for v0.3.2. No DOI has been invented or assigned
in this source tree. Do not publish the older v0.3.1 draft: it predates the
Windows Unicode-path fix.

## Distribution layout

- GitHub: version-controlled source, issues and tests.
- Zenodo: one `MarmosetAtlasMapper_v0.3.2_Windows_Complete.zip`, containing the
  Windows application, exact corresponding source, BMA 2.0, all six reference
  CT/MRI/landmark sets, and six CT-to-atlas point-forward transforms.
- Alongside the ZIP: SHA256SUMS.txt, file manifest, validation report and
  installation/publication instructions.

The complete ZIP is uploaded directly to a Zenodo draft. Do not assume that
GitHub integration also archives manually attached executable/data assets.
GitHub's 2 GiB release-asset limit does not apply to the Zenodo ZIP. Zenodo's
documented default record quota is 50 GB, which is sufficient for this package.

## Before publication

1. Pass local tests, Windows GitHub Actions, and tests of the extracted executable.
2. Confirm the six-reference data owners' redistribution approval and license.
   Software copyright ownership does not establish research-data permissions.
3. Review the exact bundled dependencies' redistribution obligations, including
   Qt/PySide6 licenses, corresponding source and library replacement.
4. Confirm the complete-package creators/contributors, order, affiliations and
   any ORCIDs; CITATION.cff currently describes the original software author.
5. Sign in to the intended Zenodo account; create/save a draft, not a public record.
6. Reserve a DOI in the draft ("No" existing DOI, then "Get a DOI now!").
   A reserved DOI is not yet registered/publicly resolvable. Keep the draft.
7. Record the exact version DOI and record URL, update the citation and manuscript,
   and repackage/re-hash if any bundled file changes. Do not label the mixed
   package as entirely MIT: retain BMA CC BY 4.0 and all component-specific terms.
8. Upload the full ZIP and supporting files; verify the server-side size/checksum.
9. Check installation on a clean Windows PC. Build-host smoke tests are not
   equivalent to clean-machine certification.
10. Obtain explicit author approval before publishing the Zenodo record, making
    GitHub public or publishing a GitHub Release. The present preparation task
    authorizes none of those public-exposure actions.

For the manuscript, cite the DOI of the specific archived version, not only the
all-versions/concept DOI. For substantive subsequent changes create a new version.
Preserve the archived ZIP's SHA256 and source commit in the validation manifest.

Official references (checked 2026-10-27):
- https://help.zenodo.org/docs/deposit/manage-files/
- https://help.zenodo.org/docs/deposit/describe-records/reserve-doi/
- https://help.zenodo.org/docs/deposit/manage-versions/
- https://help.zenodo.org/docs/github/describe-software/citation-file/
