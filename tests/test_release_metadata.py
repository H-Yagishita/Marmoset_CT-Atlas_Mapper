"""Keep the public version and legacy registration names consistent."""
from pathlib import Path
import json
import tomllib

import pytest
from marmoset_atlas_mapper import __version__
from marmoset_atlas_mapper.registration_modes import normalize_registration_type

ROOT = Path(__file__).resolve().parents[1]


def test_release_version_consistency():
    assert __version__ == '1.00'
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text())
    assert project['project']['version'] == __version__
    catalog = json.loads((ROOT / 'config/reference_data_catalog.json').read_text())
    assert catalog['package']['filename'] == f'MarmosetAtlasMapper_v{__version__}_Windows_Complete.zip'
    assert f'version: "{__version__}"' in (ROOT / 'CITATION.cff').read_text()
    assert f"'ProductVersion', '{__version__}'" in (ROOT / 'packaging/version_info.txt').read_text()


@pytest.mark.parametrize('old, current', [
    ('Landmark (Skull-base)', 'Landmarks (skull base)'),
    ('Landmark (Skull-all)', 'Landmarks (total)'),
    ('ANTs registration', 'ANTs registration'),
    (None, None),
    ('Unrecognized mode', 'Unrecognized mode'),
])
def test_normalize_mode(old, current):
    assert normalize_registration_type(old) == current


def test_reference_license_and_version_doi():
    catalog = json.loads((ROOT / 'config/reference_data_catalog.json').read_text())
    assert catalog['landing_page_url'] == 'https://doi.org/10.5281/zenodo.23683937'
    assert 'Reference images, landmarks, and transforms: CC BY 4.0.' in catalog['license_summary']
    notice = (ROOT / 'data/licenses/ReferenceLibrary-CC-BY-4.0.txt').read_text(encoding='utf-8')
    for name in ['Haruya Yagishita', 'Yuji Nagai', 'Yuki Hori',
                 'Takafumi Minamimoto', 'Yoshikazu Isomura']:
        assert name in notice
    assert '[rights holders]' not in notice
    assert 'https://creativecommons.org/licenses/by/4.0/' in notice
    assert 'license: MIT' in (ROOT / 'CITATION.cff').read_text(encoding='utf-8')


def test_maintainer_notes_excluded_from_source_archives():
    attributes = (ROOT / '.gitattributes').read_text(encoding='utf-8')
    for name in ['PUBLICATION_CHECKLIST.md', 'docs/ZENODO_RELEASE.md']:
        assert f'/{name} export-ignore' in attributes


def test_legacy_release_placeholders_absent():
    # A preprint DOI may still be pending in the working draft. The separate
    # publication preflight must pass before a public package can be built.
    for name in ['README.md', 'CHANGELOG.md', 'CITATION.cff', 'data/README.md',
                 'data/licenses/ReferenceLibrary-CC-BY-4.0.txt']:
        content = (ROOT / name).read_text(encoding='utf-8')
        for placeholder in ['[rights holders]', 'YYYY-MM-DD', '[Preprint DOI to be added]']:
            assert placeholder not in content, (name, placeholder)
