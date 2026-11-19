from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import bundled_config_root, configured_resource_root


@dataclass(frozen=True)
class AtlasLayer:
    name: str
    path: Path
    interpolation: str


@dataclass(frozen=True)
class AtlasProfile:
    profile_id: str
    display_name: str
    atlas_space: str
    reference_id: str
    registration_method: str
    registration_labels: tuple[str, ...]
    reference_ct: Path
    reference_landmarks: Path
    reference_to_atlas_point_transform: Path
    atlas_reference: Path
    atlas_layers: tuple[AtlasLayer, ...]
    atlas_label_map: Path
    atlas_color_table: Path
    license_name: str
    source_url: str

    def missing_files(self) -> list[Path]:
        paths = [
            self.reference_ct,
            self.reference_landmarks,
            self.reference_to_atlas_point_transform,
            self.atlas_reference,
            self.atlas_label_map,
            self.atlas_color_table,
        ] + [layer.path for layer in self.atlas_layers]
        return sorted({path for path in paths if not path.is_file()})


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (root / path).resolve()


def _profile_from_dict(data: dict[str, Any], root: Path) -> AtlasProfile:
    layers = tuple(
        AtlasLayer(name=name, path=_resolve(root, item["path"]), interpolation=item["interpolation"])
        for name, item in data["atlas_layers"].items()
    )
    return AtlasProfile(
        profile_id=data["id"],
        display_name=data["display_name"],
        atlas_space=data["atlas_space"],
        reference_id=data["reference_id"],
        registration_method=data["registration_method"],
        registration_labels=tuple(data["registration_labels"]),
        reference_ct=_resolve(root, data["reference_ct"]),
        reference_landmarks=_resolve(root, data["reference_landmarks"]),
        reference_to_atlas_point_transform=_resolve(root, data["reference_to_atlas_point_transform"]),
        atlas_reference=_resolve(root, data["atlas_reference"]),
        atlas_layers=layers,
        atlas_label_map=_resolve(root, data["atlas_label_map"]),
        atlas_color_table=_resolve(root, data["atlas_color_table"]),
        license_name=data["license"],
        source_url=data["source_url"],
    )


def load_profiles(path: Path | None = None) -> list[AtlasProfile]:
    config_path = path or bundled_config_root() / "atlas_profiles.json"
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    root = configured_resource_root()
    if "references" in payload:
        shared = payload["shared"]
        profiles = []
        for reference in payload["references"]:
            item = {**shared, **reference}
            profiles.append(_profile_from_dict(item, root))
        return profiles
    return [_profile_from_dict(item, root) for item in payload["profiles"]]
