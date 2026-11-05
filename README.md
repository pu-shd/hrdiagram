# hrdiagram

A static astronomy teaching tool: select a color FITS image, generate an
instrumental color–magnitude diagram, and download its plot and measurements.
The analysis runs on the student's computer, inside the browser using Pyodide.
Students do not need to install Python. Hosting requires only static files.

The photometry workflow follows the course script provided by Robert J. Vanderbei.
His original `HRdiagram.py` and the supplied course FITS/PNG files are excluded
from this repository and all deployment artifacts.

## Use

Open the deployed course page, wait for the analysis tools to load, select a
linear three-channel RGB FITS image, and select **Generate diagram**. Download
the PNG plot or CSV measurements. Images are processed locally and are not
uploaded. Keep the page open to analyze additional images without a connection
after initialization. Offline reopening is not implemented in this prototype.

The axes are instrumental blue-minus-green color and shifted instrumental green
magnitude. They are not calibrated temperature or absolute magnitude. See
[the method and limitations](docs/method.md) before using the results in an assignment.

The image-size note shows the selected FITS file's size and, when its primary RGB
header can be read, its dimensions and the size of the floating-point RGB array
alone. It flags files over 250 MiB or images over 19 megapixels before processing.
Browser-reported device RAM is approximate installed memory; Safari and Firefox
do not expose that report. The page cannot determine free memory or guarantee
that an image below the limits will fit. Additional processing arrays and tools
require more memory than the RGB array shown.
The note starts collapsed; select its disclosure triangle to expand it. Selecting
an image over a known size limit opens it automatically to explain the problem.

## Build and preview

Development requires Docker and `docker-compose`; the deployed site requires
neither. From macOS with zsh:

```sh
./scripts/build.sh
./scripts/run.sh
```

Open `http://localhost:8080`. The build produces `dist/hr-diagram/` and
`dist/hr-diagram.zip`. Upload the contents of that directory to any compatible
static web host. Serve the app over HTTP(S), rather than opening `index.html`
directly from disk.

If port 8080 is occupied, choose another port:

```sh
HRDIAGRAM_PORT=8090 ./scripts/run.sh
```

The current runtime assets occupy approximately 47 MiB. All packages are served
from the same origin as the app. Python wheels are checked against the pinned
Pyodide package lock, and packaging verifies the downloaded asset manifest.
Generated dependencies and build output remain outside Git.

## Test

```sh
./scripts/test.sh
```

The containerized suite runs Python lint, formatting and type checks,
JavaScript lint and type checks, numerical regression tests, and browser
workflows in Chromium, Firefox, and WebKit. Browser tests verify that analysis
works with network access blocked after initialization and compare CSV values
with native Python. A local optional instructor-image regression is documented
in [development and validation](docs/development.md).

GitHub Actions runs the same checks on pushes and pull requests. The deployment
workflow also requires them to pass before publishing.

## Deploy to GitHub Pages

The intended repository is `pu-shd/hrdiagram`, with the site at
`https://pu-shd.github.io/hrdiagram/`. All asset URLs are relative, so a project
subdirectory works without changing the source.

Preview and run the publishing automation from an authenticated developer terminal:

```sh
./scripts/publish.sh --dry-run
./scripts/publish.sh
```

It creates the public `pu-shd/hrdiagram` repository, commits the allowed source
files, pushes, waits for Checks, enables Pages, deploys, and waits for the
deployment to succeed. The developer-side publisher uses Python 3.10+ with only
standard-library modules, plus `git` and the authenticated `gh` CLI. It does not
change the browser-only student requirements.

See [publishing details and manual commands](docs/deployment.md). The workflow builds
the static assets and publishes them through GitHub Pages; no runtime service,
database, or API credentials are required. The same build can be copied to
`vanderbei.princeton.edu`.

## License

Application code is distributed under the [MIT license](LICENSE.md). Bundled
third-party runtimes and scientific packages retain their respective licenses;
see [third-party notices](docs/third-party.md).
