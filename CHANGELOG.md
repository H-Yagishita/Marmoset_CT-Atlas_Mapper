# Release notes

## 1.00

- Exclude unused Qt plugins and include matching Qt/PySide source archives in
  the complete package.

- Revised the interface text and documentation for the public release.
- Standardized the terms "target CT", "reference", and "atlas" throughout the app.
- Updated installation instructions for the complete, single-ZIP package.
- Retained the Japanese-path fix from version 0.3.2.
- Included the six-reference library and standalone ANTs 2.6.5 runtime.

Registration algorithms, parameters, reference images, landmark coordinates,
and transforms are unchanged from version 0.3.2. Existing results are not recomputed.

## 0.3.2

Fixed image loading on Windows when Japanese or other non-ASCII paths were
converted to short filenames that lost the original extension. Images and
transforms now use temporary ASCII paths while preserving the file type.

## 0.3.1

Replaced the SlicerANTs dependency with the bundled standalone ANTs runtime.
ANTs uses the same six-reference averaging workflow as landmark registration.
