from pathlib import Path

import numpy as np
import SimpleITK as sitk

from marmoset_atlas_mapper.displacement_consensus import (
    GridGeometryRAS,
    displacement_transform,
    equal_weight_consensus,
    sample_forward_transform,
)
from marmoset_atlas_mapper.io_manifest import write_transform_checked


GRID = GridGeometryRAS((-2.0, -2.0, -2.0), (1.0, 1.0, 1.0), (5, 5, 5))


def translation(offset):
    transform = sitk.TranslationTransform(3)
    transform.SetOffset(tuple(offset))
    return transform


def test_four_identical_transforms_have_the_same_consensus():
    field = sample_forward_transform(translation((1.0, -2.0, 3.0)), GRID)
    consensus = equal_weight_consensus({f"R{i}": field for i in range(4)})
    assert np.allclose(sitk.GetArrayFromImage(consensus), (1.0, -2.0, 3.0))


def test_known_translations_are_averaged_pointwise():
    offsets = {
        "R1": (0.0, 0.0, 0.0),
        "R2": (2.0, 0.0, 0.0),
        "R3": (0.0, 4.0, 0.0),
        "R4": (0.0, 0.0, 6.0),
    }
    fields = {key: sample_forward_transform(translation(value), GRID) for key, value in offsets.items()}
    transform = displacement_transform(equal_weight_consensus(fields))
    point = np.asarray((0.25, -0.5, 0.75))
    expected = np.mean(
        [np.asarray(translation(value).TransformPoint(tuple(point))) for value in offsets.values()],
        axis=0,
    )
    assert np.allclose(transform.TransformPoint(tuple(point)), expected)


def test_consensus_is_independent_of_reference_order():
    fields = {
        key: sample_forward_transform(translation(value), GRID)
        for key, value in {
            "J0477M": (0.0, 0.0, 4.0),
            "HJ0285F": (1.0, 0.0, 0.0),
            "J0476M": (0.0, 3.0, 0.0),
            "HH0424M": (0.0, 0.0, 2.0),
        }.items()
    }
    first = equal_weight_consensus(fields)
    second = equal_weight_consensus(dict(reversed(list(fields.items()))))
    assert np.array_equal(sitk.GetArrayFromImage(first), sitk.GetArrayFromImage(second))


def test_saved_reloaded_h5_preserves_coordinates(tmp_path: Path):
    field = sample_forward_transform(translation((1.25, -0.5, 2.0)), GRID)
    transform = displacement_transform(field)
    points = np.asarray([(-1.0, -1.0, -1.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)])
    error = write_transform_checked(tmp_path / "forward.h5", transform, points)
    assert error < 1e-10
