# Publish to GitHub Pages

The release is entirely static. GitHub Actions downloads the pinned browser
runtime, runs lint/type/tests, creates a Pages artifact, and deploys it. The
repository stores source and lockfiles, not downloaded wheels, build output,
or course images.

## First publication

The preferred route is the publishing automation. From the project directory:

```sh
./scripts/publish.sh --dry-run
./scripts/publish.sh
```

The default target is `pu-shd/hrdiagram`. To override it, set
`HRDIAGRAM_REPOSITORY` or supply `--repository OWNER/NAME`. The shell wrapper uses
the project's `.venv` Python when available, falling back to `python3`; the
publisher uses only standard-library modules and requires Python 3.10+.

The dry run only prints its plan. Execution verifies GitHub authentication and
Git commit identity, initializes `main` if needed, checks the tracked/staged
file list, and commits the explicit source paths. It then creates the public
repository and pushes. It waits for the **Checks** workflow to pass before
enabling Pages, dispatching the deployment, waiting for its result, and checking
that the published page responds. Failed workflows display their failed-step
logs and stop publishing.

Reruns reuse an existing public target only when the local `origin` already
points to it, skip empty commits, and create a fresh Pages deployment. A failed
deployment preserves the repository and source commit for diagnosis. It never
force-pushes or overwrites another origin.

## Manual alternative

Run the following commands in your own macOS terminal, where `gh` is already
authenticated. Your account needs permission to create public repositories in
`pu-shd`, configure Pages, and run Actions.

From `/Users/bino/Downloads/frs`, optionally run the full local check first:

```sh
./scripts/test.sh
```

Initialize Git and stage the explicit source-file list. Bob's original
`HRdiagram.py` and all FITS/diagram samples are ignored and omitted:

```sh
cd /Users/bino/Downloads/frs
git init -b main
git add .github .gitignore .dockerignore compose.yaml nginx.conf Dockerfile Dockerfile.tests \
  LICENSE.md README.md docs example.env package.json package-lock.json \
  eslint.config.mjs tsconfig.json pyproject.toml requirements.lock scripts tests web
git diff --cached --stat
git diff --cached --name-only
```

Review the staged list, then commit and create the requested public repository:

```sh
git commit -m "Add static FITS color-magnitude diagram app"
gh repo create pu-shd/hrdiagram --public --source=. --remote=origin --push \
  --description "Browser-based FITS photometry and instrumental color-magnitude diagrams"
```

Enable GitHub Pages using the Actions build source, then start deployment:

```sh
gh api --method POST repos/pu-shd/hrdiagram/pages -f build_type=workflow
gh workflow run pages.yml --repo pu-shd/hrdiagram --ref main
```

If the API says Pages is already enabled, inspect its configuration with
`gh api repos/pu-shd/hrdiagram/pages`; change the source to Actions in repository
Settings → Pages if needed. Do not recreate or overwrite an existing repository
when rerunning the setup.

## Monitor and verify

List the two workflow runs initiated by the push and manual deployment:

```sh
gh run list --repo pu-shd/hrdiagram --limit 10
```

For each **Checks** and **Publish static app to GitHub Pages** run, use its ID:

```sh
gh run watch RUN_ID --repo pu-shd/hrdiagram --exit-status
```

If a run fails, inspect its failed step output before retrying:

```sh
gh run view RUN_ID --repo pu-shd/hrdiagram --log-failed
```

Once deployment succeeds:

```sh
gh api repos/pu-shd/hrdiagram/pages --jq .html_url
open https://pu-shd.github.io/hrdiagram/
```

Select the instructor's local FITS file and confirm 5,216 detections, 5,008
positive RGB measurements, and 4,906 plotted stars. Download both outputs.
Repeat in Safari on a supported Mac before classroom distribution.

## Subsequent releases

Commit and push focused changes, check the **Checks** workflow, and manually run
`pages.yml` again. Deployment is intentionally manual; a push alone does not
publish. Each deployment runs its own checks before publishing.

To roll back, revert the relevant source commit, push, and deploy the resulting
revision through the same workflow. Avoid force-pushing shared history.

## Other static hosts

Run `./scripts/build.sh`, then copy the contents of `dist/hr-diagram/` to a
dedicated site directory, preserving all subdirectories. The same directory
works under a subpath on `vanderbei.princeton.edu`.

The host must serve `.mjs`/`.js` as JavaScript and `.wasm` as
`application/wasm`, allow same-origin asset requests and workers, and permit
WebAssembly execution in any content security policy. The baseline uses an
ordinary worker, so cross-origin isolation headers are not required. Self-hosted
assets avoid cross-origin package requests. Use HTTPS for classroom hosting.

To serve the built source in a container, first prepare the runtime with the
build script, then build `Dockerfile`. The default `docker-compose` web service
instead serves the prepared `web/` directory for local preview.
