"""Disposable Unicode I/O audit for the frozen Windows executable."""
from pathlib import Path
import json
import traceback

import numpy as np
import SimpleITK as sitk

from . import native_io
from .transform_io import read_transform


def audit(report_path):
    report = Path(report_path).resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    root = report.with_suffix('') / '日本語 入出力'
    root.mkdir(parents=True, exist_ok=False)
    details = {'status': 'Running', 'image_formats': [], 'short_file_alias_used': False}
    original_short = native_io._short_path
    try:
        def directory_alias_only(path):
            if path.is_file():
                details['short_file_alias_used'] = True
                raise AssertionError('A file alias can lose its extension.')
            return original_short(path)
        native_io._short_path = directory_alias_only
        image = sitk.GetImageFromArray(np.arange(120, dtype=np.float32).reshape(4, 5, 6))
        angle = .23
        image.SetDirection((np.cos(angle), -np.sin(angle), 0,
                            np.sin(angle), np.cos(angle), 0, 0, 0, 1))
        image.SetSpacing((.1, .3, .8))
        image.SetOrigin((12, -100, 53))
        for suffix in ['.nii', '.nii.gz', '.nrrd', '.nhdr']:
            path = root / ('日本語 CT' + suffix)
            native_io.write_image(image, path, True)
            loaded = native_io.read_image(path)
            np.testing.assert_array_equal(sitk.GetArrayFromImage(loaded), sitk.GetArrayFromImage(image))
            np.testing.assert_allclose(loaded.GetSpacing(), image.GetSpacing(), atol=1e-6)
            np.testing.assert_allclose(loaded.GetDirection(), image.GetDirection(), atol=1e-6)
            np.testing.assert_allclose(loaded.GetOrigin(), image.GetOrigin(), atol=1e-6)
            details['image_formats'].append(suffix)
        transform = sitk.AffineTransform(3)
        transform.SetTranslation((1.25, -3.5, 2.75))
        path = root / '日本語 変換.h5'
        native_io.write_transform(transform, path)
        assert read_transform(path).TransformPoint((2, 3, 4)) == transform.TransformPoint((2, 3, 4))
        details.update(status='Passed', h5_roundtrip=True, geometry_and_voxels_preserved=True)
    except Exception:
        details.update(status='Failed', traceback=traceback.format_exc())
    finally:
        native_io._short_path = original_short
    report.write_text(json.dumps(details, indent=2), encoding='utf-8')
    return 0 if details['status'] == 'Passed' else 1
