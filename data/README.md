# Runtime data

The MIT License for Marmoset Atlas Mapper's software does not apply to the
datasets, landmark annotations, or derived transforms in this directory.
Their licensing and redistribution terms are specified separately below.

## Brain/MINDS BMA 2.0

The files under `atlas/` are from:

> Gong R, et al. The Brain/MINDS 3D Digital Marmoset Brain Atlas Version 2.0.
> https://doi.org/10.6084/m9.figshare.29992687

License: Creative Commons Attribution 4.0 International (CC BY 4.0)
https://creativecommons.org/licenses/by/4.0/

Files are retained with their original filenames and are used for image
resampling and region lookup. The application does not claim endorsement by
the Brain/MINDS authors or RIKEN.

## Reference CT/MRI data (version 2.0)

`reference_v2/` contains HH0312F, HH0424M, HH0428M, HJ0285F, J0476M, and J0477M
CT/MRI images and Slicer Markups from the 260918 manuscript analysis.
`transforms_v2/` contains the six validated `*_PointTransform.h5` forward mappings
to BMA 2.0, derived from the CT-to-MRI and MRI-to-Atlas transforms originating in
260911. Source hashes and coordinate checks are recorded in
`reference_v2/PROVENANCE.json`. There is no dependency on the analysis folder. Legacy
`*_Atlas_ANTs.h5` files remain local and are not distributed with the app.

These files are local research data. Redistribution/public-release permission
must be confirmed by the data owners and responsible institution before this
repository is made public.
No public reuse license for these reference data is granted by the software's
MIT License. Record the approved data license here before releasing them.
