import numpy as np
import pytest

from marmoset_atlas_mapper.landmark_validation import select_common_landmarks


LABELS = ("LM01", "LM02", "LM03", "LM04", "LM05")


def points(labels=LABELS):
    base = {
        "LM01": (0.0, 0.0, 0.0),
        "LM02": (1.0, 0.0, 0.0),
        "LM03": (0.0, 1.0, 0.0),
        "LM04": (0.0, 0.0, 1.0),
        "LM05": (1.0, 1.0, 1.0),
    }
    return {label: np.asarray(base[label]) for label in labels}


def references(reference_points=None):
    reference_points = reference_points or points()
    return {f"R{i}": dict(reference_points) for i in range(4)}


def test_common_subset_is_label_based_and_preserves_requested_order():
    target = points()
    shuffled = ("LM04", "LM01", "LM05", "LM03", "LM02")
    subset = select_common_landmarks(
        target,
        references(),
        shuffled,
        allowed_labels=LABELS,
    )
    assert subset.labels == shuffled


def test_missing_landmark_is_removed_from_every_reference_route():
    target = points(("LM01", "LM02", "LM03", "LM04"))
    refs = references()
    refs["R2"].pop("LM04")
    subset = select_common_landmarks(target, refs, LABELS, allowed_labels=LABELS)
    assert subset.labels == ("LM01", "LM02", "LM03")
    assert "R2" in subset.missing_by_dataset
    assert subset.warnings


def test_duplicate_requested_label_is_rejected():
    with pytest.raises(ValueError, match="duplicates"):
        select_common_landmarks(
            points(), references(), ("LM01", "LM02", "LM03", "LM03"), allowed_labels=LABELS
        )


def test_collinear_points_are_rejected():
    collinear = {
        "LM01": np.asarray((0.0, 0.0, 0.0)),
        "LM02": np.asarray((1.0, 0.0, 0.0)),
        "LM03": np.asarray((2.0, 0.0, 0.0)),
    }
    with pytest.raises(ValueError, match="collinear"):
        select_common_landmarks(
            collinear,
            references(collinear),
            tuple(collinear),
            allowed_labels=LABELS,
        )
