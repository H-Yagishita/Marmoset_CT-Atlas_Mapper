import hashlib
import json
from pathlib import Path

from marmoset_atlas_mapper.data_manager import load_data_catalog, validate_resource_root


def _catalog(tmp_path: Path, expected_sha256: str = "") -> Path:
    path = tmp_path / "catalog.json"
    payload = {
        "schema_version": 1,
        "dataset_id": "test-data",
        "display_name": "Test reference data",
        "version": "1.0",
        "landing_page_url": "https://example.invalid/data",
        "license_summary": "Test license",
        "package": {
            "filename": "MarmosetAtlasMapper_Data_v1.0.zip",
            "sha256": "abc",
            "size_bytes": 123,
        },
        "required_files": ["data/atlas/test.txt", "data/reference/test.txt"],
        "file_sha256": {},
    }
    if expected_sha256:
        payload["file_sha256"]["data/atlas/test.txt"] = expected_sha256
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_catalog_describes_single_manual_zip(tmp_path):
    catalog = load_data_catalog(_catalog(tmp_path))
    assert catalog.package_filename == "MarmosetAtlasMapper_Data_v1.0.zip"
    assert catalog.package_sha256 == "abc"
    assert catalog.package_size_bytes == 123


def test_validate_complete_data_folder_beside_application(tmp_path):
    catalog = load_data_catalog(_catalog(tmp_path))
    (tmp_path / "data/atlas").mkdir(parents=True)
    (tmp_path / "data/reference").mkdir(parents=True)
    (tmp_path / "data/atlas/test.txt").write_text("atlas", encoding="utf-8")
    (tmp_path / "data/reference/test.txt").write_text("reference", encoding="utf-8")
    assert validate_resource_root(tmp_path, catalog).complete


def test_validate_reports_missing_files(tmp_path):
    catalog = load_data_catalog(_catalog(tmp_path))
    status = validate_resource_root(tmp_path, catalog)
    assert not status.complete
    assert len(status.missing_files) == 2


def test_optional_checksum_validation_detects_corruption(tmp_path):
    expected = hashlib.sha256(b"correct").hexdigest()
    catalog = load_data_catalog(_catalog(tmp_path, expected))
    (tmp_path / "data/atlas").mkdir(parents=True)
    (tmp_path / "data/reference").mkdir(parents=True)
    (tmp_path / "data/atlas/test.txt").write_text("corrupt", encoding="utf-8")
    (tmp_path / "data/reference/test.txt").write_text("reference", encoding="utf-8")
    status = validate_resource_root(tmp_path, catalog, verify_checksums=True)
    assert not status.complete
    assert status.checksum_failures == (tmp_path / "data/atlas/test.txt",)
