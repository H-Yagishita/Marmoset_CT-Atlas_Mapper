import numpy as np
import SimpleITK as sitk

from marmoset_atlas_mapper.imaging import (
    compose_atlas_to_user_for_resampling,
    compose_user_to_atlas,
    matrix_to_sitk_affine,
)
from marmoset_atlas_mapper.image_resampling import (
    resample_atlas_to_target,
    resample_target_to_reference,
)


def test_matrix_to_sitk_affine_matches_numpy():
    matrix = np.eye(4)
    matrix[:3, 3] = [1.0, 2.0, 3.0]
    transform = matrix_to_sitk_affine(matrix)
    np.testing.assert_allclose(transform.TransformPoint((4.0, 5.0, 6.0)), [5.0, 7.0, 9.0])


def test_composite_applies_user_to_reference_before_reference_to_atlas(tmp_path):
    user_to_reference = np.eye(4)
    user_to_reference[:3, 3] = [1.0, 0.0, 0.0]
    reference_to_atlas = sitk.Euler3DTransform()
    reference_to_atlas.SetRotation(0.0, 0.0, np.pi / 2.0)
    path = tmp_path / "reference_to_atlas.tfm"
    sitk.WriteTransform(reference_to_atlas, str(path))
    composite = compose_user_to_atlas(user_to_reference, path)
    expected = reference_to_atlas.TransformPoint((2.0, 0.0, 0.0))
    np.testing.assert_allclose(composite.TransformPoint((1.0, 0.0, 0.0)), expected)


def test_atlas_to_user_resampling_composite_uses_inverse_rigid(tmp_path):
    user_to_reference = np.eye(4)
    user_to_reference[:3, 3] = [1.0, 0.0, 0.0]
    atlas_to_reference = sitk.TranslationTransform(3, (5.0, 0.0, 0.0))
    path = tmp_path / "atlas_to_reference.tfm"
    sitk.WriteTransform(atlas_to_reference, str(path))
    composite = compose_atlas_to_user_for_resampling(user_to_reference, path)
    np.testing.assert_allclose(composite.TransformPoint((0.0, 0.0, 0.0)), [4.0, 0.0, 0.0])


def test_vector_atlas_layer_is_resampled_channel_by_channel():
    components = [sitk.Image((5, 5, 5), sitk.sitkFloat32) + value for value in (1.0, 2.0, 3.0)]
    vector = sitk.Compose(components)
    target = sitk.Image((5, 5, 5), sitk.sitkFloat32)
    output = resample_atlas_to_target(
        vector,
        target,
        sitk.Transform(3, sitk.sitkIdentity),
        "linear",
    )
    assert output.GetNumberOfComponentsPerPixel() == 3
    np.testing.assert_allclose(sitk.GetArrayFromImage(output)[2, 2, 2], (1.0, 2.0, 3.0))


def test_target_ct_is_resampled_into_reference_with_exact_inverse_and_coverage():
    target = sitk.GetImageFromArray(np.asarray([[[10.0, 20.0, 30.0]]], dtype=np.float32))
    reference = sitk.Image((5, 1, 1), sitk.sitkFloat32)
    target_to_reference = np.eye(4)
    target_to_reference[0, 3] = 1.0

    mapped, coverage = resample_target_to_reference(
        target,
        reference,
        target_to_reference,
    )

    np.testing.assert_allclose(
        sitk.GetArrayFromImage(mapped).reshape(-1),
        [0.0, 10.0, 20.0, 30.0, 0.0],
    )
    np.testing.assert_array_equal(
        sitk.GetArrayFromImage(coverage).reshape(-1),
        [0, 1, 1, 1, 0],
    )
