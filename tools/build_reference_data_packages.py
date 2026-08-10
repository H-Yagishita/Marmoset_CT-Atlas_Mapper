"""Build the separately published, versioned reference-data ZIP package.

This tool intentionally excludes the obsolete *_Atlas_ANTs.h5 files. The
application's forward K04 pipeline uses the four validated PointTransform H5
files. Run this only after redistribution approval has been recorded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def write_archive(destination: Path, root: Path, relative_files: list[Path], catalog: dict) -> dict:
    missing = [path for path in relative_files if not (root / path).is_file()]
    if missing:
        raise FileNotFoundError("Missing package inputs: " + ", ".join(map(str, missing)))
    contents = {
        path.as_posix(): {"size_bytes": (root / path).stat().st_size, "sha256": sha256(root / path)}
        for path in sorted(relative_files)
    }
    internal_manifest = {
        "dataset_id": catalog["dataset_id"],
        "version": catalog["version"],
        "package_filename": destination.name,
        "layout": "Copy the extracted data folder beside MarmosetAtlasMapper.exe.",
        "files": contents,
    }
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as package:
        for relative in sorted(relative_files):
            package.write(root / relative, relative.as_posix())
        package.writestr(
            "data/PACKAGE_MANIFEST.json",
            json.dumps(internal_manifest, indent=2).encode("utf-8"),
        )
    return {
        "filename": destination.name,
        "size_bytes": destination.stat().st_size,
        "sha256": sha256(destination),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resource-root", type=Path, required=True, help="Folder containing data/")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "config/reference_data_catalog.json",
    )
    args = parser.parse_args()
    root = args.resource_root.expanduser().resolve()
    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    required = [Path(value) for value in catalog["required_files"]]

    package_files = list(required)
    if (root / "data/README.md").is_file():
        package_files.append(Path("data/README.md"))

    results = {
        "dataset_id": catalog["dataset_id"],
        "version": catalog["version"],
        "package": {},
    }
    package_name = catalog["package"]["filename"]
    results["package"] = write_archive(
        output / package_name, root, package_files, catalog
    )

    manifest = output / "MarmosetAtlasMapper_Data_v1.0_RELEASE_MANIFEST.json"
    manifest.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
