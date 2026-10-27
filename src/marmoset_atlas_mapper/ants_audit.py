"""Opt-in disposable end-to-end ANTs check, including the frozen launcher boundary."""
from pathlib import Path
import json
import traceback
import numpy as np
import SimpleITK as sitk
from .ants_registration import discover_ants_runtime, load_parameters, runtime_info, run_ants
from .registration import register_landmarks


def audit(report_path):
    report = Path(report_path).resolve()
    report.parent.mkdir(parents=True, exist_ok=True)
    root = report.with_suffix("")
    # Never overwrite an existing registration or test run.
    root.mkdir(exist_ok=False)
    details = {"status": "Running", "checks": [], "output": str(root)}
    try:
        runtime = discover_ants_runtime()
        parameters = load_parameters()
        software = runtime_info(runtime, parameters["threads_per_job"])
        details["software"] = software
        z, y, x = np.indices((48, 48, 48), dtype=float)
        array = np.exp(-((x-23)**2/100+(y-21)**2/144+(z-24)**2/81))
        array += .7*np.exp(-((x-31)**2/16+(y-26)**2/25+(z-21)**2/16))
        array += .4*np.exp(-((x-19)**2/9+(y-31)**2/16+(z-29)**2/25))
        # Distinct edges and asymmetric texture prevent the scale/intensity
        # ambiguity of a nearly single-Gaussian MI phantom.
        ellipsoid = (x-23)**2/17**2 + (y-22)**2/15**2 + (z-24)**2/18**2
        array += 1.5*((ellipsoid > .75) & (ellipsoid < 1.))
        rng = np.random.default_rng(91)
        for _ in range(30):
            cx, cy, cz = rng.uniform(12, 36, 3)
            radius = rng.uniform(1.5, 3.5)
            array += rng.uniform(.2, 1.)*np.exp(-((x-cx)**2+(y-cy)**2+(z-cz)**2)/radius**2)
        image = sitk.GetImageFromArray((array/array.max()).astype("float32"))
        image.SetSpacing((.5,)*3)
        image.SetOrigin((-12,)*3)
        fixed_path = root / "fixed.nrrd"
        sitk.WriteImage(image, str(fixed_path))
        fixed_points = {f"LM{i:02}": np.array(p, float) for i,p in enumerate(
            [(0,0,0),(3,0,0),(0,3,0),(0,0,3),(-3,2,-2)], 1)}
        angle = .08
        rotation = np.array([[np.cos(angle),-np.sin(angle),0],
                             [np.sin(angle), np.cos(angle),0],[0,0,1]])
        shift = np.array([1.5,-1.,.75])
        details["errors_mm"] = {}
        for method, scale in (("Rigid",1.), ("Similarity",1.06)):
            moving = sitk.Image(image)
            moving.SetSpacing(tuple(np.array(image.GetSpacing())*scale))
            moving.SetDirection(tuple(rotation.ravel()))
            moving.SetOrigin(tuple(scale*rotation@np.array(image.GetOrigin())+shift))
            moving_path = root / f"{method}_moving.nrrd"
            sitk.WriteImage(moving, str(moving_path))
            moving_points = {key: scale*rotation@point+shift for key,point in fixed_points.items()}
            initial = register_landmarks(moving_points, fixed_points, tuple(fixed_points), method="Rigid").matrix_lps
            initial[0,3] += .3  # Nonzero residual to refine, not a trivial identity.
            fitted = run_ants(moving_ct=moving_path, fixed_ct=fixed_path,
                initial_matrix_lps=initial, method=method, output_directory=root/method,
                moving_landmarks=moving_points, fixed_landmarks=fixed_points, labels=tuple(fixed_points),
                runtime=runtime, parameters=parameters, software=software)
            details["errors_mm"][method] = fitted.rms_mm
            assert fitted.rms_mm < .2, (method, fitted.rms_mm)
            assert abs(fitted.uniform_scale - 1/scale) < .02
        details["checks"] = ["standalone ANTs Rigid and Similarity with normalized phantom",
            "nonzero rotation, translation and scale", "pull/forward convention",
            "true isotropic 7 DOF", "save/reload H5"]
        details["status"] = "Passed"
    except Exception:
        details.update(status="Failed", traceback=traceback.format_exc())
    report.write_text(json.dumps(details, indent=2), encoding="utf-8")
    return 0 if details["status"] == "Passed" else 1
