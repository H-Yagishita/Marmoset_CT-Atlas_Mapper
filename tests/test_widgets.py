import numpy as np

from marmoset_atlas_mapper.profile import QCBenchmark
from marmoset_atlas_mapper.widgets import (
    display_xy_to_index,
    extract_display_plane,
    index_to_display_xy,
    plane_pixel_spacing,
    qc_benchmark_state,
)


def test_coronal_and_sagittal_are_displayed_superior_up():
    array = np.arange(2 * 3 * 4).reshape(2, 3, 4)
    np.testing.assert_array_equal(
        extract_display_plane(array, "Coronal", (1, 1, 0)),
        np.flipud(array[:, 1, :]),
    )
    np.testing.assert_array_equal(
        extract_display_plane(array, "Sagittal", (1, 1, 0)),
        np.flipud(array[:, :, 1]),
    )


def test_axial_keeps_lps_radiological_orientation():
    array = np.arange(2 * 3 * 4).reshape(2, 3, 4)
    np.testing.assert_array_equal(extract_display_plane(array, "Axial", (1, 1, 1)), array[1, :, :])


def test_display_coordinate_roundtrip_for_all_orientations():
    index = np.array([2.25, 3.5, 4.75])
    size = (10, 11, 12)
    for orientation in ("Axial", "Coronal", "Sagittal"):
        image_x, image_y = index_to_display_xy(index, orientation, size)
        restored = display_xy_to_index(image_x, image_y, orientation, index, size)
        np.testing.assert_allclose(restored, index)


def test_plane_pixel_spacing_uses_physical_axes():
    spacing = (0.25, 0.25, 0.50)
    assert plane_pixel_spacing("Axial", spacing) == (0.25, 0.25)
    assert plane_pixel_spacing("Coronal", spacing) == (0.25, 0.50)
    assert plane_pixel_spacing("Sagittal", spacing) == (0.25, 0.50)


def test_qc_benchmark_warning_and_context_states():
    benchmark = QCBenchmark(
        condition="test",
        sample_count=12,
        mean_rms_mm=0.616,
        minimum_rms_mm=0.463,
        maximum_rms_mm=0.737,
        warning_threshold_mm=0.737,
        source="test.csv",
    )
    assert qc_benchmark_state(0.80, "Rigid", 8, benchmark) == "warning"
    assert qc_benchmark_state(0.60, "Rigid", 8, benchmark) == "within_reference_range"
    assert qc_benchmark_state(0.60, "Rigid", 5, benchmark) == "context_only"
    assert qc_benchmark_state(0.60, "Similarity", 8, benchmark) == "context_only"
