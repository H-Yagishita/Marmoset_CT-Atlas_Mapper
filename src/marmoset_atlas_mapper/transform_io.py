from __future__ import annotations

import ctypes
import hashlib
import os
import shutil
from pathlib import Path

import SimpleITK as sitk

from .data_manager import load_data_catalog
from .paths import user_state_root


DRIVE_REMOTE = 4


def _is_remote_path(path: Path) -> bool:
    """Return True for a Windows mapped or UNC network drive."""
    if os.name != "nt":
        return False
    anchor = path.anchor or path.drive
    if not anchor:
        return False
    try:
        return int(ctypes.windll.kernel32.GetDriveTypeW(str(anchor))) == DRIVE_REMOTE
    except (AttributeError, OSError):
        return False


def _requires_local_cache(path: Path) -> bool:
    if _is_remote_path(path):
        return True
    # Some removable/external or virtualized fixed drives also expose HDF5
    # locking/mapping failures. Cache when the transform is not on the same
    # volume as the per-user state directory.
    state_drive = user_state_root().expanduser().resolve().drive
    return bool(path.drive and state_drive and path.drive.casefold() != state_drive.casefold())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _expected_sha256(path: Path) -> str | None:
    try:
        catalog = load_data_catalog()
    except (OSError, KeyError, TypeError, ValueError):
        return None
    matches = [digest for relative, digest in catalog.file_sha256.items() if relative.name == path.name]
    return matches[0] if len(matches) == 1 else None


def localize_hdf5_transform(path: str | Path) -> Path:
    """Cache remote HDF5 transforms locally before SimpleITK opens them.

    Some SimpleITK/HDF5 builds access-violate on mapped SMB drives. Images stay
    in the selected library; only .h5 transforms are copied once per path,
    size, and modification-time fingerprint into the per-user cache.
    """
    source = Path(path).expanduser().resolve()
    if source.suffix.lower() != ".h5" or not _requires_local_cache(source):
        return source
    stat = source.stat()
    expected = _expected_sha256(source)
    if expected:
        source_digest = _sha256(source)
        if source_digest.lower() != expected.lower():
            raise ValueError(
                f"Reference transform checksum failed: {source.name}. "
                "Reinstall or reselect the reference-data library."
            )
        fingerprint = expected[:16]
    else:
        fingerprint = hashlib.sha256(
            f"{source}|{stat.st_size}|{stat.st_mtime_ns}".encode("utf-8")
        ).hexdigest()[:16]
    destination = user_state_root() / "transform_cache" / f"{source.stem}-{fingerprint}.h5"
    if destination.is_file() and destination.stat().st_size == stat.st_size:
        if not expected or _sha256(destination).lower() == expected.lower():
            return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    if expected and not destination.exists():
        for candidate in destination.parent.glob(f"{source.stem}-*.h5"):
            if candidate.stat().st_size == stat.st_size and _sha256(candidate).lower() == expected.lower():
                candidate.replace(destination)
                return destination
    temporary = destination.with_name(f"{destination.name}.{os.getpid()}.part")
    shutil.copy2(source, temporary)
    if temporary.stat().st_size != stat.st_size:
        raise OSError(f"Incomplete transform cache copy: {source}")
    if expected and _sha256(temporary).lower() != expected.lower():
        raise OSError(f"Cached transform checksum failed: {source}")
    temporary.replace(destination)
    return destination


def read_transform(path: str | Path) -> sitk.Transform:
    return sitk.ReadTransform(str(localize_hdf5_transform(path)))
