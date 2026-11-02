# Third-party notices

The application license in `LICENSE.md` applies to this repository's application
code. It does not replace licenses for separately distributed dependencies.

The browser bundle uses [Pyodide](https://github.com/pyodide/pyodide) version
0.29.3, including CPython 3.13.2, and the scientific packages resolved by its
package lock. Pyodide uses the Mozilla Public License 2.0; CPython uses the
Python Software Foundation license and associated notices.

Scientific packages include NumPy, SciPy, Matplotlib, Astropy, PyERFA, OpenBLAS,
Pillow, and their dependencies. Their distributed wheels/archives retain
upstream license and copyright metadata. Runtime license files are included in
`vendor/`, and the package manifest identifies the exact downloaded files.

The photometry workflow was provided by Robert J. Vanderbei for classroom use.
His original script and course input/output files are not distributed here.
