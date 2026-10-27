"""Build a portable library from the exact inputs used by the manuscript.

Native ANTs H5s are pull transforms; invert component deformation fields,
then validate point-forward exports against the saved Slicer evaluation.
All artifacts are staged. No analysis inputs or installed library are edited.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import SimpleITK as sitk


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def forward_inverse(transform):
    if transform.GetName() == "CompositeTransform":
        result = sitk.CompositeTransform(3)
        for i in reversed(range(transform.GetNumberOfTransforms())):
            result.AddTransform(forward_inverse(transform.GetNthTransform(i)))
        result.FlattenTransform()
        return result
    if transform.GetName() == "DisplacementFieldTransform":
        field = sitk.DisplacementFieldTransform(transform).GetDisplacementField()
        print(f"  Inverting deformation: {field.GetSize()}, spacing={field.GetSpacing()}", flush=True)
        inverse = sitk.InvertDisplacementField(field, maximumNumberOfIterations=80,
            maxErrorToleranceThreshold=0.001, meanErrorToleranceThreshold=0.0001,
            enforceBoundaryCondition=True)
        return sitk.DisplacementFieldTransform(inverse)
    return transform.GetInverse()


def apply(transform, points):
    return np.array([transform.TransformPoint(tuple(p)) for p in points])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis-root", type=Path, required=True)
    parser.add_argument("--evaluation-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config-template", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.analysis_root.resolve(), args.output.resolve()
    if root == output or root in output.parents:
        raise ValueError("Stage outside the immutable analysis root.")
    manifest = read(root / "01_Transforms/manifest.json")
    evaluation = args.evaluation_run.resolve()
    input_files = read(evaluation / "InputManifest.json")["files"]
    records = [r for r in manifest["subjects"] if r["cohort"] == "Reference"]
    if len(records) != 6:
        raise ValueError("The manuscript library must contain six reference subjects.")
    package = output / "package"
    hashes, sources, validation, references, profiles = {}, {}, {}, [], []

    def copy_checked(source, destination, expected=None):
        source = source.resolve(strict=True)
        if source.is_symlink() or not source.is_file():
            raise ValueError(f"Not a regular source file: {source}")
        digest = sha(source)
        if expected is not None and digest != expected:
            raise ValueError(f"Manuscript input has changed: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(source, destination)
        if sha(destination) != digest:
            raise ValueError(f"Staged copy differs: {destination}")
        return digest

    for record in records:
        identity = record["id"]
        print(f"Preparing {identity}", flush=True)
        ct_rel = f"data/reference_v2/{identity}_CT.nii.gz"
        lm_rel = f"data/reference_v2/{identity}_Landmarks.mrk.json"
        mri_rel = f"data/reference_v2/{identity}_MRI_t2r.nii.gz"
        forward_rel = f"data/transforms_v2/{identity}_CT_to_BMA2_PointTransform.h5"
        for source_rel, target_rel in [(record["images"]["ct"], ct_rel),
                                       (record["landmarks"]["path"], lm_rel),
                                       (record["images"]["mri"], mri_rel)]:
            expected = input_files.get(source_rel, {}).get("sha256")
            if target_rel != mri_rel and expected is None:
                raise ValueError(f"Input not recorded by evaluation: {source_rel}")
            digest = copy_checked(root / source_rel, package / target_rel, expected)
            hashes[target_rel] = digest
            sources[target_rel] = {"source_relative": source_rel, "sha256": digest}
        native = []
        for key in ("ct_to_mri", "mri_to_atlas"):
            rel = record[key]
            local = output / "native_transform_cache" / identity / Path(rel).name
            digest = copy_checked(root / rel, local, input_files[rel]["sha256"])
            sources[f"{identity}/{key}"] = {"source_relative": rel, "sha256": digest}
            native.append(sitk.ReadTransform(str(local)))
        pull = sitk.CompositeTransform(native)
        pull.FlattenTransform()
        destination = package / forward_rel
        if destination.exists():
            forward = sitk.ReadTransform(str(destination))
        else:
            forward = forward_inverse(pull)
        truth_path = evaluation / "Direct" / f"{identity}.npz"
        with np.load(truth_path) as truth:
            sign = np.array([-1., -1., 1.])
            points = truth["target_ct_ras"] * sign
            expected = truth["direct_atlas_ras"] * sign
        mapped = apply(forward, points)
        discrepancy = np.linalg.norm(mapped - expected, axis=1)
        roundtrip = np.linalg.norm(apply(pull, mapped) - points, axis=1)
        stats = {"points": len(points), "manuscript_p95_mm": float(np.percentile(discrepancy, 95)),
                 "manuscript_max_mm": float(discrepancy.max()), "roundtrip_p95_mm": float(np.percentile(roundtrip, 95)),
                 "roundtrip_max_mm": float(roundtrip.max()), "truth_sha256": sha(truth_path)}
        print(f"  QC: {stats}", flush=True)
        if not np.isfinite(mapped).all() or stats["manuscript_p95_mm"] >= .01 or stats["manuscript_max_mm"] >= .05 or stats["roundtrip_max_mm"] >= .05:
            raise ValueError(f"Forward transform QC failed for {identity}: {stats}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            sitk.WriteTransform(forward, str(destination))
        reloaded = sitk.ReadTransform(str(destination))
        stats["saved_reload_max_mm"] = float(np.linalg.norm(apply(reloaded, points[::17]) - mapped[::17], axis=1).max())
        if stats["saved_reload_max_mm"] > 1e-9:
            raise ValueError("Saved/reloaded point transform changed coordinates")
        hashes[forward_rel] = sha(destination)
        validation[identity] = stats
        write(output / "validation_progress.json", validation)
        references.append({"id": identity, "ct": ct_rel, "landmarks": lm_rel, "mri": mri_rel,
                           "ct_to_atlas_forward": forward_rel})
        profiles.append({"id": "bma2_" + identity.lower(), "display_name": f"BMA 2.0 ({identity} reference)",
                         "reference_id": identity, "reference_ct": ct_rel, "reference_landmarks": lm_rel,
                         "reference_to_atlas_point_transform": forward_rel})
        del native, pull, forward, reloaded
        gc.collect()
    library = read(args.config_template / "reference_library.json")
    library.update(library_id="bma2_manuscript_nref6_v2", expected_reference_count=6,
                   dataset_version="2.0.0", analysis_id=manifest["analysis_id"], references=references)
    profile = read(args.config_template / "atlas_profiles.json")
    profile["references"] = profiles
    for rel in sorted({library["atlas"]["reference_image"], library["atlas"]["label_map"],
                       library["atlas"]["color_table"], *[v["path"] for v in library["atlas"]["layers"].values()]}):
        source = root / "00_Data/BMA2.0_Atlas" / Path(rel).name
        hashes[rel] = copy_checked(source, package / rel)
        sources[rel] = {"source_relative": source.relative_to(root).as_posix(), "sha256": hashes[rel]}
    provenance_rel = "data/reference_v2/PROVENANCE.json"
    write(package / provenance_rel, {"status": "Passed", "analysis_id": manifest["analysis_id"],
        "reference_count": 6, "transform_origin": "260911 CT-to-MRI and MRI-to-Atlas, as reused by manuscript analysis",
        "landmark_origin": "Fresh manuscript landmarks; no exploratory optimization substituted",
        "sources": sources, "forward_transform_validation": validation})
    hashes[provenance_rel] = sha(package / provenance_rel)
    catalog = read(args.config_template / "reference_data_catalog.json")
    catalog.update(dataset_id="bma2-manuscript-nref6-reference-library", display_name="BMA 2.0 / Nref=6 Marmoset CT Reference Library",
                   version="2.0.0", required_files=sorted(hashes), file_sha256=hashes)
    catalog["license_summary"] = "BMA 2.0: CC BY 4.0. Reference-data redistribution permission must be confirmed before publication."
    catalog["package"] = {"filename": "MarmosetAtlasMapper_Data_v2.0.zip", "sha256": "", "size_bytes": None}
    for name, payload in [("reference_library.json", library), ("atlas_profiles.json", profile), ("reference_data_catalog.json", catalog)]:
        write(output / "config" / name, payload)
    write(output / "BuildReport.json", {"status": "Passed", "Nref": 6, "reference_ids": [r["id"] for r in records],
                                       "validation": validation, "files": hashes})
    print("LIBRARY COMPLETE: " + str(package), flush=True)


if __name__ == "__main__":
    main()
