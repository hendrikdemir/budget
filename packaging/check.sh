#!/usr/bin/env bash
# Every check, as GitHub runs them for each push (.github/workflows/checks.yml): the tests
# (with the page tests in WebKit), lint and security checks for the Python, and type checks and
# lint for the page. Installs what's needed the first time.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d .venv-build ] || python3 -m venv .venv-build
.venv-build/bin/pip install --quiet -r requirements-dev.txt
.venv-build/bin/playwright install webkit > /dev/null
[ -d node_modules ] || npm ci --silent

echo "Tests (with the page in WebKit)…"
.venv-build/bin/python -m unittest
echo "Python: ruff…"
.venv-build/bin/ruff check .
echo "Page: type checks and ESLint…"
npm run --silent check
echo "All checks passed."
