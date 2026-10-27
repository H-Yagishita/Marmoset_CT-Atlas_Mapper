# Third-party software and data notices

Marmoset Atlas Mapper uses or interoperates with the following third-party
components. The original application software is licensed under the MIT License
(see `LICENSE`; Copyright (c) 2026 Haruya Yagishita). That license does not
relicense third-party software or data. Their original license terms and
attribution requirements continue to apply. Reference imaging data, landmarks,
and derived transforms have separate terms described in `data/README.md`.

- Brain/MINDS Marmoset Brain Atlas 2.0 data — CC BY 4.0. Dataset and citation:
  https://doi.org/10.6084/m9.figshare.29992687
- Python — Python Software Foundation License.
- NumPy — BSD-3-Clause.
- SimpleITK/ITK — Apache License 2.0.
- Qt for Python (PySide6) — LGPLv3/GPLv3/commercial terms; the distributed app
  uses the dynamically linked PySide6 runtime included by the packaging tool.
- PyInstaller — GPLv2-or-later with the exception that permits distribution of
  bundled applications.
- ANTs 2.6.5 — Apache License 2.0, Copyright ConsortiumOfANTS. The Windows
  antsRegistration executable is bundled unmodified from the official ANTsX
  release. Source: https://github.com/ANTsX/ANTs/tree/v2.6.5.
  Runtime provenance, binary checksum, and ANTs/ITK license files are in
  `_internal/ants/Runtime.json` and `_internal/ants/licenses` (source checkout:
  `runtime/ants`). The license collection includes ITK third-party notices;
  inclusion of a notice does not imply every optional ITK module is used.
- Microsoft Visual C++ runtime — external Windows prerequisite. Microsoft
  system/runtime DLLs are not copied from Slicer or from Windows into the ANTs
  bundle. Install the official x64 redistributable if the runtime is missing.

Neither 3D Slicer nor SlicerANTs is required or bundled in version 0.3.1.
BRAINSTools/BRAINSFit is no longer an application registration backend.

Before a public binary release, retain the license files installed with the
exact dependency wheels and review this notice against their shipped metadata.
For Qt/PySide6, verify the licenses of the modules actually distributed, provide
the required license texts and notices, and fulfill the applicable corresponding
source and library replacement/relinking requirements. Dynamic linking and this
summary alone do not establish compliance. See the official Qt guidance:
https://www.qt.io/development/open-source-lgpl-obligations.
