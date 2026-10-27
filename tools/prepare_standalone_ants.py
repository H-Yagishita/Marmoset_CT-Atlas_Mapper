"""Prepare the pinned Windows ANTs runtime; never download anything at app startup.

Supply the official ZIP described below. This build-time command verifies its
published SHA256, extracts antsRegistration and its bundled DLL dependencies,
and retrieves license files from pinned upstream source revisions.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import urllib.request
import zipfile

import pefile

VERSION = "2.6.5"
ARCHIVE_URL = "https://github.com/ANTsX/ANTs/releases/download/v2.6.5/ants-2.6.5-windows-2022-X64-VS2019.zip"
ARCHIVE_SHA256 = "2cfb09f9bfd796720819054711f493abd750dd3245875caaa5d04000d3a98c3d"
ITK_COMMIT = "f51594ad88194a72cdc06a314dafff709fcdc2e9"
WORKSPACE = Path(__file__).resolve().parents[1]


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def get_url(url):
    request = urllib.request.Request(url, headers={"User-Agent": "MarmosetAtlasMapper-runtime-preparation"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def prepare(archive, destination):
    archive, destination = archive.resolve(), destination.resolve()
    if not destination.is_relative_to(WORKSPACE) or destination == WORKSPACE:
        raise ValueError("Runtime output must be a new directory inside the source workspace.")
    if destination.exists():
        raise FileExistsError(f"Runtime output already exists: {destination}")
    if sha256(archive) != ARCHIVE_SHA256:
        raise ValueError("Official ANTs ZIP checksum mismatch")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Keep a failed staging directory for diagnosis; never delete broad targets.
    stage = Path(tempfile.mkdtemp(prefix="ants-preparation-", dir=destination.parent))
    (stage / "bin").mkdir()
    with zipfile.ZipFile(archive) as package:
        entries = {PurePosixPath(i.filename).name.lower(): i for i in package.infolist()
                   if not i.is_dir() and i.filename.lower().endswith((".dll", "/antsregistration.exe"))}
        required = ["antsregistration.exe"]
        imported, included = set(), set()
        while required:
            name = required.pop()
            if name in included:
                continue
            info = entries[name]
            target = stage / "bin" / PurePosixPath(info.filename).name
            target.write_bytes(package.read(info))
            included.add(name)
            pe = pefile.PE(str(target))
            if pe.FILE_HEADER.Machine != 0x8664:
                raise ValueError("Expected Windows x64 ANTs binary")
            dependencies = {entry.dll.decode("ascii").lower() for attribute in
                            ("DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT")
                            for entry in getattr(pe, attribute, [])}
            pe.close()
            imported.update(dependencies)
            required.extend(d for d in dependencies if d in entries and d not in included)
    external = sorted(imported - included)
    # Only OS API sets/Windows libraries and documented Microsoft VC runtime
    # dependencies may remain external. Never resolve a missing DLL from Slicer.
    allowed = {"kernel32.dll", "advapi32.dll", "user32.dll", "gdi32.dll", "ole32.dll",
               "oleaut32.dll", "shell32.dll", "ws2_32.dll", "wsock32.dll", "rpcrt4.dll", "ntdll.dll",
               "comdlg32.dll", "shlwapi.dll", "ucrtbase.dll", "bcrypt.dll", "crypt32.dll",
               "msvcrt.dll", "version.dll", "normaliz.dll", "psapi.dll"}
    unsupported = [d for d in external if d not in allowed and not d.startswith(
        ("api-ms-win-", "ext-ms-win-", "vcruntime140", "msvcp140", "concrt140"))]
    if unsupported:
        raise ValueError(f"Unresolved non-system DLLs: {unsupported}")

    licenses = [
        ("ANTs/ANTSCopyright.txt", "https://raw.githubusercontent.com/ANTsX/ANTs/v2.6.5/ANTSCopyright.txt"),
        ("ANTs/COPYING.txt", "https://raw.githubusercontent.com/ANTsX/ANTs/v2.6.5/COPYING.txt"),
    ]
    tree = json.loads(get_url(f"https://api.github.com/repos/InsightSoftwareConsortium/ITK/git/trees/{ITK_COMMIT}?recursive=1"))
    if tree.get("truncated"):
        raise ValueError("ITK license inventory was truncated")
    for entry in tree["tree"]:
        name = PurePosixPath(entry["path"]).name
        if entry["type"] == "blob" and re.match(r"^(LICENSE|LICENCE|COPYING|COPYRIGHT|NOTICE)([._-]|$)", name, re.I):
            licenses.append(("ITK/" + entry["path"],
                             f"https://raw.githubusercontent.com/InsightSoftwareConsortium/ITK/{ITK_COMMIT}/{entry['path']}"))
    if not any(relative == "ITK/LICENSE" for relative, _ in licenses):
        raise ValueError("Missing ITK license")

    def download_license(item):
        relative, url = item
        target = (stage / "licenses" / relative).resolve()
        if not target.is_relative_to(stage):
            raise ValueError("Invalid license path")
        content = get_url(url)
        if not content:
            raise ValueError(f"Empty license: {url}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(download_license, licenses))
    manifest = {
        "schema_version": 1, "name": "ANTs", "version": VERSION,
        "platform": "Windows x64", "executable": "bin/antsRegistration.exe",
        "archive_url": ARCHIVE_URL, "archive_sha256": ARCHIVE_SHA256,
        "itk_commit": ITK_COMMIT, "external_dlls": external,
        "license_sources": dict(licenses),
        "files": {p.relative_to(stage).as_posix(): sha256(p) for p in sorted(stage.rglob("*")) if p.is_file()},
    }
    (stage / "Runtime.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    stage.rename(destination)
    print(json.dumps({"runtime": str(destination), "files": len(manifest["files"]),
                      "external_dlls": external, "bytes": sum(p.stat().st_size for p in destination.rglob("*") if p.is_file())}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--destination", type=Path, default=WORKSPACE / "runtime/ants")
    args = parser.parse_args()
    prepare(args.archive, args.destination)
