from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

def smoke_test() -> int:
    import SimpleITK as sitk

    from marmoset_atlas_mapper.imaging import VolumeData
    from marmoset_atlas_mapper.landmarks import load_slicer_markups
    from marmoset_atlas_mapper.profile import load_profiles
    from marmoset_atlas_mapper.reference_library import load_reference_library
    from marmoset_atlas_mapper.transform_io import read_transform

    profiles = load_profiles()
    library = load_reference_library()
    if not profiles:
        raise RuntimeError("No atlas profiles found.")
    for profile in profiles:
        missing = profile.missing_files()
        if missing:
            raise FileNotFoundError("Missing profile files: " + ", ".join(map(str, missing)))
        VolumeData.read(profile.reference_ct)
        points = load_slicer_markups(profile.reference_landmarks)
        if any(label not in points for label in profile.registration_labels):
            raise RuntimeError(f"{profile.reference_id} registration landmarks are incomplete.")
        forward = read_transform(profile.reference_to_atlas_point_transform)
        del forward
    if len(library.references) != 4:
        raise RuntimeError("K04 reference library must contain exactly four references.")
    if library.missing_files():
        raise FileNotFoundError("K04 reference library is incomplete.")
    return 0


if __name__ == "__main__":
    if "--smoke-test" in sys.argv:
        raise SystemExit(smoke_test())
    from marmoset_atlas_mapper.main_window import run

    raise SystemExit(run())
