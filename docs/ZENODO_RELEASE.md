# Preparing a release

Use GitHub for source development and Zenodo for the versioned complete package.
The Windows package includes the executable, corresponding source, BMA 2.0,
and all six reference datasets. Upload it directly to Zenodo; do not assume
that GitHub integration includes manually attached release assets.

## Release checks

1. Update the app version, package filename, citation metadata, and release notes.
   The public version label is **1.00**. Python packaging may normalize it to
   `1.0`; the Windows numeric version is `1.0.0.0`.
2. Run the test suite and Windows CI. Build into a new output folder.
3. Package the exact source commit with the executable and data. Verify the
   data against the catalog, then extract the finished ZIP and check every hash.
4. Test image and transform I/O with Japanese paths, GUI startup, contrast
   controls, saved results, and the bundled ANTs runtime. Test installation on
   a clean Windows computer without Python, Slicer, or ANTs.
5. Confirm contributor details and any institutional or third-party requirements
   for distributing the reference data. Preserve the MIT, BMA CC BY 4.0, and
   dependency notices. Review Qt/PySide6 source and library-replacement obligations.
6. Save the verification results beside the archive. Do not include private
   paths, credentials, unpublished analysis outputs, or development logs.

## Zenodo deposit

1. Create a draft record with resource type **Software** and version **1.00**.
2. Confirm the title, creators, description, keywords, and related identifiers.
   `CITATION.cff` describes the software author; add other package contributors
   where appropriate.
3. Reserve the version DOI if the record does not already have one. A reserved
   DOI is not registered until the record is published.
4. Add the DOI to the final citation. If any file inside the ZIP changes,
   rebuild the package and regenerate its checksums.
5. Upload the ZIP, file manifest, checksums, and verification report. Check the
   uploaded size and checksum against the local files.
6. Review the draft and publish only after the author approves it. A release
   preparation task does not authorize publication or a repository visibility change.

For the manuscript, cite the DOI of the version used, not just the concept DOI.
Use **New version** for subsequent software releases, retaining the earlier
version and its source commit.

## Official guidance

- [File uploads](https://help.zenodo.org/docs/deposit/manage-files/)
- [Reserve a DOI](https://help.zenodo.org/docs/deposit/describe-records/reserve-doi/)
- [Manage versions](https://help.zenodo.org/docs/deposit/manage-versions/)
- [Citation metadata](https://help.zenodo.org/docs/github/describe-software/citation-file/)
