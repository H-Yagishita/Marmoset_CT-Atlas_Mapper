# Build with the Windows system ICU API expected by the pinned Qt distribution.
from pathlib import Path
import os
import re
import sys
import pefile

root = Path(SPECPATH).parent
sys.path.insert(0, str(root / 'src'))
from marmoset_atlas_mapper.ants_registration import verify_bundled_runtime
verify_bundled_runtime(root / 'runtime/ants')
a = Analysis(
    [str(root / 'app.py')], pathex=[str(root / 'src')], binaries=[],
    # Native ANTs runs out of process. Preserve the verified distribution
    # verbatim instead of letting PyInstaller substitute host DLLs into it.
    datas=[(str(root / 'config'), 'config'), (str(root / 'assets'), 'assets'),
           (str(root / 'runtime/ants'), 'ants')],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[],
    noarchive=False, optimize=0,
)

# Analysis may reclassify executable data as binaries. Keep ANTs byte-for-byte
# identical even on a build host that has UPX installed.
ants_binaries = [row for row in a.binaries if Path(row[0]).parts[0] == 'ants']
a.binaries = [row for row in a.binaries if Path(row[0]).parts[0] != 'ants']
a.datas += [(name, source, 'DATA') for name, source, _ in ants_binaries]

# A build host may put a private, version-suffixed ICU on PATH. Qt 6.11's
# Windows wheel instead imports unversioned functions from the OS ICU DLL.
# PyInstaller's dependency search can mistakenly collect the private DLL.
# Validate the required API, then leave ICU to the Windows loader; never
# redistribute an incompatible private DLL (or copy Windows system DLLs).
qt_core = next(source for name, source, kind in a.binaries if Path(name).name.lower() == 'qt6core.dll')
qt_pe = pefile.PE(qt_core)
icu_imports = {i.name for entry in qt_pe.DIRECTORY_ENTRY_IMPORT
               if entry.dll.lower() == b'icuuc.dll' for i in entry.imports if i.name}
if not icu_imports or b'ucnv_open' not in icu_imports:
    raise RuntimeError('Qt ICU ABI changed: review the Windows packaging rule.')
system_icu = Path(os.environ['SystemRoot']) / 'System32' / 'icuuc.dll'
system_pe = pefile.PE(str(system_icu))
system_exports = {symbol.name for symbol in system_pe.DIRECTORY_ENTRY_EXPORT.symbols}
if not icu_imports.issubset(system_exports):
    raise RuntimeError('This Windows installation lacks the ICU API required by Qt.')
qt_pe.close()
system_pe.close()

excluded = [row for row in a.binaries if re.fullmatch(r'(icuuc|icudt\d+)\.dll', Path(row[0]).name, re.I)]
for name, source, kind in excluded:
    print(f'Using Windows ICU instead of build-host dependency: {name} ({source})')
a.binaries = [row for row in a.binaries if row not in excluded]

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name='MarmosetAtlasMapper',
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True,
    console=False, disable_windowed_traceback=False,
    icon=[str(root / 'assets/marmoset_atlas_mapper_icon.ico')],
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, upx_exclude=[], name='MarmosetAtlasMapper')
