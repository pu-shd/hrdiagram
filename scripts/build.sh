#!/bin/zsh
set -euo pipefail
cd "${0:A:h:h}"
docker-compose build tools
docker-compose run --rm -T tools python scripts/vendor.py
docker-compose run --rm -T tools python scripts/package.py
