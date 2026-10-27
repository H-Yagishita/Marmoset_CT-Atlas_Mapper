# Data sources and licenses

The complete package contains the BMA 2.0 atlas and a six-marmoset reference
library. They have different licenses.

## Brain/MINDS Marmoset Brain Atlas 2.0

The files in `atlas/` are from:

> Gong R, et al. The Brain/MINDS 3D Digital Marmoset Brain Atlas Version 2.0.
> https://doi.org/10.6084/m9.figshare.29992687

BMA 2.0 is licensed under
[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)
(CC BY 4.0). A copy of the license is provided in `licenses/`.

The bundled atlas files retain their original filenames. The app resamples
them for display and uses the region labels to identify mapped locations.
Outputs resampled from the atlas should retain the source attribution and
identify the resampling as a modification. Use of the atlas does not imply
endorsement by its authors or RIKEN.

## Six-marmoset reference library

The reference CT/MRI images, landmark annotations, and derived transforms are
distributed under the [MIT License](../LICENSE), as specified by Haruya Yagishita
for this release. This does not change the license of BMA 2.0 or any third-party
material used to produce or display the data.

`reference_v2/` contains CT, MRI, and Slicer Markups for HH0312F, HH0424M,
HH0428M, HJ0285F, J0476M, and J0477M. `transforms_v2/` contains their
CT-to-atlas point-forward transforms. File provenance and transform checks are
recorded in `reference_v2/PROVENANCE.json`.

These are the reference images and landmarks used in the manuscript analysis,
not landmark configurations selected by the earlier optimization experiments.
The library version is **2.0.0**, independent of the application version **1.00**.
