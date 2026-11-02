#!/bin/zsh
set -euo pipefail
cd "${0:A:h:h}"
docker-compose build tools
docker-compose run --rm -T tools python scripts/vendor.py
docker-compose run --rm -T tools ruff check web/analysis.py scripts tests
docker-compose run --rm -T tools ruff format --check web/analysis.py scripts tests
docker-compose run --rm -T tools mypy
docker-compose run --rm -T lint-js npm ci --ignore-scripts
docker-compose run --rm -T lint-js npm run check
docker-compose run --rm -T tools python -m pytest -v -s tests
print 'PASS: lint, format, types, photometry tests, and browser workflows.'
