# Method and interpretation

This tool reproduces the supplied classroom algorithm for an **instrumental
color–magnitude diagram**. RGB channels are camera/image channels. In particular,
the green channel is not Gaia G, and blue-minus-green is not a calibrated
standard photometric color index.

## Input

- FITS image with axes `(3, height, width)`, ordered red, green, blue.
- Linear pixel values: a temporary display autostretch is compatible, while
  saving a nonlinear stretch changes the measurements.
- At least 27 pixels in each spatial dimension; prototype limits are 12 million
  spatial pixels and 160 MiB per file.
- Finite pixel values. Missing/infinite pixels produce an explanatory error.

The prototype reads the first image HDU containing data. It does not debayer
raw sensor data, register channels, or combine separate monochrome exposures.

Before processing, the page reads at most 32 FITS header blocks (about 90 KiB)
to display primary-image dimensions and flag known size-limit violations. If the
image is in an extension HDU or its primary header cannot be identified, the
dimensions are checked by Astropy during analysis. Full FITS validation remains
in Python. Displayed RGB-array memory is `width × height × 3 × 8` bytes, not total
working memory or a forecast of browser capacity. Any device-memory report is
rounded installed RAM; the page does not measure free RAM or a per-page limit.

## Calculations

1. Detect stars in the RGB mean after Gaussian smoothing with sigma 1 pixel.
   The threshold is the unsmoothed image median plus five times its MAD-derived
   noise estimate. Detect local maxima with a seven-pixel filter and exclude
   edge positions using the supplied script's 12-pixel border.
2. Measure each channel in a circular aperture of radius 3, 4, or 5 pixels.
   Brightness percentiles 70 and 95 select the larger apertures. Subtract the
   median local sky estimated between radii 7 and 10 pixels.
3. Keep positive measured flux in every RGB channel. Convert fluxes to
   instrumental magnitudes using `-2.5 log10(flux)`.
4. Plot instrumental blue-minus-green color against green magnitude. Shift
   magnitudes so the brightest measured star is 10, before color filtering.
5. Exclude colors below the first or above the 99th percentile. Color the points
   using the supplied script's relative blue/gray/red mapping.

CSV files contain the plotted stars only, with zero-based image coordinates,
aperture radii, background-subtracted fluxes, and plotted color/magnitude values.
The displayed detection, positive-flux, and final plotted counts make selection
steps visible to students.

## Limits

There is no distance determination, absolute magnitude calculation, temperature
calibration, or Gaia/VizieR lookup. A cluster whose stars have approximately the
same distance can make a useful classroom example; a mixed-distance field has a
different interpretation. Instrumental values across separately processed images
are not automatically comparable.

The supplied algorithm does not explicitly reject saturated stars, deblend
overlapping sources, estimate photometric uncertainties, correct extinction, or
fit a spatial background model. Fixed pixel apertures depend on image scale and
seeing. Color clipping can remove real astrophysical outliers. These limitations
are retained rather than changing the exercise's scientific method.

Added safeguards handle empty detections, fewer than three positive RGB
measurements, invalid input, and constant-color rendering. PNG pixel appearance
can differ between Matplotlib/font versions even when plotted measurements match.
