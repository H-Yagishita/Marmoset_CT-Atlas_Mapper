from pathlib import Path

import SimpleITK as sitk

import marmoset_atlas_mapper.transform_io as transform_io


def test_remote_hdf5_transform_is_cached_and_read(tmp_path, monkeypatch):
    source = tmp_path / "remote" / "transform.h5"
    source.parent.mkdir()
    original = sitk.TranslationTransform(3, (1.0, 2.0, 3.0))
    sitk.WriteTransform(original, str(source))
    cache = tmp_path / "state"
    monkeypatch.setattr(transform_io, "_requires_local_cache", lambda path: True)
    monkeypatch.setattr(transform_io, "user_state_root", lambda: cache)

    localized = transform_io.localize_hdf5_transform(source)
    assert localized != source
    assert localized.is_file()
    assert localized.stat().st_size == source.stat().st_size
    loaded = transform_io.read_transform(source)
    assert loaded.TransformPoint((0.0, 0.0, 0.0)) == (1.0, 2.0, 3.0)


def test_local_non_hdf5_path_is_not_copied(tmp_path, monkeypatch):
    path = tmp_path / "transform.tfm"
    path.write_text("unused", encoding="utf-8")
    monkeypatch.setattr(transform_io, "_requires_local_cache", lambda value: True)
    assert transform_io.localize_hdf5_transform(path) == path.resolve()
