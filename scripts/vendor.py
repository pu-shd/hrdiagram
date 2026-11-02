"""Download a pinned, self-hosted Pyodide distribution and required wheels."""

import hashlib
import json
import urllib.request
from pathlib import Path

VERSION = "0.29.3"
BASE = f"https://cdn.jsdelivr.net/pyodide/v{VERSION}/full/"
DEST = Path(__file__).resolve().parents[1] / "web" / "vendor"
CORE = (
    "pyodide.mjs",
    "pyodide.js",
    "pyodide.asm.js",
    "pyodide.asm.wasm",
    "python_stdlib.zip",
    "pyodide-lock.json",
)


def download(name: str, expected: str | None = None, url: str | None = None) -> None:
    target = DEST / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        with urllib.request.urlopen(url or BASE + name, timeout=120) as response:
            content = response.read()
        temporary = target.with_suffix(target.suffix + ".partial")
        temporary.write_bytes(content)
        temporary.replace(target)
    if expected and hashlib.sha256(target.read_bytes()).hexdigest() != expected:
        target.unlink()
        raise RuntimeError(f"Checksum failed for {name}; run preparation again.")
    print(f"Verified {name}", flush=True)


def main() -> None:
    for filename in CORE:
        download(filename)
    packages = json.loads((DEST / "pyodide-lock.json").read_text())["packages"]
    visited: set[str] = set()

    def package(name: str) -> None:
        name = name.lower().replace("_", "-")
        if name in visited:
            return
        visited.add(name)
        entry = packages[name]
        for dependency in entry["depends"]:
            package(dependency)
        download(entry["file_name"], entry["sha256"])

    for name in ("numpy", "scipy", "matplotlib", "astropy"):
        package(name)
    download(
        "LICENSE-pyodide.txt",
        url=f"https://raw.githubusercontent.com/pyodide/pyodide/{VERSION}/LICENSE",
    )
    download(
        "LICENSE-python.txt",
        url="https://raw.githubusercontent.com/python/cpython/v3.13.2/LICENSE",
    )
    manifest = {
        "pyodide": VERSION,
        "files": {
            p.relative_to(DEST).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(DEST.rglob("*"))
            if p.is_file() and p.name != "manifest.json"
        },
    }
    (DEST / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Ready: {len(manifest['files'])} runtime files, {len(visited)} packages.")


if __name__ == "__main__":
    main()
