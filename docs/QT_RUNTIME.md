# Qt runtime and source

The Windows package uses the unmodified PySide6 and Shiboken6 6.11.1 wheels with
Qt 6.11.1, linked dynamically. The Qt Virtual Keyboard, PDF, QML, and Quick
modules are not used and are not included.

## Source archives

`THIRD_PARTY_SOURCES/` contains the matching upstream source archives for Qt Base,
SVG, Image Formats, Translations, and PySide/Shiboken, each with its build files
and license notices. `Sources.json` gives the official download URL and SHA-256
of each archive. The archives are unmodified copies from Qt's official
distribution, and Marmoset Atlas Mapper makes no changes to these libraries.

## Replacing the libraries

Work on a copy of the application folder. The Qt libraries and Python extension
modules are in `_internal/PySide6/` and `_internal/shiboken6/`. Replace them with
a compatible build for the same Windows architecture and Python version,
together with the matching plugins and dependent DLLs; mixing incompatible Qt
builds may prevent the app from starting.

Alternatively, run the application source with your own PySide6 installation,
or rebuild the executable with `build_exe.ps1`. The app does not check the Qt
libraries against fixed checksums or prevent their replacement; its integrity
checks apply only to the reference data and the ANTs runtime.

Building Qt and PySide requires the tools described in the source archives and
the upstream documentation:

- [Building Qt for Windows](https://doc.qt.io/qt-6/windows-building.html)
- [Building PySide6](https://doc.qt.io/qtforpython-6/building_from_source/index.html)
- [Qt open-source obligations](https://www.qt.io/development/open-source-lgpl-obligations)

Your rights to use, modify, replace, and redistribute these components are
defined by the LGPL and related license texts in `THIRD_PARTY_LICENSES/`.
