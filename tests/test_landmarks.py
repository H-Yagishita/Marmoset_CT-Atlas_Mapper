import json

import numpy as np
import pytest

from marmoset_atlas_mapper.landmarks import load_slicer_markups, write_slicer_markups


def test_markups_round_trip_lps(tmp_path):
    expected = {"LM01": np.array([1.0, 2.0, 3.0]), "LM02": np.array([-4.0, 5.0, 6.0])}
    path = tmp_path / "points.mrk.json"
    write_slicer_markups(path, expected)
    actual = load_slicer_markups(path)
    assert list(actual) == ["LM01", "LM02"]
    for label in expected:
        np.testing.assert_allclose(actual[label], expected[label])


def test_ras_markups_are_converted_to_lps(tmp_path):
    payload = {
        "markups": [
            {
                "coordinateSystem": "RAS",
                "controlPoints": [
                    {"label": "LM01", "position": [1, 2, 3], "positionStatus": "defined"}
                ],
            }
        ]
    }
    path = tmp_path / "ras.mrk.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    actual = load_slicer_markups(path)
    np.testing.assert_allclose(actual["LM01"], [-1, -2, 3])


def test_undefined_point_is_excluded(tmp_path):
    payload = {
        "markups": [{
            "coordinateSystem": "LPS",
            "controlPoints": [
                {"label": "LM01", "position": [1, 2, 3], "positionStatus": "undefined"},
                {"label": "LM02", "position": [4, 5, 6], "positionStatus": "defined"},
            ],
        }]
    }
    path = tmp_path / "undefined.mrk.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert list(load_slicer_markups(path)) == ["LM02"]


def test_duplicate_label_is_rejected_even_when_one_point_is_undefined(tmp_path):
    payload = {
        "markups": [{
            "coordinateSystem": "LPS",
            "controlPoints": [
                {"label": "LM01", "position": [1, 2, 3], "positionStatus": "undefined"},
                {"label": "LM01", "position": [4, 5, 6], "positionStatus": "defined"},
            ],
        }]
    }
    path = tmp_path / "duplicate.mrk.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        load_slicer_markups(path)
