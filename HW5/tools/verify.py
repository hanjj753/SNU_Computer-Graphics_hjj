"""Verify the renderer and deliverables in snu_graphics_hjj."""

import ast
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify():
    sys.path.insert(0, str(ROOT / "code"))
    output = ROOT / "outputs"
    output.mkdir(exist_ok=True)
    checks = {}
    forbidden = []
    for path in (ROOT / "code").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else ([node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            forbidden.extend(f"{path.name}:{node.lineno}: {name}" for name in names
                             if name.split(".")[0] in {"pyglet", "OpenGL", "moderngl", "bpy", "taichi", "mitsuba"})
    checks["cpu_renderer_without_opengl"] = {"passed": not forbidden, "forbidden_imports": forbidden}

    log = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    (output / "test_results.txt").write_text(log.getvalue(), encoding="utf-8")
    print(log.getvalue(), end="")
    checks["tests"] = {"passed": result.wasSuccessful(), "run": result.testsRun,
                       "failures": len(result.failures), "errors": len(result.errors), "log": "test_results.txt"}

    # Restrict automatic temporary-directory removal to this workspace.
    temporary_root = ROOT / "tmp"
    temporary_root.mkdir(exist_ok=True)
    assert temporary_root.resolve().is_relative_to(ROOT.resolve())
    with tempfile.TemporaryDirectory(prefix="verify_", dir=temporary_root) as temp:
        folder = Path(temp).resolve()
        assert folder.is_relative_to(ROOT.resolve())
        # Invoke an executable named python, with this verified environment first.
        env = os.environ.copy()
        env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
        image = folder / "entrypoint.png"
        command = ["python", "main.py", "render", "--width", "48", "--height", "36", "--spp", "4",
                   "--max-depth", "8", "--output", str(image), "--quiet"]
        run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
        checks["python_main_entrypoint"] = {"passed": run.returncode == 0 and image.exists(),
                                            "command": "python main.py render --width 48 --height 36 --spp 4 --max-depth 8",
                                            "python": sys.executable, "exit_code": run.returncode,
                                            "stdout": run.stdout, "stderr": run.stderr}

    required = ["main.py", "scene.json", "References.md",
                "pictures/Cornell Box.jpg", "pictures/HW4_render.png", "report/HW5_Report.pdf",
                "demo/HW5_A1_Poster.pdf", "demo/README.md", "outputs/cornell.png",
                "outputs/cornell_denoised.png", "outputs/reference.png", "outputs/comparison/results.json",
                "outputs/comparison/details.png", "outputs/benchmark/timings.json", "outputs/penumbra_validation.json"]
    missing = [name for name in required if not (ROOT / name).is_file()]
    checks["required_deliverables"] = {"passed": not missing, "missing": missing}
    benchmark = json.loads((output / "benchmark" / "timings.json").read_text(encoding="utf-8"))
    checks["bvh_same_image"] = {"passed": benchmark["same_image"],
                                "max_abs_difference": benchmark["linear_max_abs_difference"],
                                "median_render_seconds": benchmark["median_render_seconds"],
                                "speedup": benchmark["speedup"]}
    cases = json.loads((output / "comparison" / "results.json").read_text(encoding="utf-8"))["cases"]
    expected = {"full", "indirect", "shadows", "reflections", "refraction", "textures", "aa", "dof", "absorption"}
    checks["feature_comparisons"] = {"passed": expected.issubset(cases), "cases": sorted(cases)}
    penumbra = json.loads((output / "penumbra_validation.json").read_text(encoding="utf-8"))
    checks["penumbra_integration"] = {"passed": penumbra["passed"],
                                      "maximum_visibility_error": penumbra["maximum_visibility_error"]}
    provenance = json.loads((ROOT / "assets" / "source_manifest.json").read_text(encoding="utf-8"))
    model_digest = hashlib.sha256((ROOT / "assets/models/cornell_scene.obj").read_bytes()).hexdigest()
    checks["assignment2_scene"] = {"passed": model_digest == provenance["hw2_obj_sha256"], "sha256": model_digest}
    checks["human_actions"] = {"demo_day_attendance": "pending user action",
                                "etl_upload": "pending user action"}
    passed = all(check["passed"] for check in checks.values() if "passed" in check)
    sources = {str(path.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
               for path in [ROOT / "main.py", ROOT / "scene.json", *sorted((ROOT / "code").glob("*.py"))]}
    evidence = {"verified_at_kst": datetime.now(timezone(timedelta(hours=9))).isoformat(),
                "software_and_files_passed": passed, "checks": checks, "source_sha256": sources,
                "scope": "Local software and deliverables only; Demo Day participation and ETL upload cannot be verified locally."}
    (output / "verification.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Local software/files passed: {passed}; evidence: {output / 'verification.json'}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(verify())
