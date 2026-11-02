"""Bob's instrumental RGB photometry, shared by the browser and native tests."""

import base64
import csv
import io
import json
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from astropy.io import fits
from scipy.ndimage import gaussian_filter, maximum_filter

MAX_FILE_BYTES = 160 * 1024 * 1024
MAX_PIXELS = 12_000_000


def analyze(source: Any) -> dict[str, Any]:
    """Return the diagram, plotted measurements, and explicit selection counts.

    Preserve the supplied script's detection, aperture, percentile, and magnitude
    rules. Added validation and constant-color handling protect the web interface.
    """
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
                raise ValueError("This browser prototype supports images up to 12 megapixels.")
            data = image.data.astype(float)
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(
            "Unable to read this FITS image. Check its format and completeness."
        ) from error
    if not np.isfinite(data).all():
        raise ValueError("The image contains missing or infinite pixel values.")

    red, green, blue = data
    luminance = (red + green + blue) / 3.0
    background = np.median(luminance)
    sigma = 1.4826 * np.median(np.abs(luminance - background))
    threshold = background + 5.0 * sigma
    smoothed = gaussian_filter(luminance, 1.0)
    maxima = smoothed == maximum_filter(smoothed, size=7)
    y, x = np.where(maxima & (smoothed > threshold))
    border = (x > 12) & (x < width - 12) & (y > 12) & (y < height - 12)
    x, y = x[border], y[border]
    detected = len(x)
    if detected == 0:
        raise ValueError("No usable stars were detected. Try a different linear RGB FITS image.")
    peaks = smoothed[y, x] - background
    p70, p95 = np.percentile(peaks, [70, 95])
    yy, xx = np.mgrid[-10:11, -10:11]
    distance = np.sqrt(xx**2 + yy**2)
    annulus = (distance >= 7) & (distance <= 10)
    rows = []
    for sx, sy, peak in zip(x, y, peaks, strict=True):
        radius = 3 if peak < p70 else 4 if peak < p95 else 5
        aperture = distance <= radius
        fluxes = []
        for channel in (red, green, blue):
            box = channel[sy - 10 : sy + 11, sx - 10 : sx + 11]
            sky = np.median(box[annulus])
            fluxes.append(float(np.sum(box[aperture] - sky)))
        if all(flux > 0 for flux in fluxes):
            rows.append([float(sx), float(sy), float(radius), *fluxes])
    if len(rows) < 3:
        raise ValueError("Fewer than three stars have positive measurements in all RGB channels.")
    measurements = np.asarray(rows)
    rflux, gflux, bflux = measurements[:, 3:].T
    gmag = -2.5 * np.log10(gflux)
    color = -2.5 * np.log10(bflux) - gmag
    gmag = gmag - np.min(gmag) + 10
    q1, q99 = np.percentile(color, [1, 99])
    good = (color >= q1) & (color <= q99)
    color, gmag, measurements = color[good], gmag[good], measurements[good]
    if len(color) == 0:
        raise ValueError("No measurements remain after color filtering.")

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
        plt.close(fig)
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
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("Choose a FITS file smaller than 160 MiB.")
    return json.dumps(analyze(io.BytesIO(raw)), allow_nan=False)
