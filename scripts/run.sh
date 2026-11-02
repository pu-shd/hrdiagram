#!/bin/zsh
set -euo pipefail
cd "${0:A:h:h}"
if [[ ! -f web/vendor/manifest.json ]]; then
  print -u2 'Missing browser runtime. Run ./scripts/build.sh first.'
  exit 1
fi
export HRDIAGRAM_PORT="${HRDIAGRAM_PORT:-8080}"
if [[ "$HRDIAGRAM_PORT" != <1-65535> ]]; then
  print -u2 'HRDIAGRAM_PORT must be an integer from 1 to 65535.'
  exit 1
fi
print "Open http://localhost:${HRDIAGRAM_PORT}. Press Control-C to stop the local preview."
docker-compose up web
