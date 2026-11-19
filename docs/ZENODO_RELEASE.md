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
   for distributing the reference data. Preserve the software MIT notice,
   separate CC BY 4.0 notices for the reference library and BMA 2.0, and
   dependency notices. Review Qt/PySide6 source and library-replacement obligations.
6. Save the verification results beside the archive. Do not include private
   paths, credentials, unpublished analysis outputs, or development logs.

## Zenodo deposit

1. Create a draft record with resource type **Software** and version **1.00**.
2. Confirm the title, creators, description, keywords, and related identifiers.
   `CITATION.cff` describes the software author; add other package contributors
   where appropriate.
3. The DOI reserved for version 1.00 is `10.5281/zenodo.23683937`. Use the existing
   draft rather than reserving another DOI. A reserved DOI is not registered
   until the record is published.
4. Add the DOI to the final citation. If any file inside the ZIP changes,
   rebuild the package and regenerate its checksums.
   For this release, wait for the bioRxiv DOI before rebuilding the complete
   package. Replace its placeholder in README.md, CITATION.cff, data/README.md,
   data/licenses/ReferenceLibrary-CC-BY-4.0.txt, and the local Zenodo metadata.
   Run `tools/check_publication_metadata.py --preparation-dir <release-folder>`;
   the check must pass before building. It checks agreement and DOI syntax,
   not whether the DOI resolves online. Do not mark a reserved DOI as registered.
   Public build records omit DOI registration status; the local deposit metadata
   retains the actual status until publication.
5. Upload the ZIP, file manifest, checksums, and verification report. Check the
   uploaded size and checksum against the local files.
6. Review the draft and publish only after all authors approve it.

For the manuscript, cite the DOI of the version used, not just the concept DOI.
Use **New version** for subsequent software releases, retaining the earlier
version and its source commit.

## Official guidance

- [File uploads](https://help.zenodo.org/docs/deposit/manage-files/)
- [Reserve a DOI](https://help.zenodo.org/docs/deposit/describe-records/reserve-doi/)
- [Manage versions](https://help.zenodo.org/docs/deposit/manage-versions/)
- [Citation metadata](https://help.zenodo.org/docs/github/describe-software/citation-file/)
