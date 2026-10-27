"""Unicode paths must not depend on Windows 8.3-name availability."""
import hashlib
import shutil

import numpy as np
import pytest
import SimpleITK as sitk

from marmoset_atlas_mapper import native_io
from marmoset_atlas_mapper.transform_io import read_transform


@pytest.mark.parametrize('suffix', ['.nii', '.nii.gz', '.nrrd', '.nhdr'])
@pytest.mark.parametrize('short_names', [False, True])
def test_unicode_image_geometry_and_voxels(tmp_path, monkeypatch, suffix, short_names):
    folder = tmp_path / '日本語フォルダ'
    folder.mkdir()
    source = folder / ('画像 CT' + suffix)
    monkeypatch.setattr(native_io, 'needs_staging', lambda p: not str(p).isascii())
    image = sitk.GetImageFromArray(np.arange(120, dtype=np.float32).reshape(4, 5, 6))
    angle = .23
    image.SetDirection((np.cos(angle), -np.sin(angle), 0,
                        np.sin(angle), np.cos(angle), 0, 0, 0, 1))
    image.SetSpacing((.1, .3, .8))
    image.SetOrigin((12, -100, 53))
    native_io.write_image(image, source, True)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    # Reproduce the GitHub Windows runner's short filename, including loss of
    # the .nii portion and truncation of the four-character .nrrd extension.
    alias = tmp_path / ('IMAGE~1' + {'.nii': '.NII', '.nii.gz': '.GZ',
                                    '.nrrd': '.NRR', '.nhdr': '.NHD'}[suffix])
    shutil.copyfile(source, alias)
    original_short_path = native_io._short_path
    monkeypatch.setattr(native_io, '_short_path', lambda p:
        (str(alias) if short_names else None) if p == source.resolve()
        else original_short_path(p))
    with native_io.native_input_path(source) as staged:
        assert str(staged).isascii()
        assert staged.name == 'input' + suffix
        extracted_path = staged
    assert not extracted_path.exists()
    actual = native_io.read_image(source)
    np.testing.assert_array_equal(sitk.GetArrayFromImage(actual), sitk.GetArrayFromImage(image))
    np.testing.assert_allclose(actual.GetSpacing(), image.GetSpacing(), atol=1e-6)
    np.testing.assert_allclose(actual.GetDirection(), image.GetDirection(), atol=1e-6)
    np.testing.assert_allclose(actual.GetOrigin(), image.GetOrigin(), atol=1e-6)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


def test_unicode_transform_and_exception_cleanup(tmp_path, monkeypatch):
    source = tmp_path / '日本語変換.h5'
    monkeypatch.setattr(native_io, 'needs_staging', lambda p: not str(p).isascii())
    transform = sitk.AffineTransform(3)
    transform.SetTranslation((1.25, -3.5, 2.75))
    native_io.write_transform(transform, source)
    before = source.read_bytes()
    actual = read_transform(source)
    assert actual.TransformPoint((2, 3, 4)) == transform.TransformPoint((2, 3, 4))
    with pytest.raises(RuntimeError, match='test exception'):
        with native_io.native_input_path(source) as staged:
            extracted_path = staged
            assert staged.suffix == '.h5'
            raise RuntimeError('test exception')
    assert not extracted_path.exists()
    assert source.read_bytes() == before


def test_ascii_path_is_not_copied(tmp_path):
    source = tmp_path / 'ascii.nii.gz'
    source.write_bytes(b'unchanged')
    with native_io.native_input_path(source) as native:
        assert native == source.resolve()
    assert source.read_bytes() == b'unchanged'
