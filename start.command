#!/bin/sh
# Run from Finder or Terminal; independent of Codex.
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import flask' >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements.txt
fi
printf '\nMarginGuard: http://127.0.0.1:5050\nKeep this Terminal window open. Ctrl+C stops the server.\n\n'
export PYTHONDONTWRITEBYTECODE=1
exec .venv/bin/python app.py
