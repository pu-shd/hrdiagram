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
from astropy.io import fits

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


@pytest.mark.parametrize("reported_memory", [8, None])
def test_image_resources_show_file_dimensions_and_honest_memory_report(static_url, reported_memory):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(locale="en-US")
        context.add_init_script(
            "Object.defineProperty(navigator, 'deviceMemory', {get: () => "
            + json.dumps(reported_memory)
            + "});"
        )
        context.route(
            "**/worker.js*",
            lambda route: route.fulfill(
                content_type="application/javascript", body="self.postMessage({type:'ready'});"
            ),
        )
        page = context.new_page()
        page.goto(static_url)
        assert page.locator("#image-resources").count() == 1
        page.locator("#image").set_input_files(
            {
                "name": "example.fit",
                "mimeType": "application/octet-stream",
                "buffer": as_fits(synthetic()).getvalue(),
            }
        )
        page.wait_for_function(
            'document.querySelector("#image-resources").textContent.includes("160 × 160")'
        )
        assert page.locator("#image-resources").is_hidden()
        page.locator("#resource-heading").click()
        note = page.locator("#image-resources").inner_text()
        assert "0.03 megapixels" in note
        assert "RGB array alone: 0.6 MiB" in note
        memory = page.locator("#browser-memory").inner_text()
        assert ("about 8 GiB" if reported_memory else "not reported by this browser") in memory
        assert "available memory" in page.locator("#resource-note").inner_text()
        page.locator("#image").set_input_files([])
        assert "Choose an image" in page.locator("#image-resources").inner_text()
        browser.close()


@pytest.mark.parametrize("engine", ["chromium", "firefox", "webkit"])
def test_resource_note_starts_collapsed_and_supports_keyboard_disclosure(static_url, engine):
    with sync_playwright() as playwright:
        browser = getattr(playwright, engine).launch()
        context = browser.new_context()
        context.route(
            "**/worker.js*",
            lambda route: route.fulfill(
                content_type="application/javascript", body="self.postMessage({type:'ready'});"
            ),
        )
        page = context.new_page()
        page.goto(static_url)
        note = page.locator("#resource-note")
        assert note.evaluate("element => element.tagName") == "DETAILS"
        assert note.get_attribute("open") is None
        assert page.locator("#image-resources").is_hidden()
        summary = note.locator("summary")
        assert summary.is_visible()
        assert summary.inner_text() == "Image size and browser memory"
        summary.focus()
        summary.press("Enter")
        assert page.locator("#image-resources").is_visible()
        summary.press("Enter")
        assert page.locator("#image-resources").is_hidden()
        browser.close()


def test_image_over_pixel_limit_is_explained_before_processing(static_url):
    header = fits.Header()
    for key, value in (
        ("SIMPLE", True),
        ("BITPIX", -32),
        ("NAXIS", 3),
        ("NAXIS1", 5000),
        ("NAXIS2", 3801),
        ("NAXIS3", 3),
    ):
        header[key] = value
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(locale="en-US")
        context.route(
            "**/worker.js*",
            lambda route: route.fulfill(
                content_type="application/javascript", body="self.postMessage({type:'ready'});"
            ),
        )
        page = context.new_page()
        page.goto(static_url)
        assert page.locator("#image-resources").count() == 1
        page.locator("#image").set_input_files(
            {
                "name": "large.fit",
                "mimeType": "application/octet-stream",
                "buffer": header.tostring().encode("ascii"),
            }
        )
        page.wait_for_function(
            'document.querySelector("#image-resources").textContent.includes("Exceeds")'
        )
        assert "19-megapixel limit" in page.locator("#image-resources").inner_text()
        assert page.locator("#resource-note").get_attribute("open") is not None
        assert page.locator("#generate").is_disabled()
        browser.close()


def test_images_at_limits_are_accepted_before_processing(static_url, tmp_path):
    header = fits.Header()
    for key, value in (
        ("SIMPLE", True),
        ("BITPIX", -32),
        ("NAXIS", 3),
        ("NAXIS1", 5000),
        ("NAXIS2", 3800),
        ("NAXIS3", 3),
    ):
        header[key] = value
    at_pixel_limit = tmp_path / "at-pixel-limit.fit"
    at_pixel_limit.write_bytes(header.tostring().encode("ascii"))
    at_file_limit = tmp_path / "at-file-limit.fit"
    with at_file_limit.open("wb") as output:
        output.truncate(250 * 1024**2)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(locale="en-US")
        context.route(
            "**/worker.js*",
            lambda route: route.fulfill(
                content_type="application/javascript", body="self.postMessage({type:'ready'});"
            ),
        )
        page = context.new_page()
        page.goto(static_url)
        page.locator("#image").set_input_files(at_pixel_limit)
        page.wait_for_function(
            'document.querySelector("#image-resources").textContent.includes("19 megapixels")'
        )
        note = page.locator("#image-resources").text_content() or ""
        assert "5,000 × 3,800 pixels (19 megapixels)" in note
        assert "Exceeds" not in note
        assert page.locator("#generate").is_enabled()
        page.locator("#image").set_input_files(at_file_limit)
        page.wait_for_function(
            'document.querySelector("#image-resources").textContent.includes("checked during")'
        )
        assert "250 MiB file" in (page.locator("#image-resources").text_content() or "")
        assert page.locator("#generate").is_enabled()
        browser.close()


def test_image_over_file_limit_is_rejected_without_reading_image_data(static_url, tmp_path):
    image = tmp_path / "large.fit"
    with image.open("wb") as output:
        output.truncate(251 * 1024**2)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context()
        context.route(
            "**/worker.js*",
            lambda route: route.fulfill(
                content_type="application/javascript", body="self.postMessage({type:'ready'});"
            ),
        )
        context.add_init_script(
            "Blob.prototype.arrayBuffer = () => { throw new Error('File must not be read'); };"
        )
        page = context.new_page()
        failures = []
        page.on("pageerror", lambda error: failures.append(str(error)))
        page.goto(static_url)
        page.locator("#image").set_input_files(image)
        assert "250-MiB file limit" in page.locator("#image-resources").inner_text()
        assert page.locator("#resource-note").get_attribute("open") is not None
        assert page.locator("#generate").is_disabled()
        assert not failures
        browser.close()


def test_header_has_no_lab_prototype_label(static_url):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context()
        context.route(
            "**/worker.js*",
            lambda route: route.fulfill(
                content_type="application/javascript", body="self.postMessage({type:'ready'});"
            ),
        )
        page = context.new_page()
        page.goto(static_url)
        header = page.locator("main > header").inner_text()
        assert "Find the pattern in the stars." in header
        assert "prototype" not in header.lower()
        assert "astronomy lab" not in header.lower()
        assert page.locator(".eyebrow").count() == 0
        browser.close()
