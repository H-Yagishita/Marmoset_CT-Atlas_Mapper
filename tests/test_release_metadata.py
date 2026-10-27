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
