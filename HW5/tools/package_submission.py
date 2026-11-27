"""Build and integrity-check one self-contained ETL submission ZIP."""

import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def package():
    required = ["main.py", "scene.json", "README.md", "REQUIREMENTS.md",
                "report/HW5_Report.pdf", "demo/HW5_A1_Poster.pdf", "outputs/verification.json"]
    missing = [p for p in required if not (ROOT / p).is_file()]
    if missing:
        raise SystemExit("Missing required files: " + ", ".join(missing))
    verification = json.loads((ROOT / "outputs/verification.json").read_text(encoding="utf-8"))
    if not verification["software_and_files_passed"]:
        raise SystemExit("Run python tools/verify.py and resolve failing checks before packaging")
    excluded_dirs = {"dist", "tmp", "__pycache__", ".venv", ".git"}
    files = [path for path in ROOT.rglob("*") if path.is_file()
             and not any(part in excluded_dirs for part in path.relative_to(ROOT).parts)
             and path.suffix.lower() not in {".pyc", ".pyo", ".npy", ".npz", ".nbi", ".nbc"}
             and not path.name.endswith("_progress.png")]
    manifest = {str(path.relative_to(ROOT)).replace("\\", "/"): {"bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(files)}
    target = ROOT / "dist" / "HW5_Submission.zip"
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(files):
            archive.write(path, "HW5/" + str(path.relative_to(ROOT)).replace("\\", "/"))
        archive.writestr("HW5/SUBMISSION_MANIFEST.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP CRC integrity verification failed")
        for name, record in manifest.items():
            if hashlib.sha256(archive.read("HW5/" + name)).hexdigest() != record["sha256"]:
                raise RuntimeError("ZIP hash mismatch: " + name)
    temporary_root = ROOT / "tmp"
    temporary_root.mkdir(exist_ok=True)
    assert temporary_root.resolve().is_relative_to(ROOT.resolve())
    with tempfile.TemporaryDirectory(prefix="submission_", dir=temporary_root) as temp:
        extracted = Path(temp).resolve()
        assert extracted.is_relative_to(ROOT.resolve())
        with zipfile.ZipFile(target) as archive:
            for name in archive.namelist():
                resolved = (extracted / name).resolve()
                if not resolved.is_relative_to(extracted):
                    raise RuntimeError("Unsafe ZIP member: " + name)
            archive.extractall(extracted)
        output = extracted / "standalone.png"
        command = [sys.executable, "main.py", "render", "--width", "64", "--height", "48", "--spp", "4",
                   "--max-depth", "8", "--output", str(output), "--quiet"]
        run = subprocess.run(command, cwd=extracted / "HW5", capture_output=True, text=True, timeout=180)
        standalone = {"passed": run.returncode == 0 and output.is_file(),
                      "command": "python main.py render --width 64 --height 48 --spp 4 --max-depth 8",
                      "python": sys.executable, "exit_code": run.returncode,
                      "stdout": run.stdout, "stderr": run.stderr,
                      "isolated_assets": True, "source_manifest_file_count": len(manifest)}
        if not standalone["passed"]:
            raise RuntimeError("Extracted ZIP cannot render: " + run.stderr)
    with zipfile.ZipFile(target, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("HW5/ARCHIVE_VERIFICATION.json", json.dumps(standalone, ensure_ascii=False, indent=2))
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Final archive CRC verification failed")
    standalone["zip_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    standalone["zip_bytes"] = target.stat().st_size
    (target.parent / "package_verification.json").write_text(json.dumps(standalone, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {target}: {len(files)} files, {target.stat().st_size / 1024 ** 2:.2f} MiB; "
          "CRC, SHA-256 and isolated render verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(package())
