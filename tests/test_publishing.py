"""Model Git/GitHub operations without creating repositories or deployments."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "publish_app", Path(__file__).resolve().parents[1] / "scripts/publish.py"
)
assert spec is not None and spec.loader is not None
publish_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish_app)


class GitHubModel:
    def __init__(
        self,
        root,
        existing=False,
        fail_checks=False,
        unsafe=False,
        wrong_origin=False,
        docs_only=False,
    ):
        self.root = root
        self.existing = existing
        self.fail_checks = fail_checks
        self.unsafe = unsafe
        self.wrong_origin = wrong_origin
        self.commands = []
        self.dispatched = False
        self.docs_only = docs_only  # HEAD changes only Markdown: Checks don't run on its push
        self.checks_dispatched = False
        self.pages = False
        self.sha = "a" * 40

    def run(self, args, **kwargs):
        args = tuple(args)
        self.commands.append(args)
        code, out, err = 0, "", ""
        if args[:2] == ("git", "config"):
            out = "configured\n"
        elif args == ("git", "rev-parse", "--show-toplevel"):
            code, out = (0, str(self.root)) if self.existing else (1, "")
        elif args == ("git", "branch", "--show-current"):
            out = "main\n"
        elif args == ("git", "remote", "get-url", "origin"):
            if self.wrong_origin:
                out = "git@github.com:other/project.git\n"
            elif self.existing:
                out = "git@github.com:pu-shd/hrdiagram.git\n"
            else:
                code = 2
        elif args[:3] == ("gh", "api", "repos/pu-shd/hrdiagram"):
            if self.existing:
                out = json.dumps({"private": False})
            else:
                code, err = 1, "gh: Not Found (HTTP 404)"
        elif args == ("git", "ls-files", "-z"):
            out = "web/analysis.py\0README.md\0"
            if self.unsafe:
                out += "HRdiagram.py\0"
        elif args == ("git", "diff", "--cached", "--quiet"):
            code = 0 if self.existing else 1
        elif args == ("git", "rev-parse", "HEAD"):
            out = self.sha
        elif args[:3] == ("gh", "run", "list"):
            workflow = args[args.index("--workflow") + 1]
            event = args[args.index("--event") + 1]
            if workflow == "checks.yml" and self.docs_only:
                manual = event == "workflow_dispatch" and self.checks_dispatched
                out = json.dumps([{"databaseId": 101}] if manual else [])
                return subprocess.CompletedProcess(args, code, out, err)
            out = json.dumps(
                [{"databaseId": 100}]
                if workflow == "checks.yml"
                else [{"databaseId": 200}, {"databaseId": 199}]
                if self.dispatched
                else [{"databaseId": 199}]
            )
        elif args[:4] == ("gh", "run", "watch", "100") and self.fail_checks:
            code = 1
        elif args[:4] == ("gh", "workflow", "run", "pages.yml"):
            self.dispatched = True
        elif args[:4] == ("gh", "workflow", "run", "checks.yml"):
            self.checks_dispatched = True
        elif args == ("gh", "api", "repos/pu-shd/hrdiagram/pages"):
            if self.pages:
                out = json.dumps(
                    {"build_type": "workflow", "html_url": "https://pu-shd.github.io/hrdiagram/"}
                )
            else:
                code, err = 1, "gh: Not Found (HTTP 404)"
        elif args[:4] == ("gh", "api", "--method", "POST"):
            self.pages = True
        return subprocess.CompletedProcess(args, code, out, err)


def setup_publisher(tmp_path, monkeypatch, **options):
    model = GitHubModel(tmp_path, **options)
    monkeypatch.setattr(publish_app.subprocess, "run", model.run)
    verified = []
    monkeypatch.setattr(
        publish_app.Publisher, "verify_site", lambda self, url: verified.append(url)
    )
    return publish_app.Publisher(tmp_path, "pu-shd/hrdiagram"), model, verified


def test_creates_public_repo_and_waits_for_checks_before_deploying(tmp_path, monkeypatch):
    publisher, model, verified = setup_publisher(tmp_path, monkeypatch)
    publisher.publish()
    commands = model.commands
    create = next(command for command in commands if command[:3] == ("gh", "repo", "create"))
    assert create[3] == "pu-shd/hrdiagram"
    assert "--public" in create
    stage = next(command for command in commands if command[:2] == ("git", "add"))
    assert "HRdiagram.py" not in stage
    assert "docs" in stage and "LICENSE.md" in stage and "README.md" in stage
    checks = next(command for command in commands if command[:4] == ("gh", "run", "watch", "100"))
    dispatch = next(command for command in commands if command[:3] == ("gh", "workflow", "run"))
    deployment = next(
        command for command in commands if command[:4] == ("gh", "run", "watch", "200")
    )
    assert commands.index(checks) < commands.index(dispatch) < commands.index(deployment)
    assert verified == ["https://pu-shd.github.io/hrdiagram/"]


def test_starts_checks_by_hand_when_the_push_only_changed_markdown(tmp_path, monkeypatch):
    """checks.yml ignores Markdown-only pushes; publishing must still check before deploying."""
    clock = [0.0]
    monkeypatch.setattr(publish_app.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        publish_app.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )
    publisher, model, verified = setup_publisher(
        tmp_path, monkeypatch, existing=True, docs_only=True
    )
    publisher.publish()
    commands = model.commands
    start = commands.index(
        ("gh", "workflow", "run", "checks.yml", "--repo", "pu-shd/hrdiagram", "--ref", "main")
    )
    checks = next(command for command in commands if command[:4] == ("gh", "run", "watch", "101"))
    deploy = next(
        command for command in commands if command[:4] == ("gh", "workflow", "run", "pages.yml")
    )
    assert start < commands.index(checks) < commands.index(deploy)
    assert clock[0] < 120  # gave up waiting for a push run well before the old two minutes
    assert verified


def test_failed_checks_stop_deployment_and_show_logs(tmp_path, monkeypatch):
    publisher, model, verified = setup_publisher(tmp_path, monkeypatch, fail_checks=True)
    with pytest.raises(publish_app.PublishError, match="Workflow 100 failed"):
        publisher.publish()
    assert not model.dispatched
    assert not verified
    assert any(command[:3] == ("gh", "run", "view") for command in model.commands)


def test_rerun_reuses_matching_repo_and_skips_empty_commit(tmp_path, monkeypatch):
    publisher, model, verified = setup_publisher(tmp_path, monkeypatch, existing=True)
    publisher.publish()
    assert not any(command[:3] == ("gh", "repo", "create") for command in model.commands)
    assert not any(command[:2] == ("git", "commit") for command in model.commands)
    assert verified


@pytest.mark.parametrize("options", [{"unsafe": True}, {"wrong_origin": True}])
def test_refuses_excluded_files_or_unrelated_origin(tmp_path, monkeypatch, options):
    publisher, model, _ = setup_publisher(tmp_path, monkeypatch, **options)
    with pytest.raises(publish_app.PublishError):
        publisher.publish()
    assert not any(command[:3] == ("gh", "repo", "create") for command in model.commands)
    assert not any(command[:2] == ("git", "push") for command in model.commands)


@pytest.mark.parametrize(
    "name",
    ["web/vendor/file.whl", "docs/.env", "tests/sample.fits", "CLAUDE.md", "docs/private.pem"],
)
def test_rejects_force_added_excluded_paths(name):
    with pytest.raises(publish_app.PublishError, match="Excluded file"):
        publish_app.validate_sources([name])


def test_dry_run_performs_no_git_or_network_calls(monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("Dry run must not call external commands")

    monkeypatch.setattr(publish_app.subprocess, "run", forbidden)
    publish_app.dry_run("pu-shd/hrdiagram")
    output = capsys.readouterr().out
    assert "DRY RUN" in output
    assert "gh repo create pu-shd/hrdiagram --public" in output
    assert "--exit-status" in output


def test_invalid_repository_is_rejected():
    with pytest.raises(publish_app.PublishError, match="OWNER/NAME"):
        publish_app.validate_repository("pu-shd/hrdiagram;echo secret")
