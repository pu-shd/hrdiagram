# Development and validation

The source is deliberately small:

- `web/analysis.py`: validated FITS input, photometry, plotting, and CSV output.
- `web/worker.js`: Pyodide initialization and analysis in a dedicated worker.
- `web/app.js`, `index.html`, `style.css`: file selection, status, and downloads.
- `scripts/vendor.py`: pinned browser runtime and scientific dependencies.
- `scripts/package.py`: a static deployment directory and ZIP.
- `scripts/publish.py`: authenticated Git/GitHub publishing and workflow monitoring.

The original instructor script is neither a build dependency nor a test
dependency. Synthetic golden measurements and an optional course-image
baseline preserve regression coverage without publishing that script or image.

## Container checks

`./scripts/test.sh` on macOS runs all checks with `docker-compose`. On Linux,
the equivalent individual commands appear in `.github/workflows/checks.yml`.
That workflow runs on pushes and pull requests, except those changing only
Markdown, and can be started by hand.
The test image includes matching Playwright browser binaries and Python library
versions from `requirements.lock`. JavaScript tools use `package-lock.json`.

The optional instructor-image test is explicitly reported as skipped when its
fixture is absent. To enable it, copy the supplied image to the ignored path
`artifacts/course.fit`, then run:

```sh
docker-compose run --rm -T -e SAMPLE_FITS=/samples/course.fit tools \
  python -m pytest -v -s tests
```

For an image stored elsewhere, set `SAMPLE_DIRECTORY` to its containing directory
and `CONTAINER_SAMPLE_FITS` to `/samples/<filename>` before running the test
script. See `example.env`; variables can be exported in the shell.

Browser tests run against a static test server, select the FITS file through the
file picker, block network access, verify PNG/CSV downloads, and compare all CSV
color and magnitude values to native Python with absolute/relative tolerance
`1e-10`. They also check recovery after a corrupt file. Screenshots and timing
reports are written to ignored `artifacts/` paths.

Publisher tests mock Git and GitHub, including repository creation, safe reruns,
excluded files, wrong origins, failed Checks, Checks started by hand for a
Markdown-only commit, and deployment-run selection. They
create no external resources. The macOS preview launcher tests run in local zsh;
the container reports those checks as skipped when zsh is unavailable.

To check the running Nginx preview's JavaScript/WebAssembly content types:

```sh
HRDIAGRAM_PORT=8090 docker-compose up -d --wait web
docker-compose run --rm -T -e PREVIEW_URL=http://web tools \
  python -m pytest -v tests/test_static_host.py
```

## Instructor-image validation

The supplied 2750 × 2200 RGB image produced:

| Stage | Stars |
| --- | ---: |
| Detected after edge exclusion | 5,216 |
| Positive RGB fluxes | 5,008 |
| Plotted after color filtering | 4,906 |

Native extraction matched the supplied script's color and magnitude arrays to
`1e-12`. Chromium, Firefox, and WebKit reproduced the plotted values within
`1e-10`, using the actual course image, with no HTTP requests during analysis.
The baseline additionally records SHA-256 hashes of all plotted measurements
rounded to six decimal places.

The reference PNG records Matplotlib 3.7.2. The generated point cloud visually
matches it; pixel-identical PNG rendering is not a requirement across Matplotlib
and font versions. Native Python peaked near 466 MiB resident memory during an
initial diagnostic run. This is not a measurement of browser memory usage.

These are container browser-engine tests. WebKit testing is useful coverage but
does not substitute for a classroom smoke test in Safari on the supported Macs.

## Local Python

Python development uses a project-specific virtual environment:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
MPLBACKEND=Agg .venv/bin/python -m pytest -v tests/test_analysis.py
```

Use Docker for the complete reproducible browser suite. Generated runtime files,
images, environment files, caches, and build output are ignored by Git.
