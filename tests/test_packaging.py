import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "package_app", Path(__file__).resolve().parents[1] / "scripts/package.py"
)
assert spec is not None and spec.loader is not None
package_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package_app)


def staged_source(tmp_path, monkeypatch):
    monkeypatch.setattr(package_app, "ROOT", tmp_path)
    web = tmp_path / "web"
    vendor = web / "vendor"
    vendor.mkdir(parents=True)
    for name in ("index.html", "style.css", "app.js", "worker.js", "analysis.py", ".nojekyll"):
        (web / name).write_text("test")
    (vendor / "runtime.wasm").write_bytes(b"test runtime")
    (vendor / "manifest.json").write_text(
        json.dumps({"files": {"runtime.wasm": hashlib.sha256(b"test runtime").hexdigest()}})
    )
    (tmp_path / "LICENSE.md").write_text("MIT")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/third-party.md").write_text("notices")
    for name in ("HRdiagram.py", "course.fit", ".env", "private_HR.png"):
        (web / name).write_text("must not ship")
    return web


def test_release_excludes_instructor_source_images_and_configuration(tmp_path, monkeypatch):
    staged_source(tmp_path, monkeypatch)
    package_app.main()
    with zipfile.ZipFile(tmp_path / "dist/hr-diagram.zip") as archive:
        names = archive.namelist()
    assert "hr-diagram/index.html" in names
    assert "hr-diagram/vendor/runtime.wasm" in names
    assert "hr-diagram/LICENSE.md" in names
    assert "hr-diagram/THIRD_PARTY.md" in names
    assert not any(
        "HRdiagram.py" in name or name.endswith((".fit", ".png", ".env")) for name in names
    )


def test_release_fails_on_modified_runtime(tmp_path, monkeypatch):
    web = staged_source(tmp_path, monkeypatch)
    (web / "vendor/runtime.wasm").write_bytes(b"tampered runtime")
    with pytest.raises(SystemExit, match="integrity check failed"):
        package_app.main()
