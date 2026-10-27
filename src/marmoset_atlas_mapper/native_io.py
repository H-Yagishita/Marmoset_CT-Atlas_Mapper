"""Unicode-safe paths for Windows ITK backends that still use narrow fopen.

Python handles the user's actual filenames; native libraries see ASCII paths.
Ordinary ASCII paths are untouched. Temporary files are private and removed
after each operation; no original image headers or voxel data are modified.
"""
from contextlib import contextmanager
from pathlib import Path
import ctypes
import os
import re
import shutil
import tempfile
import uuid
import SimpleITK as sitk


def needs_staging(path) -> bool:
    return os.name == 'nt' and not str(Path(path).resolve()).isascii()


def _short_path(path: Path) -> str | None:
    if os.name != 'nt':
        return None
    buffer = ctypes.create_unicode_buffer(32768)
    count = ctypes.windll.kernel32.GetShortPathNameW(str(path), buffer, len(buffer))
    return buffer.value if 0 < count < len(buffer) and buffer.value.isascii() else None


@contextmanager
def ascii_temporary_directory():
    with tempfile.TemporaryDirectory(prefix='mapper_io_') as value:
        native = value if value.isascii() else _short_path(Path(value))
        if native is None:
            raise ValueError('ITK requires an ASCII temporary path on this Windows installation. Set TEMP to an ASCII path.')
        yield Path(native)


def _suffix(path):
    return '.nii.gz' if str(path).lower().endswith('.nii.gz') else Path(path).suffix


@contextmanager
def native_input_path(path):
    source = Path(path).resolve()
    if not needs_staging(source):
        yield source
        return
    # Do not pass a file's Windows 8.3 alias to ITK. For example, .nii.gz
    # becomes .GZ and .nrrd becomes .NRR; automatic ImageIO selection then
    # fails on hosts where short names are enabled. Stage with the original
    # suffix instead. A short *directory* path remains safe for TEMP above.
    # Detached NRRD headers may themselves contain a Unicode payload name.
    with ascii_temporary_directory() as temp:
        staged = temp / ('input' + _suffix(source))
        if source.suffix.lower() == '.nhdr':
            header = source.read_text(encoding='utf-8-sig')
            match = re.search(r'^data\s*file\s*:\s*(.+)$', header, re.M | re.I)
            if match is None or match.group(1).strip().upper().startswith('LIST') or '%' in match.group(1):
                raise ValueError('For non-ASCII paths, use a single-payload .nhdr or an embedded .nrrd image.')
            value = match.group(1).strip().strip('"')
            payload = source.parent / value
            shutil.copyfile(payload, temp / 'payload.raw')
            staged.write_text(header[:match.start()] + 'data file: payload.raw' + header[match.end():], encoding='utf-8')
        else:
            shutil.copyfile(source, staged)
        yield staged


def read_image(path, *args, **kwargs):
    with native_input_path(path) as native:
        return sitk.ReadImage(str(native), *args, **kwargs)


def _write_native(writer, value, path, *args, **kwargs):
    destination = Path(path).resolve()
    if not needs_staging(destination):
        writer(value, str(destination), *args, **kwargs)
        return
    with ascii_temporary_directory() as temp:
        staged = temp / ('image' + _suffix(destination))
        writer(value, str(staged), *args, **kwargs)
        if destination.suffix.lower() == '.nhdr':
            header = staged.read_text(encoding='utf-8')
            match = re.search(r'^data\s*file\s*:\s*(.+)$', header, re.M | re.I)
            if match is None:
                raise ValueError('Detached NRRD writer did not produce a data file.')
            payload_name = 'mapper_data_' + uuid.uuid4().hex + '.raw'
            shutil.copyfile(temp / match.group(1).strip(), destination.parent / payload_name)
            destination.write_text(header[:match.start()] + 'data file: ' + payload_name + header[match.end():], encoding='utf-8')
        else:
            shutil.copyfile(staged, destination)


def write_image(image, path, *args, **kwargs):
    _write_native(sitk.WriteImage, image, path, *args, **kwargs)


def write_transform(transform, path):
    _write_native(sitk.WriteTransform, transform, path)
