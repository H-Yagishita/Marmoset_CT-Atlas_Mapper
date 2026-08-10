import numpy as np
import SimpleITK as sitk

from marmoset_atlas_mapper.brainsfit_registration import transform_to_matrix_lps
from marmoset_atlas_mapper.imaging import matrix_to_sitk_affine


def test_linear_itk_transform_is_recovered_as_homogeneous_matrix():
    angle = np.deg2rad(17.0)
    matrix = np.eye(4)
    matrix[:3, :3] = np.array(
        [
            [np.cos(angle), -np.sin(angle), 0.0],
            [np.sin(angle), np.cos(angle), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    matrix[:3, 3] = [3.0, -4.0, 1.5]
    recovered = transform_to_matrix_lps(matrix_to_sitk_affine(matrix))
    np.testing.assert_allclose(recovered, matrix, atol=1e-8)


def test_composite_linear_transform_is_recovered():
    first = sitk.TranslationTransform(3, (1.0, 2.0, 3.0))
    second = sitk.ScaleTransform(3, (1.1, 1.1, 1.1))
    transform = sitk.CompositeTransform([first, second])
    matrix = transform_to_matrix_lps(transform)
    points = np.asarray([[0.0, 0.0, 0.0], [2.0, -1.0, 4.0]])
    expected = np.asarray([transform.TransformPoint(tuple(point)) for point in points])
    homogeneous = np.column_stack([points, np.ones(len(points))])
    np.testing.assert_allclose((matrix @ homogeneous.T).T[:, :3], expected)
