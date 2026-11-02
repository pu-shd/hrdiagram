#!/bin/zsh
set -euo pipefail
cd "${0:A:h:h}"
if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python scripts/publish.py "$@"
fi
exec python3 scripts/publish.py "$@"
