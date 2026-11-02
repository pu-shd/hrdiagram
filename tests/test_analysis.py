import base64
import csv
import hashlib
import io
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "web"))
from analysis import analyze


def synthetic() -> np.ndarray:
    rng = np.random.default_rng(2026)
    data = rng.normal(100, 0.5, (3, 160, 160))
    yy, xx = np.mgrid[:160, :160]
    for i, (x, y) in enumerate(
        (
            (30, 30),
            (70, 30),
            (110, 30),
            (30, 70),
            (70, 70),
            (110, 70),
            (30, 110),
            (70, 110),
            (110, 110),
        )
    ):
        star = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 1.6**2)) * (200 + 100 * i)
        for channel, scale in enumerate((1.0, 1.2, 0.5 + i * 0.2)):
            data[channel] += star * scale
    return data


def as_fits(data: np.ndarray) -> io.BytesIO:
    output = io.BytesIO()
    fits.PrimaryHDU(data).writeto(output)
    output.seek(0)
    return output


def test_matches_original_baseline(tmp_path):
    path = tmp_path / "synthetic.fit"
    fits.PrimaryHDU(synthetic()).writeto(path)
    expected = json.loads((Path(__file__).parent / "fixtures/synthetic.json").read_text())
    actual = analyze(path)
    np.testing.assert_allclose(actual["color"], expected["color"], rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(actual["magnitude"], expected["magnitude"], rtol=1e-12, atol=1e-12)
    assert actual["detected"] == 9
    assert actual["plotted"] == 7
    assert Image.open(io.BytesIO(base64.b64decode(actual["png"]))).size == (1600, 1800)
    assert len(actual["csv"].splitlines()) == actual["plotted"] + 1


def test_csv_exports_the_plotted_fluxes_colors_and_magnitudes():
    """The added CSV adapter must preserve the scientific values in the plot."""
    result = analyze(as_fits(synthetic()))
    rows = list(csv.DictReader(io.StringIO(result["csv"])))
    assert len(rows) == result["plotted"]
    green_flux = np.array([float(row["G_flux"]) for row in rows])
    blue_flux = np.array([float(row["B_flux"]) for row in rows])
    assert all(float(row["R_flux"]) > 0 for row in rows)
    assert (green_flux > 0).all() and (blue_flux > 0).all()
    np.testing.assert_allclose(
        -2.5 * np.log10(blue_flux) + 2.5 * np.log10(green_flux),
        result["color"],
        rtol=1e-12,
        atol=1e-12,
    )
    np.testing.assert_allclose(
        [float(row["instrumental_B_minus_G"]) for row in rows], result["color"]
    )
    np.testing.assert_allclose(
        [float(row["shifted_instrumental_G"]) for row in rows], result["magnitude"]
    )
    assert {float(row["aperture_radius"]) for row in rows} <= {3, 4, 5}


@pytest.mark.parametrize(
    "data,message",
    [
        (np.zeros((3, 60, 60)), "No usable stars"),
        (np.zeros((60, 60)), "three-channel"),
        (np.zeros((3, 12, 12)), "too small"),
        (np.full((3, 60, 60), np.nan), "missing or infinite"),
        (np.full((3, 60, 60), np.inf), "missing or infinite"),
    ],
)
def test_invalid_images_have_explanations(data, message):
    with pytest.raises(ValueError, match=message):
        analyze(as_fits(data))


def test_constant_colors_are_finite():
    data = synthetic()
    data[0] = data[1]
    data[2] = data[1]
    result = analyze(as_fits(data))
    assert result["plotted"] == 9
    assert np.isfinite(result["color"]).all()
    assert result["png"]


def test_corrupt_file_has_explanation():
    with pytest.raises(ValueError, match="Unable to read"):
        analyze(io.BytesIO(b"not a FITS file"))


def test_course_image_matches_original_baseline():
    fixture = os.environ.get("SAMPLE_FITS")
    if not fixture:
        pytest.skip("Set SAMPLE_FITS to run the optional instructor-image regression")
    expected = json.loads((Path(__file__).parent / "fixtures/course-baseline.json").read_text())
    actual = analyze(Path(fixture))
    for key in ("width", "height", "detected", "positive_rgb", "plotted"):
        assert actual[key] == expected[key]
    for key in ("color", "magnitude"):
        digest = hashlib.sha256(
            ",".join(f"{value:.6f}" for value in actual[key]).encode()
        ).hexdigest()
        assert digest == expected["rounded_six_decimal_sha256"][key]


def test_large_dimensions_rejected_before_conversion(monkeypatch):
    monkeypatch.setattr("analysis.MAX_PIXELS", 100)
    with pytest.raises(ValueError, match="12 megapixels"):
        analyze(as_fits(synthetic()))


def test_no_image_has_explanation():
    output = io.BytesIO()
    fits.PrimaryHDU().writeto(output)
    output.seek(0)
    with pytest.raises(ValueError, match="no image data"):
        analyze(output)
