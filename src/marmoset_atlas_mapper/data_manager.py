from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .paths import bundled_config_root, configured_resource_root


@dataclass(frozen=True)
class DataCatalog:
    schema_version: int
    dataset_id: str
    display_name: str
    version: str
    landing_page_url: str
    license_summary: str
    package_filename: str
    package_sha256: str
    package_size_bytes: int | None
    required_files: tuple[Path, ...]
    file_sha256: dict[Path, str]


@dataclass(frozen=True)
class DataStatus:
    root: Path
    missing_files: tuple[Path, ...]
    checksum_failures: tuple[Path, ...] = ()

    @property
    def complete(self) -> bool:
        return not self.missing_files and not self.checksum_failures


def load_data_catalog(path: str | Path | None = None) -> DataCatalog:
    override = os.environ.get("MARM_ATLAS_DATA_CATALOG")
    catalog_path = Path(path or override or bundled_config_root() / "reference_data_catalog.json")
    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    package = payload["package"]
    return DataCatalog(
        schema_version=int(payload["schema_version"]),
        dataset_id=payload["dataset_id"],
        display_name=payload["display_name"],
        version=payload["version"],
        landing_page_url=payload.get("landing_page_url", ""),
        license_summary=payload.get("license_summary", ""),
        package_filename=package["filename"],
        package_sha256=package.get("sha256", "").lower(),
        package_size_bytes=package.get("size_bytes"),
        required_files=tuple(Path(value) for value in payload["required_files"]),
        file_sha256={Path(key): value.lower() for key, value in payload.get("file_sha256", {}).items()},
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def validate_resource_root(
    root: str | Path,
    catalog: DataCatalog | None = None,
    *,
    verify_checksums: bool = False,
) -> DataStatus:
    catalog = catalog or load_data_catalog()
    resolved = Path(root).expanduser().resolve()
    missing = tuple(
        resolved / relative
        for relative in catalog.required_files
        if not (resolved / relative).is_file()
    )
    failures: list[Path] = []
    if verify_checksums:
        for relative, expected in catalog.file_sha256.items():
            candidate = resolved / relative
            if candidate.is_file() and _sha256(candidate).lower() != expected:
                failures.append(candidate)
    return DataStatus(resolved, missing, tuple(failures))


def active_data_status(catalog: DataCatalog | None = None) -> DataStatus:
    return validate_resource_root(configured_resource_root(), catalog)
