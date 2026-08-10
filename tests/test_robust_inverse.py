import numpy as np
import SimpleITK as sitk

from marmoset_atlas_mapper.displacement_consensus import create_target_ras_grid, sample_forward_transform
from marmoset_atlas_mapper.robust_inverse import InverseQCReport, generate_robust_inverse
from marmoset_atlas_mapper.transform_qc import ErrorStatistics
from marmoset_atlas_mapper.transform_composition import transform_points


def image(size=(20, 18, 16), origin=(-9.5, -8.5, -7.5)):
    result = sitk.Image(size, sitk.sitkFloat32)
    result.SetOrigin(origin)
    result.SetSpacing((1.0, 1.0, 1.0))
    return result


def assert_roundtrip(transform):
    target = image()
    atlas = image()
    field = sample_forward_transform(transform, create_target_ras_grid(target, 0.5, 1.0))
    inverse = generate_robust_inverse(
        forward_field=field,
        target_image=target,
        atlas_reference=atlas,
        inverse_spacing_mm=0.5,
        inverse_padding_mm=1.0,
        qc_sample_count=100,
        convergence_tolerance_mm=0.01,
        roundtrip_threshold_mm=0.05,
        minimum_roundtrip_sample_count=10,
    )
    points = np.asarray([(-4.0, -3.0, -2.0), (0.0, 0.0, 0.0), (4.0, 3.0, 2.0)])
    mapped = transform_points(transform, points)
    recovered = transform_points(inverse.inverse_transform, mapped)
    np.testing.assert_allclose(recovered, points, atol=0.02)
    assert inverse.qc.roundtrip.p95_mm < 0.05


def test_translation_inverse():
    transform = sitk.TranslationTransform(3, (1.0, -0.5, 0.75))
    assert_roundtrip(transform)


def test_rigid_rotation_inverse_uses_non_identity_initialization():
    transform = sitk.Euler3DTransform()
    transform.SetCenter((0.0, 0.0, 0.0))
    transform.SetRotation(0.08, -0.06, 0.12)
    transform.SetTranslation((0.5, -0.25, 0.3))
    assert_roundtrip(transform)


def test_partial_atlas_coverage_does_not_fail_inverse_qc():
    report = InverseQCReport(
        roundtrip=ErrorStatistics(0.04, 0.08, 0.2),
        converged_target_samples=30,
        target_sample_count=300,
        valid_inverse_voxels=100,
        inverse_voxel_count=1000,
        valid_atlas_voxels=100,
        atlas_voxel_count=1000,
        threshold_mm=0.25,
        minimum_roundtrip_sample_count=30,
    )
    assert report.atlas_coverage_fraction == 0.1
    assert report.passed


def test_too_few_roundtrip_samples_still_fails_inverse_qc():
    report = InverseQCReport(
        roundtrip=ErrorStatistics(0.04, 0.08, 0.2),
        converged_target_samples=29,
        target_sample_count=300,
        valid_inverse_voxels=100,
        inverse_voxel_count=1000,
        valid_atlas_voxels=1000,
        atlas_voxel_count=1000,
        threshold_mm=0.25,
        minimum_roundtrip_sample_count=30,
    )
    assert not report.passed
