# Data sources and licenses

The complete package contains two datasets: the BMA 2.0 atlas and a library of
six reference marmosets. Both are licensed under CC BY 4.0, but they have
different sources and must be credited separately.

## Brain/MINDS Marmoset Brain Atlas 2.0 (`atlas/`)

Source:

> Gong R, et al. Brain/MINDS marmoset brain atlas 2.0: Population cortical
> parcellation with multi-modal templates. *Sci. Data* 13, 274 (2026).
> Paper: https://doi.org/10.1038/s41597-026-06601-z
> Dataset: https://doi.org/10.6084/m9.figshare.29992687

BMA 2.0 is licensed under
[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)
(CC BY 4.0); see `licenses/BrainMINDS-BMA2-CC-BY-4.0.txt`. The files keep their
original names. The app resamples them for display and uses the region labels to
identify mapped locations. When sharing outputs resampled from the atlas,
credit BMA 2.0 and state that the data were resampled. Use of the
atlas does not imply endorsement by its creators or RIKEN.

## Six-marmoset reference library (`reference_v2/`, `transforms_v2/`)

- `reference_v2/`: CT and MR images and landmarks (3D Slicer Markups, LM01–LM13)
  of HH0312F, HH0424M, HH0428M, HJ0285F, J0476M, and J0477M.
- `transforms_v2/`: the CT-to-atlas transform of each reference, combining its
  CT-to-MRI and MRI-to-atlas registrations.
- `reference_v2/PROVENANCE.json`: input checksums and transform checks.

These are the reference images and landmarks used in the related publication,
which describes their acquisition and processing. The library is licensed under
[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)
(CC BY 4.0); see `licenses/ReferenceLibrary-CC-BY-4.0.txt`. When reusing these
data, credit Haruya Yagishita, Yuji Nagai, Yuki Hori, Takafumi Minamimoto, and
Yoshikazu Isomura; link to the dataset and license; and indicate any changes.
The dataset DOI is https://doi.org/10.5281/zenodo.23683937 (reserved until
publication). Please also cite the related publication once it is available.
The library version is **2.0.0**, independent of the application version (1.00).
