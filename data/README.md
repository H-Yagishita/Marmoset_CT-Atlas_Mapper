# Runtime data

## Brain/MINDS BMA 2.0

The files under `atlas/` are from:

> Gong R, et al. The Brain/MINDS 3D Digital Marmoset Brain Atlas Version 2.0.
> https://doi.org/10.6084/m9.figshare.29992687

License: Creative Commons Attribution 4.0 International (CC BY 4.0)
https://creativecommons.org/licenses/by/4.0/

Files are retained with their original filenames and are used for image
resampling and region lookup. The application does not claim endorsement by
the Brain/MINDS authors or RIKEN.

## Reference CT data

`reference/` contains the HJ0285F, HH0424M, J0476M, and J0477M CTs and Slicer
Markups selected in the validation workspace. `transforms/` contains the
validated mappings between each reference CT and BMA 2.0. The public runtime
package uses only the four `*_PointTransform.h5` forward mappings; legacy
`*_Atlas_ANTs.h5` files remain local and are not distributed with the app.

These files are local research data. Redistribution/public-release permission
must be confirmed by the data owners and responsible institution before this
repository is made public.
