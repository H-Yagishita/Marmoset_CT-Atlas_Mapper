# Third-party notices

The original Marmoset Atlas Mapper code and six-reference data library are
distributed under the MIT License. Bundled atlas data and third-party software
retain their own licenses. The MIT License does not replace those terms.

| Component | Version | License or source |
| --- | --- | --- |
| Python | 3.12.14 | Python Software Foundation License |
| NumPy | 2.5.1 | BSD-3-Clause, with additional bundled third-party licenses |
| SimpleITK / ITK | SimpleITK 2.5.6 | Apache 2.0 and bundled third-party notices |
| Qt / PySide6 / Shiboken6 | 6.11.1 | LGPLv3 for the included runtime components; additional third-party notices apply |
| PyInstaller | 6.21.0 | GPLv2-or-later with the bundled-application exception |
| ANTs | 2.6.5 | Apache 2.0; Copyright ConsortiumOfANTS |
| BMA 2.0 | 2.0 | CC BY 4.0 |

License texts supplied with the dependency distributions are included in
`THIRD_PARTY_LICENSES/`. Qt-related source archives are in `THIRD_PARTY_SOURCES/`.
The ANTs runtime has its own license and provenance files under
`_internal/ants/`. BMA attribution is in [data/README.md](data/README.md).

## Qt and PySide6

This application uses Qt through PySide6. The Qt libraries are dynamically
loaded from `_internal/PySide6/`; they are not part of the application's MIT code.
The release includes Qt Core, GUI, Widgets, Network, OpenGL, and SVG components,
with image-format, platform, and related plugins. The unused Qt Virtual
Keyboard, PDF, QML, and Quick components are excluded.

You may modify or replace the LGPL-covered libraries and debug the application
with those replacements, as permitted by their licenses. The application imposes
no additional restriction on those rights. Matching source archives and
replacement instructions are described in [QT_RUNTIME.md](docs/QT_RUNTIME.md).
The license texts, rather than this summary, define the applicable terms.

## ANTs

The bundled `antsRegistration.exe` comes from the
[official ANTs 2.6.5 release](https://github.com/ANTsX/ANTs/releases/tag/v2.6.5)
and is not modified. `_internal/ants/Runtime.json` records its source and checksums.
ANTs and ITK notices are in `_internal/ants/licenses/`. A notice for an optional
ITK component does not mean that component is used by this application.

Neither 3D Slicer nor SlicerANTs is required or bundled.

## Other runtime components

Microsoft Visual C++ runtime components retain Microsoft's terms. If a required
runtime is missing, obtain the x64 redistributable from Microsoft. Windows
system DLLs are not copied into the package.

Dependencies may include code from other projects. Retain their notices when
redistributing the package. This document is an index to the included licenses,
not a substitute for them.
