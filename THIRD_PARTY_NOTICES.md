# Third-party notices

The Marmoset Atlas Mapper code is under the MIT License, and the six-reference
data are under CC BY 4.0 (see [data/README.md](data/README.md)). The bundled atlas
and third-party software retain their own licenses. This document lists the
components; the license texts define their terms.

| Component | Version | License |
| --- | --- | --- |
| Python | 3.12.14 | Python Software Foundation License |
| NumPy | 2.5.1 | BSD-3-Clause, with additional bundled licenses |
| SimpleITK / ITK | SimpleITK 2.5.6 | Apache 2.0, with bundled notices |
| Qt / PySide6 / Shiboken6 | 6.11.1 | LGPLv3 for the included runtime components, with additional notices |
| PyInstaller | 6.21.0 | GPLv2 or later, with the bootloader exception for bundled applications |
| ANTs | 2.6.5 | Apache 2.0; Copyright ConsortiumOfANTS |
| BMA 2.0 | 2.0 | CC BY 4.0 |

- License texts of the dependencies: `THIRD_PARTY_LICENSES/`
- Qt and PySide source archives: `THIRD_PARTY_SOURCES/`
- ANTs license and provenance files: `_internal/ants/`
- BMA 2.0 attribution: [data/README.md](data/README.md)

## Qt and PySide6

The application uses Qt through PySide6. The Qt libraries in `_internal/PySide6/`
are loaded dynamically and are not part of the MIT-licensed code. The package
includes the Qt Core, GUI, Widgets, Network, OpenGL, and SVG modules with their
plugins; the Qt Virtual Keyboard, PDF, QML, and Quick modules are not included.

You may modify or replace the LGPL-licensed libraries and debug the application
with your replacements; the application adds no restriction to these rights.
[docs/QT_RUNTIME.md](docs/QT_RUNTIME.md) describes the matching source archives
and how to replace the libraries.

## ANTs

The bundled `antsRegistration.exe` is the unmodified executable from the
[official ANTs 2.6.5 release](https://github.com/ANTsX/ANTs/releases/tag/v2.6.5).
`_internal/ants/Runtime.json` records its source and checksums, and the ANTs and
ITK notices are in `_internal/ants/licenses/`. A notice for an optional ITK
component does not mean that the component is used. 3D Slicer and SlicerANTs
are neither required nor bundled.

## Other components

Microsoft Visual C++ runtime components remain under Microsoft's terms. Windows
system DLLs are not included. Dependencies may contain code from other projects;
keep their notices when redistributing the package.
