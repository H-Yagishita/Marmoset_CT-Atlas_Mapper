import pytest

from marmoset_atlas_mapper.profile import load_profiles
from marmoset_atlas_mapper.reference_library import load_reference_library
from marmoset_atlas_mapper.landmarks import load_slicer_markups


def test_all_six_reference_profiles_are_complete():
    profiles = load_profiles()
    assert [profile.reference_id for profile in profiles] == ["HH0312F", "HH0424M", "HH0428M", "HJ0285F", "J0476M", "J0477M"]
    if any(profile.missing_files() for profile in profiles):
        pytest.skip("Optional reference-data integration check requires the local data library.")
    assert all(not profile.missing_files() for profile in profiles)


def test_reference_library_contains_all_thirteen_public_landmarks():
    library = load_reference_library(validate_files=False)
    assert library.allowed_labels == tuple(f"LM{index:02d}" for index in range(1, 14))
    if library.missing_files():
        pytest.skip("Optional landmark-data integration check requires the local data library.")
    for reference in library.references:
        points = load_slicer_markups(reference.landmarks_path)
        assert all(label in points for label in library.allowed_labels)
