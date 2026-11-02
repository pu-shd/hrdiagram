"""Build a static upload directory and ZIP; never include course images."""

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    source = ROOT / "web"
    manifest_path = source / "vendor/manifest.json"
    if not manifest_path.exists():
        raise SystemExit("Missing browser runtime. Run scripts/vendor.py first.")
    manifest = json.loads(manifest_path.read_text())
    for name, expected in manifest["files"].items():
        if hashlib.sha256((source / "vendor" / name).read_bytes()).hexdigest() != expected:
            raise SystemExit(f"Runtime integrity check failed: {name}")
    destination = ROOT / "dist" / "hr-diagram"
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    for name in ("index.html", "style.css", "app.js", "worker.js", "analysis.py", ".nojekyll"):
        shutil.copy2(source / name, destination / name)
    shutil.copytree(source / "vendor", destination / "vendor")
    shutil.copy2(ROOT / "LICENSE.md", destination / "LICENSE.md")
    shutil.copy2(ROOT / "docs/third-party.md", destination / "THIRD_PARTY.md")
    archive = ROOT / "dist" / "hr-diagram.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for file in sorted(destination.rglob("*")):
            if file.is_file():
                output.write(file, file.relative_to(destination.parent))
    print(f"Static directory: {destination}")
    print(f"Upload ZIP: {archive} ({archive.stat().st_size / 1024**2:.1f} MiB)")


if __name__ == "__main__":
    main()
