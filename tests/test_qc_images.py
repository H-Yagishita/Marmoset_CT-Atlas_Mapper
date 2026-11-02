"""Saved QC overlays use the same magenta/green channels as the live viewer."""
import numpy as np
import SimpleITK as sitk

from marmoset_atlas_mapper.qc_images import write_overlay_triplet


def test_saved_triplet_channels_and_filenames(tmp_path):
    z, y, x = np.indices((2, 2, 2))
    base_array = ((x + y) % 2).astype(float)
    overlay_array = ((y + z) % 2).astype(float)
    base = sitk.GetImageFromArray(base_array)
    overlay = sitk.GetImageFromArray(overlay_array)
    original_base = sitk.GetArrayFromImage(base).copy()
    original_overlay = sitk.GetArrayFromImage(overlay).copy()
    files = write_overlay_triplet(base, overlay, (0, 0, 0), tmp_path, "AtlasConsensus_Overlay")
    expected_base = [base_array[0], np.flipud(base_array[:, 0, :]), np.flipud(base_array[:, :, 0])]
    expected_overlay = [overlay_array[0], np.flipud(overlay_array[:, 0, :]), np.flipud(overlay_array[:, :, 0])]
    assert [path.name for path in files] == [
        f"AtlasConsensus_Overlay_{axis}.png" for axis in ("Axial", "Coronal", "Sagittal")]
    for path, green, magenta in zip(files, expected_base, expected_overlay):
        rgb = sitk.GetArrayFromImage(sitk.ReadImage(str(path)))
        np.testing.assert_array_equal(rgb[..., 0], magenta * 255)
        np.testing.assert_array_equal(rgb[..., 2], magenta * 255)
        np.testing.assert_array_equal(rgb[..., 1], green * 255)
        assert set(map(tuple, rgb.reshape(-1, 3))) == {
            (0, 0, 0), (0, 255, 0), (255, 0, 255), (255, 255, 255)}
    np.testing.assert_array_equal(sitk.GetArrayFromImage(base), original_base)
    np.testing.assert_array_equal(sitk.GetArrayFromImage(overlay), original_overlay)
