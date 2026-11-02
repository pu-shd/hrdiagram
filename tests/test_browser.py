"""Exercise the static application with real browser engines and offline analysis."""

import csv
import functools
import io
import json
import os
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest
from playwright.sync_api import sync_playwright

from test_analysis import analyze, as_fits, synthetic

ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log student filenames or HTTP request details.


@pytest.fixture(scope="module")
def static_url(tmp_path_factory):
    assert (ROOT / "web/vendor/manifest.json").exists(), "Run scripts/vendor.py first"
    site = tmp_path_factory.mktemp("static-site")
    (site / "hrdiagram").symlink_to(ROOT / "web", target_is_directory=True)
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(site))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/hrdiagram/"
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_browser_workflow_and_offline_measurements(static_url, tmp_path, engine):
    fixture = os.environ.get("SAMPLE_FITS")
    image = Path(fixture) if fixture else tmp_path / "synthetic.fit"
    if not fixture:
        image.write_bytes(as_fits(synthetic()).getvalue())
    expected = analyze(image)
    with sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch()
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        failures = []
        page.on("pageerror", lambda error: failures.append(str(error)))
        requests = []
        context.on(
            "request",
            lambda request: requests.append((request.method, request.url))
            if request.url.startswith("http")
            else None,
        )
        began = time.perf_counter()
        page.goto(static_url)
        page.wait_for_function(
            'document.querySelector("#status").textContent.startsWith("Ready.")', timeout=180_000
        )
        load_seconds = time.perf_counter() - began
        assert all(url.startswith(static_url) for _, url in requests), requests
        assert all(method == "GET" for method, _ in requests)
        # Verify the tools can process a selected local FITS file with networking disabled.
        context.set_offline(True)
        before = len(requests)
        page.locator("#image").set_input_files(image)
        page.locator("#generate").click()
        page.locator("#results").wait_for(state="visible", timeout=180_000)
        assert f"{expected['plotted']:,} stars plotted" in page.locator("#summary").inner_text()
        assert len(requests) == before, "Processing unexpectedly requested a network resource"
        with page.expect_download() as csv_download:
            page.locator("#csv-download").click()
        saved = tmp_path / f"{engine}.csv"
        csv_download.value.save_as(saved)
        rows = list(csv.DictReader(io.StringIO(saved.read_text())))
        np.testing.assert_allclose(
            [float(row["instrumental_B_minus_G"]) for row in rows],
            expected["color"],
            rtol=1e-10,
            atol=1e-10,
        )
        np.testing.assert_allclose(
            [float(row["shifted_instrumental_G"]) for row in rows],
            expected["magnitude"],
            rtol=1e-10,
            atol=1e-10,
        )
        with page.expect_download() as png_download:
            page.locator("#png-download").click()
        png_path = tmp_path / f"{engine}.png"
        png_download.value.save_as(png_path)
        assert png_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
        artifacts = ROOT / "artifacts"
        artifacts.mkdir(exist_ok=True)
        page.screenshot(path=str(artifacts / f"{engine}-result.png"), full_page=True)
        report = {
            "engine": engine,
            "sample": bool(fixture),
            "initial_load_seconds": load_seconds,
            "status": page.locator("#status").inner_text(),
            "plotted": len(rows),
            "requests_during_analysis": len(requests) - before,
            "numeric_parity": True,
        }
        (artifacts / f"{engine}-metrics.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)
        # Recover from a bad file without reloading or making network requests.
        page.locator("#image").set_input_files(
            {"name": "bad.fit", "mimeType": "application/octet-stream", "buffer": b"bad file"}
        )
        page.locator("#generate").click()
        page.locator("#error").wait_for(state="visible", timeout=30_000)
        assert "Unable to read" in page.locator("#error").inner_text()
        assert page.locator("#results").is_hidden()
        assert not failures, failures
        context.close()
        browser.close()
