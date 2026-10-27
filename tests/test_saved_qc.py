import numpy as np

from marmoset_atlas_mapper.saved_qc import _restore_registration


def test_restore_registration_includes_landmark_residual_arrays():
    summary = {
        "Method": "Rigid",
        "FRE_RMS_mm": "0.5",
        "MeanResidual_mm": "0.45",
        "MaximumResidual_mm": "0.7",
        "UniformScale": "1.0",
    }
    rows = [
        {
            "Label": "LM02",
            "Residual_mm": "0.6",
            "dL_mm": "0.1",
            "dP_mm": "0.2",
            "dS_mm": "0.3",
        },
        {
            "Label": "LM01",
            "Residual_mm": "0.4",
            "dL_mm": "-0.1",
            "dP_mm": "-0.2",
            "dS_mm": "-0.3",
        },
    ]

    restored = _restore_registration(summary, ("LM01", "LM02"), rows)

    np.testing.assert_allclose(restored.residual_distances, [0.4, 0.6])
    np.testing.assert_allclose(
        restored.residual_vectors,
        [[-0.1, -0.2, -0.3], [0.1, 0.2, 0.3]],
    )


def test_restore_registration_marks_missing_legacy_residuals_as_nan():
    summary = {
        "Method": "Similarity",
        "FRE_RMS_mm": "0.5",
        "MeanResidual_mm": "0.45",
        "MaximumResidual_mm": "0.7",
        "UniformScale": "1.02",
    }

    restored = _restore_registration(summary, ("LM01",), [])

    assert np.isnan(restored.residual_distances[0])
    assert np.isnan(restored.residual_vectors[0]).all()
