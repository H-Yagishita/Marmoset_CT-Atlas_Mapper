# Qt runtime and source

The Windows package uses the unmodified PySide6 and Shiboken6 6.11.1 wheels
with Qt 6.11.1. The app links to the Qt libraries dynamically. It does not use
the Qt Virtual Keyboard, PDF, QML, or Quick modules, which are excluded from
the package.

## Source archives

`THIRD_PARTY_SOURCES/` contains the matching upstream source archives for Qt
Base, SVG, Image Formats, Translations, and PySide/Shiboken. Each archive includes
its build files and license notices. `Sources.json` records the official download
URL and SHA-256 for each archive.

The archives are copied from Qt's official distribution without modification.
No changes to these libraries are made by Marmoset Atlas Mapper. The archive
checksums are also pinned in `tools/prepare_qt_sources.py`.

## Replacing the libraries

Work on a copy of the application folder and retain the original installation.
The dynamic libraries and Python extension modules are in `_internal/PySide6/`
and `_internal/shiboken6/`. Replace them with a compatible build for the same
Windows architecture and Python ABI, including the matching plugins and any
dependent DLLs. A mixture of incompatible Qt builds may prevent startup.

Alternatively, run the supplied application source with your modified PySide6
installation, or rebuild the executable with `build_exe.ps1`. The app does not
verify Qt libraries against fixed hashes or prevent their replacement. Its
separate integrity checks for reference data and the ANTs runtime do not apply
to Qt.

Building Qt and PySide requires the tools described in the source archives and
upstream build documentation:

- [Building Qt for Windows](https://doc.qt.io/qt-6/windows-building.html)
- [Building PySide6](https://doc.qt.io/qtforpython-6/building_from_source/index.html)
- [Qt open-source obligations](https://www.qt.io/development/open-source-lgpl-obligations)

The LGPL and related license texts in `THIRD_PARTY_LICENSES/` govern your rights
to use, modify, replace, and redistribute these components.
