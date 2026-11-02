"""Create the public source repository and publish the checked static app."""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = (
    ".github",
    ".gitignore",
    ".dockerignore",
    "compose.yaml",
    "nginx.conf",
    "Dockerfile",
    "Dockerfile.tests",
    "LICENSE.md",
    "README.md",
    "docs",
    "example.env",
    "package.json",
    "package-lock.json",
    "eslint.config.mjs",
    "tsconfig.json",
    "pyproject.toml",
    "requirements.lock",
    "scripts",
    "tests",
    "web",
)


class PublishError(RuntimeError):
    pass


def validate_repository(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise PublishError("Repository must be an OWNER/NAME pair.")
    return value


def validate_sources(names: list[str]) -> None:
    """Reject excluded data even if it was previously force-added to Git."""
    for name in names:
        path = Path(name)
        parts = {part.lower() for part in path.parts}
        basename = path.name.lower()
        if (
            path.parts[0] not in SOURCE_PATHS
            or parts.intersection(
                {"node_modules", "__pycache__", ".claude", ".aws", ".ssh", "vendor"}
            )
            or any(part.startswith(".env") for part in parts)
            or basename in {"hrdiagram.py", "claude.md", "core", ".ds_store"}
            or basename.endswith(
                (
                    ".fit",
                    ".fits",
                    ".fts",
                    "_hr.png",
                    ".db",
                    ".dump",
                    ".dmp",
                    ".core",
                    ".pyc",
                    ".pem",
                    ".key",
                    ".p12",
                    ".pfx",
                    ".sqlite",
                    ".sqlite3",
                )
            )
        ):
            raise PublishError(
                f"Excluded file is tracked/staged: {name}. Remove it before publishing."
            )


class Publisher:
    def __init__(self, root: Path, repository: str):
        self.root = root
        self.repository = validate_repository(repository)

    def command(
        self, *args: str, check: bool = True, quiet: bool = False
    ) -> subprocess.CompletedProcess:
        print("$ " + shlex.join(args), flush=True)
        result = subprocess.run(args, cwd=self.root, text=True, capture_output=True)
        if not quiet:
            if result.stdout:
                print(result.stdout, end="", flush=True)
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr, flush=True)
        if check and result.returncode:
            raise PublishError(f"Command failed ({result.returncode}): {shlex.join(args)}")
        return result

    def api(self, path: str) -> dict[str, Any] | None:
        result = self.command("gh", "api", path, check=False, quiet=True)
        if result.returncode == 0:
            return json.loads(result.stdout)
        if "HTTP 404" in result.stderr:
            return None
        raise PublishError(
            f"GitHub API request failed: {path}. Check connectivity and permissions."
        )

    def run_ids(self, workflow: str, sha: str) -> list[int]:
        result = self.command(
            "gh",
            "run",
            "list",
            "--repo",
            self.repository,
            "--workflow",
            workflow,
            "--commit",
            sha,
            "--branch",
            "main",
            "--event",
            "push" if workflow == "checks.yml" else "workflow_dispatch",
            "--limit",
            "30",
            "--json",
            "databaseId",
            quiet=True,
            check=False,
        )
        if result.returncode:
            if (
                "HTTP 404" in result.stderr
                or "could not find any workflows" in result.stderr.lower()
            ):
                return []  # GitHub may still be registering the first pushed workflow.
            raise PublishError(f"Could not list {workflow} runs; check GitHub Actions permissions.")
        return [int(run["databaseId"]) for run in json.loads(result.stdout)]

    def await_run(self, workflow: str, sha: str, exclude: set[int] | None = None) -> int:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            runs = [run for run in self.run_ids(workflow, sha) if run not in (exclude or set())]
            if runs:
                return runs[0]
            time.sleep(3)
        raise PublishError(f"No {workflow} run appeared. Check repository Actions settings.")

    def watch(self, run_id: int) -> None:
        result = self.command(
            "gh",
            "run",
            "watch",
            str(run_id),
            "--repo",
            self.repository,
            "--exit-status",
            "--interval",
            "5",
            check=False,
        )
        if result.returncode:
            self.command(
                "gh",
                "run",
                "view",
                str(run_id),
                "--repo",
                self.repository,
                "--log-failed",
                check=False,
            )
            raise PublishError(f"Workflow {run_id} failed; publishing stopped.")

    def verify_site(self, url: str) -> None:
        for attempt in range(12):
            try:
                with urllib.request.urlopen(url, timeout=20) as response:
                    if response.status == 200 and b'id="generate"' in response.read():
                        print(f"PASS: site responds at {url}", flush=True)
                        return
            except (urllib.error.URLError, TimeoutError):
                pass
            if attempt < 11:
                time.sleep(5)
        raise PublishError(f"Deployment completed, but the site could not yet be verified: {url}")

    def publish(self) -> None:
        self.command("gh", "auth", "status", quiet=True)
        for key in ("user.name", "user.email"):
            if not self.command("git", "config", key, check=False, quiet=True).stdout.strip():
                raise PublishError(f"Configure git {key} before publishing.")
        local = self.command("git", "rev-parse", "--show-toplevel", check=False, quiet=True)
        if local.returncode:
            self.command("git", "init", "-b", "main")
        elif Path(local.stdout.strip()).resolve() != self.root.resolve():
            raise PublishError(
                "The project is inside another Git repository; refusing to publish it."
            )
        branch = self.command("git", "branch", "--show-current", quiet=True).stdout.strip()
        if branch != "main":
            raise PublishError("Publish from the main branch; the script will not switch branches.")
        origin = self.command("git", "remote", "get-url", "origin", check=False, quiet=True)
        expected = {
            f"git@github.com:{self.repository}".lower(),
            f"https://github.com/{self.repository}".lower(),
            f"ssh://git@github.com/{self.repository}".lower(),
        }
        if (
            origin.returncode == 0
            and origin.stdout.strip().removesuffix(".git").lower() not in expected
        ):
            raise PublishError("The existing origin points to another repository.")
        remote = self.api(f"repos/{self.repository}")
        if remote is not None and (remote["private"] or origin.returncode != 0):
            raise PublishError(
                "Target already exists; reruns require its public repository as origin."
            )
        # Check the current index before adding files, then check the final index again.
        tracked = self.command("git", "ls-files", "-z", quiet=True).stdout
        validate_sources([name for name in tracked.split("\0") if name])
        self.command("git", "add", "--", *SOURCE_PATHS)
        staged = self.command("git", "ls-files", "-z", quiet=True).stdout
        validate_sources([name for name in staged.split("\0") if name])
        changes = self.command("git", "diff", "--cached", "--quiet", check=False, quiet=True)
        if changes.returncode == 1:
            self.command("git", "commit", "-m", "Add static FITS color-magnitude diagram app")
        elif changes.returncode != 0:
            raise PublishError("Unable to inspect staged changes.")
        if remote is None:
            creation = ["gh", "repo", "create", self.repository, "--public", "--source=."]
            if origin.returncode != 0:
                creation.append("--remote=origin")
            self.command(*creation)
        self.command("git", "push", "--set-upstream", "origin", "main")
        sha = self.command("git", "rev-parse", "HEAD", quiet=True).stdout.strip()
        self.watch(self.await_run("checks.yml", sha))
        pages_path = f"repos/{self.repository}/pages"
        pages = self.api(pages_path)
        if pages is None or pages.get("build_type") != "workflow":
            self.command(
                "gh",
                "api",
                "--method",
                "POST" if pages is None else "PUT",
                pages_path,
                "-f",
                "build_type=workflow",
                quiet=True,
            )
        previous = set(self.run_ids("pages.yml", sha))
        self.command(
            "gh", "workflow", "run", "pages.yml", "--repo", self.repository, "--ref", "main"
        )
        self.watch(self.await_run("pages.yml", sha, previous))
        final = self.api(pages_path)
        if not final or not final.get("html_url"):
            raise PublishError("Deployment finished but GitHub did not report a Pages URL.")
        self.verify_site(final["html_url"])
        print(f"Published source: https://github.com/{self.repository}")
        print(f"Published app: {final['html_url']}")


def dry_run(repository: str) -> None:
    repository = validate_repository(repository)
    print("DRY RUN: no files, Git state, or GitHub resources will change.")
    commands = [
        ["git", "init", "-b", "main"],
        ["git", "add", "--", *SOURCE_PATHS],
        ["git", "commit", "-m", "Add static FITS color-magnitude diagram app"],
        ["gh", "repo", "create", repository, "--public", "--source=.", "--remote=origin"],
        ["git", "push", "--set-upstream", "origin", "main"],
        ["gh", "run", "watch", "CHECKS_RUN_ID", "--repo", repository, "--exit-status"],
        ["gh", "api", "--method", "POST", f"repos/{repository}/pages", "-f", "build_type=workflow"],
        ["gh", "workflow", "run", "pages.yml", "--repo", repository, "--ref", "main"],
        ["gh", "run", "watch", "PAGES_RUN_ID", "--repo", repository, "--exit-status"],
    ]
    for command in commands:
        print("$ " + shlex.join(command))
    print("Existing matching public repositories are reused; unrelated origins are rejected.")
    print("Tracked and staged paths are checked; original script and course images are excluded.")
    print("Both workflows must pass, then the live Pages URL is verified.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the plan without changing anything"
    )
    parser.add_argument(
        "--repository", default=os.environ.get("HRDIAGRAM_REPOSITORY", "pu-shd/hrdiagram")
    )
    args = parser.parse_args()
    try:
        if args.dry_run:
            dry_run(args.repository)
        else:
            for executable in ("git", "gh"):
                if shutil.which(executable) is None:
                    raise PublishError(f"Required command is missing: {executable}")
            Publisher(ROOT, args.repository).publish()
    except (PublishError, KeyboardInterrupt) as error:
        print(f"STOPPED: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
