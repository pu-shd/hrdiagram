"""Browser adaptation of the HRdiagram.py supplied by Robert J. Vanderbei.

For readers comparing this file with the supplied classroom script:

* The photometry follows the same method and defaults: RGB-mean detection,
  median/MAD background, Gaussian smoothing, local maxima, brightness-dependent
  apertures, local sky subtraction, positive RGB fluxes, instrumental B-G/G
  magnitudes, the brightest-star shift to 10, and percentile color filtering.
* The top-level command-line program is now analyze(source), a callable function.
  The browser worker loads this code and calls it with the selected FITS file.
  Short names such as R, G, B, L, and Ls have been expanded for readability.
  The original star_flux helper is expressed as the per-channel loop below.
* Added input checks turn unsupported or unusable images into readable errors.
  Browser resource limits and a constant-color rendering guard are additions.
* File saving and plt.show() are replaced by an in-memory PNG, CSV measurements,
  and a returned dictionary. The browser displays/downloads these results.

The supplied M13 image was checked against the original script: 5,216 detections,
5,008 positive RGB measurements, and 4,906 plotted stars, with matching plotted
color/magnitude values. Regression coverage is in tests/test_analysis.py.
"""

import base64
import csv
import io
import json
from typing import Any

import matplotlib

# Browser adaptation: Agg renders into an image buffer without opening a desktop
# plotting window. It must be selected before importing pyplot.
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from astropy.io import fits
from scipy.ndimage import gaussian_filter, maximum_filter

# Added browser guardrails, separate from the inherited photometry settings.
MAX_FILE_BYTES = 250 * 1024 * 1024
MAX_PIXELS = 19_000_000


def analyze(source: Any) -> dict[str, Any]:
    """Analyze a FITS path or binary file-like object and return browser-ready data.

    The returned dictionary contains the plotted color/magnitude arrays, a PNG
    encoded as base64 text, CSV text, and counts at each selection stage. These
    values can cross the browser worker's message boundary. Invalid inputs raise
    ValueError so the interface can explain why analysis could not complete.
    """
    # Added validation: select an image HDU explicitly and check its dimensions
    # before allocating the floating-point RGB array. Memory mapping is disabled
    # because the browser uses an in-memory filesystem. Float conversion matches
    # the supplied script's fits.getdata(...).astype(float).
    try:
        with fits.open(source, memmap=False) as hdus:
            image = next(
                (hdu for hdu in hdus if hdu.is_image and hdu.header.get("NAXIS", 0) > 0), None
            )
            if image is None:
                raise ValueError("The FITS file contains no image data.")
            if len(image.shape) != 3 or image.shape[0] != 3:
                raise ValueError("Choose a three-channel RGB FITS image (3 × height × width).")
            _, height, width = image.shape
            if min(height, width) < 27:
                raise ValueError("The image is too small for the background annulus.")
            if height * width > MAX_PIXELS:
                raise ValueError("This browser prototype supports images up to 19 megapixels.")
            data = image.data.astype(float)
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(
            "Unable to read this FITS image. Check its format and completeness."
        ) from error
    if not np.isfinite(data).all():
        raise ValueError("The image contains missing or infinite pixel values.")

    # Original detection method: RGB mean, robust global background/noise, and a
    # threshold five noise sigmas above the background. As in the supplied script,
    # the threshold is estimated BEFORE smoothing the detection image.
    red, green, blue = data
    luminance = (red + green + blue) / 3.0
    background = np.median(luminance)
    sigma = 1.4826 * np.median(np.abs(luminance - background))
    threshold = background + 5.0 * sigma
    # Original defaults: Gaussian sigma 1 pixel, a 7-pixel maximum-filter window,
    # and the same strict 12-pixel edge exclusion around candidate star centers.
    smoothed = gaussian_filter(luminance, 1.0)
    maxima = smoothed == maximum_filter(smoothed, size=7)
    y, x = np.where(maxima & (smoothed > threshold))
    border = (x > 12) & (x < width - 12) & (y > 12) & (y < height - 12)
    x, y = x[border], y[border]
    detected = len(x)
    # Added error handling: the original percentile operations cannot operate on
    # an empty detection list. Report that condition before reaching them.
    if detected == 0:
        raise ValueError("No usable stars were detected. Try a different linear RGB FITS image.")
    # Original aperture rules: the 70th/95th brightness percentiles select radii
    # 3, 4, and 5 pixels. The sky annulus still spans radii 7 through 10 pixels.
    peaks = smoothed[y, x] - background
    p70, p95 = np.percentile(peaks, [70, 95])
    yy, xx = np.mgrid[-10:11, -10:11]
    distance = np.sqrt(xx**2 + yy**2)
    annulus = (distance >= 7) & (distance <= 10)
    # Adaptation: collect x, y, radius, R_flux, G_flux, B_flux in one row per star
    # instead of parallel lists. Keeping them together also supports CSV export.
    rows = []
    for sx, sy, peak in zip(x, y, peaks, strict=True):
        radius = 3 if peak < p70 else 4 if peak < p95 else 5
        aperture = distance <= radius
        fluxes = []
        # This is the original star_flux calculation, applied to each channel:
        # sum the aperture pixels after subtracting the median annulus sky.
        for channel in (red, green, blue):
            box = channel[sy - 10 : sy + 11, sx - 10 : sx + 11]
            sky = np.median(box[annulus])
            fluxes.append(float(np.sum(box[aperture] - sky)))
        # Retain the original requirement for positive measured flux in ALL
        # three channels, including red even though the plot uses blue and green.
        if all(flux > 0 for flux in fluxes):
            rows.append([float(sx), float(sy), float(radius), *fluxes])
    # Added sparse-image guard: percentile color cuts can otherwise leave too few
    # measurements for the subsequent plotting operations.
    if len(rows) < 3:
        raise ValueError("Fewer than three stars have positive measurements in all RGB channels.")
    measurements = np.asarray(rows)
    # Original magnitude/color formulas. Computing Bmag inline avoids a temporary
    # array; Rmag is omitted because it was unused. The measured red flux remains
    # available in the CSV. These are camera RGB channels, not Gaia passbands.
    rflux, gflux, bflux = measurements[:, 3:].T
    gmag = -2.5 * np.log10(gflux)
    color = -2.5 * np.log10(bflux) - gmag
    # Original arbitrary zero-point shift: assign the brightest measured star 10
    # BEFORE clipping colors. This does not calibrate an apparent/absolute
    # magnitude, and the brightest star could subsequently be clipped.
    gmag = gmag - np.min(gmag) + 10
    q1, q99 = np.percentile(color, [1, 99])
    good = (color >= q1) & (color <= q99)
    # Original 1st/99th percentile color cuts. Apply the same mask to the added
    # measurement rows, ensuring the CSV and diagram describe the same stars.
    color, gmag, measurements = color[good], gmag[good], measurements[good]
    if len(color) == 0:
        raise ValueError("No measurements remain after color filtering.")

    # Original display choices: magnitude-based point sizes and a relative
    # blue/gray/red palette based on the retained stars' color distribution.
    bright = np.max(gmag) - gmag
    if np.max(bright) > 0:
        bright = bright / np.max(bright)
    sizes = 1 + 3 * bright**2
    middle = np.median(color)
    blue_limit, red_limit = np.percentile(color, [5, 95])
    blue_color = np.array([0.3, 0.6, 1.0])
    middle_color = np.array([0.6, 0.6, 0.6])
    red_color = np.array([1.0, 0.6, 0.3])
    rgb = np.zeros((len(color), 3))
    # Added rendering safeguard: if a color interval has zero width, use its gray
    # endpoint instead of dividing by zero. Measured colors/magnitudes are not
    # changed by this fallback; only the plotted marker colors are affected.
    for index, value in enumerate(color):
        if value <= middle:
            t = (
                np.clip((value - blue_limit) / (middle - blue_limit), 0, 1)
                if middle > blue_limit
                else 1.0
            )
            rgb[index] = (1 - t) * blue_color + t * middle_color
        else:
            t = (
                np.clip((value - middle) / (red_limit - middle), 0, 1)
                if red_limit > middle
                else 0.0
            )
            rgb[index] = (1 - t) * middle_color + t * red_color

    # Retain the original figure size, dark styling, labels, inverted magnitude
    # axis, and 200-dpi PNG. Save to bytes instead of a neighboring disk file.
    fig, ax = plt.subplots(figsize=(8, 9))
    try:
        fig.patch.set_facecolor("0.12")
        ax.set_facecolor("0.12")
        ax.scatter(color, gmag, s=sizes, c=rgb, alpha=0.85, edgecolors="none")
        ax.invert_yaxis()
        ax.set_xlabel("Instrumental B - G color", color="white")
        ax.set_ylabel("Instrumental G magnitude", color="white")
        ax.set_title("Color-Magnitude Diagram", color="white")
        ax.tick_params(colors="white")
        for spine in ax.spines.values():
            spine.set_color("white")
        ax.grid(alpha=0.15, color="white")
        fig.tight_layout()
        png = io.BytesIO()
        fig.savefig(png, format="png", dpi=200, facecolor=fig.get_facecolor())
    finally:
        # Added cleanup: release the figure after each analysis so repeated runs
        # in the same browser worker do not accumulate open Matplotlib figures.
        plt.close(fig)
    # Added download: export the plotted stars' positions, apertures, fluxes,
    # colors, and shifted magnitudes. Pixel coordinates are zero-based, as in
    # NumPy indexing; the underlying FITS image has not been modified.
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "x_pixel_0based",
            "y_pixel_0based",
            "aperture_radius",
            "R_flux",
            "G_flux",
            "B_flux",
            "instrumental_B_minus_G",
            "shifted_instrumental_G",
        ]
    )
    for row, c, m in zip(measurements, color, gmag, strict=True):
        writer.writerow([*row.tolist(), float(c), float(m)])
    # Browser adaptation: return results instead of printing progress/saving a
    # file/showing a window. Convert NumPy scalars/arrays to ordinary Python
    # values, and encode PNG bytes as text for the JSON/JavaScript boundary.
    return {
        "width": width,
        "height": height,
        "detected": detected,
        "positive_rgb": len(rows),
        "plotted": len(color),
        "background": float(background),
        "sigma": float(sigma),
        "color": color.tolist(),
        "magnitude": gmag.tolist(),
        "csv": output.getvalue(),
        "png": base64.b64encode(png.getvalue()).decode("ascii"),
    }


def analyze_bytes(raw: bytes) -> str:
    """Optional byte-input/JSON adapter; the web worker currently calls analyze.

    The web interface checks the same file-size limit before passing the file to
    the worker. This helper makes the limit available to other byte-based callers.
    """
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Choose a FITS file no larger than 250 MiB.")
    return json.dumps(analyze(io.BytesIO(raw)), allow_nan=False)
