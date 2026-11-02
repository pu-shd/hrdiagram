"""Optional integration checks for the containerized static preview."""

import os
import urllib.request

import pytest
from playwright.sync_api import sync_playwright

BASE = os.environ.get("PREVIEW_URL")
pytestmark = pytest.mark.skipif(not BASE, reason="Set PREVIEW_URL to a running static preview")


@pytest.mark.parametrize(
    "path,mime",
    [
        ("worker.js", "javascript"),
        ("vendor/pyodide.mjs", "javascript"),
        ("vendor/pyodide.asm.wasm", "application/wasm"),
    ],
)
def test_static_host_serves_executable_asset_types(path, mime):
    request = urllib.request.Request(f"{BASE}/{path}", method="HEAD")
    with urllib.request.urlopen(request, timeout=10) as response:
        assert response.status == 200
        assert mime in response.headers["Content-Type"]


def test_browser_loads_the_static_preview_runtime():
    assert BASE is not None
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(BASE)
        page.wait_for_function(
            'document.querySelector("#status").textContent.startsWith("Ready.")',
            timeout=120_000,
        )
        assert page.locator("#error").is_hidden()
        browser.close()
