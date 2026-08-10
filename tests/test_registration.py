import numpy as np

from marmoset_atlas_mapper.registration import (
    apply_matrix,
    register_landmarks,
    rigid_matrix,
    similarity_matrix,
)


def test_rigid_matrix_recovers_known_transform():
    moving = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [2.0, -1.0, 0.5],
        ]
    )
    angle = np.deg2rad(31.0)
    rotation = np.array(
        [
            [np.cos(angle), -np.sin(angle), 0.0],
            [np.sin(angle), np.cos(angle), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    expected = np.eye(4)
    expected[:3, :3] = rotation
    expected[:3, 3] = [4.0, -2.0, 0.75]
    fixed = apply_matrix(expected, moving)

    actual = rigid_matrix(moving, fixed)
    np.testing.assert_allclose(actual, expected, atol=1e-10)
    np.testing.assert_allclose(np.linalg.det(actual[:3, :3]), 1.0, atol=1e-12)


def test_registration_residuals_are_reported_in_label_order():
    moving = {
        "LM01": np.array([0.0, 0.0, 0.0]),
        "LM02": np.array([1.0, 0.0, 0.0]),
        "LM03": np.array([0.0, 1.0, 0.0]),
        "LM04": np.array([0.0, 0.0, 1.0]),
    }
    offset = np.array([2.0, 3.0, 4.0])
    fixed = {key: value + offset for key, value in moving.items()}
    result = register_landmarks(moving, fixed, ["LM04", "LM01", "LM02", "LM03"])
    np.testing.assert_allclose(result.matrix_lps[:3, 3], offset, atol=1e-10)
    np.testing.assert_allclose(result.residual_distances, 0.0, atol=1e-10)
    assert result.labels == ("LM04", "LM01", "LM02", "LM03")


def test_collinear_landmarks_are_rejected():
    moving = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]])
    try:
        rigid_matrix(moving, moving)
    except ValueError as exc:
        assert "collinear" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_similarity_matrix_recovers_uniform_scale_rotation_and_translation():
    moving = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [2.0, -1.0, 0.5],
        ]
    )
    angle = np.deg2rad(-23.0)
    rotation = np.array(
        [
            [np.cos(angle), -np.sin(angle), 0.0],
            [np.sin(angle), np.cos(angle), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    expected = np.eye(4)
    expected[:3, :3] = 1.17 * rotation
    expected[:3, 3] = [-3.0, 4.5, 0.2]
    fixed = apply_matrix(expected, moving)

    actual = similarity_matrix(moving, fixed)
    np.testing.assert_allclose(actual, expected, atol=1e-10)


def test_registration_accepts_selected_subset_and_similarity_method():
    moving = {
        "LM01": np.array([0.0, 0.0, 0.0]),
        "LM02": np.array([1.0, 0.0, 0.0]),
        "LM03": np.array([0.0, 1.0, 0.0]),
        "LM04": np.array([0.0, 0.0, 1.0]),
    }
    matrix = np.eye(4)
    matrix[:3, :3] *= 1.1
    matrix[:3, 3] = [2.0, 3.0, 4.0]
    fixed = {key: apply_matrix(matrix, value)[0] for key, value in moving.items()}
    result = register_landmarks(moving, fixed, ["LM01", "LM02", "LM03"], method="Similarity")
    assert result.method == "Similarity"
    assert result.labels == ("LM01", "LM02", "LM03")
    np.testing.assert_allclose(result.uniform_scale, 1.1, atol=1e-10)
