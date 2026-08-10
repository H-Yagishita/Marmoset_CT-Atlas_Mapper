from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Mapping

import numpy as np


LPS_TO_RAS = np.diag([-1.0, -1.0, 1.0])


def _coordinate_system_name(value: object) -> str:
    if isinstance(value, str):
        return value.upper()
    # Legacy Slicer Markups uses 0=RAS and 1=LPS.
    if value == 0:
        return "RAS"
    if value == 1:
        return "LPS"
    raise ValueError(f"Unsupported coordinate system: {value!r}")


def load_slicer_markups(path: str | Path) -> dict[str, np.ndarray]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    markups = payload.get("markups", [])
    if len(markups) != 1:
        raise ValueError("Expected exactly one Markups object.")

    markup = markups[0]
    coordinate_system = _coordinate_system_name(markup.get("coordinateSystem", "LPS"))
    points: dict[str, np.ndarray] = {}
    seen_labels: set[str] = set()
    for item in markup.get("controlPoints", []):
        label = str(item.get("label", "")).strip()
        if not label:
            raise ValueError("A control point has no label.")
        if label in seen_labels:
            raise ValueError(f"Duplicate landmark label: {label}")
        seen_labels.add(label)
        if str(item.get("positionStatus", "defined")).lower() != "defined":
            continue
        position = np.asarray(item["position"], dtype=float)
        if position.shape != (3,) or not np.all(np.isfinite(position)):
            raise ValueError(f"Invalid position for {label}: {position}")
        if coordinate_system == "RAS":
            position = LPS_TO_RAS @ position
        elif coordinate_system != "LPS":
            raise ValueError(f"Unsupported coordinate system: {coordinate_system}")
        points[label] = position
    return points


def write_slicer_markups(
    path: str | Path,
    points_lps: Mapping[str, Iterable[float]],
    *,
    name: str = "User_CT_Landmarks",
) -> None:
    control_points = []
    for index, (label, position) in enumerate(points_lps.items(), start=1):
        xyz = np.asarray(tuple(position), dtype=float)
        if xyz.shape != (3,) or not np.all(np.isfinite(xyz)):
            raise ValueError(f"Invalid position for {label}: {xyz}")
        control_points.append(
            {
                "id": str(index),
                "label": label,
                "description": "",
                "associatedNodeID": "",
                "position": xyz.tolist(),
                "orientation": [-1.0, 0.0, 0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 1.0],
                "selected": True,
                "locked": False,
                "visibility": True,
                "positionStatus": "defined",
            }
        )

    payload = {
        "@schema": "https://raw.githubusercontent.com/slicer/slicer/master/Modules/Loadable/Markups/Resources/Schema/markups-schema-v1.0.3.json#",
        "markups": [
            {
                "type": "Fiducial",
                "coordinateSystem": "LPS",
                "coordinateUnits": "mm",
                "locked": False,
                "fixedNumberOfControlPoints": False,
                "labelFormat": name + "_%d",
                "lastUsedControlPointNumber": len(control_points),
                "controlPoints": control_points,
                "measurements": [],
                "display": {
                    "visibility": True,
                    "opacity": 1.0,
                    "color": [0.4, 1.0, 1.0],
                    "selectedColor": [1.0, 0.5, 0.5],
                    "activeColor": [0.4, 1.0, 0.0],
                    "propertiesLabelVisibility": False,
                    "pointLabelsVisibility": True,
                    "glyphType": "Sphere3D",
                    "glyphScale": 3.0,
                    "textScale": 3.0,
                },
            }
        ],
    }
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2), encoding="utf-8")
