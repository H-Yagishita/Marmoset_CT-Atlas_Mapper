"""Download matching Qt/PySide sources for the complete Windows release."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import urllib.request

QT_ROOT = 'https://download.qt.io/archive/qt/6.11/6.11.1/submodules/'
PYSIDE_ROOT = 'https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.1-src/'
SOURCES = {
    'qtbase-everywhere-src-6.11.1.tar.xz': (QT_ROOT, 'd9594a31228aa23ad6b531719a29b45f0f3989fe6c136d45767ea179f233c1ac'),
    'qtsvg-everywhere-src-6.11.1.tar.xz': (QT_ROOT, '7f3cf02f4824bf03c2c5859ea6db173bf1482a1daf24e6cdf7bc78cfa26a8a94'),
    'qtimageformats-everywhere-src-6.11.1.tar.xz': (QT_ROOT, 'b2bf6c6845ac175ed7f819145483ba4676f617aaa6a5012c8efee63c8bbac413'),
    'qttranslations-everywhere-src-6.11.1.tar.xz': (QT_ROOT, '37c02c81206594c7bb4edca85ac93e8e55a9836b70c960fde6cb0f8623ec5677'),
    'pyside-setup-everywhere-src-6.11.1.tar.xz': (PYSIDE_ROOT, '6ffd9835bb0dd2c56f061d62f1616bb1707cfc0202b80e3165d6be087f3965e2'),
}


def prepare(destination):
    destination = Path(destination).resolve()
    workspace = Path(__file__).resolve().parents[1]
    if not destination.is_relative_to(workspace) or destination == workspace:
        raise ValueError('Use a dedicated folder within this workspace.')
    destination.mkdir(parents=True, exist_ok=True)

    def download(item):
        name, (base, expected) = item
        target = destination / name
        if target.is_symlink():
            raise ValueError('Source archive must not be a symbolic link.')
        if not target.exists():
            with urllib.request.urlopen(base + name, timeout=60) as response, target.open('xb') as output:
                shutil.copyfileobj(response, output)
        with target.open('rb') as source:
            actual = hashlib.file_digest(source, 'sha256').hexdigest()
        if actual != expected:
            raise ValueError(f'Checksum mismatch: {name}; retain the file for inspection.')
        print('Verified source: ' + name, flush=True)
        return {'file': name, 'url': base + name, 'sha256': actual, 'bytes': target.stat().st_size}

    with ThreadPoolExecutor(max_workers=3) as pool:
        rows = list(pool.map(download, SOURCES.items()))
    manifest = destination / 'Sources.json'
    with manifest.open('x', encoding='utf-8') as output:
        json.dump({'version': '6.11.1', 'modified': False, 'archives': rows}, output, indent=2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination')
    prepare(parser.parse_args().destination)
