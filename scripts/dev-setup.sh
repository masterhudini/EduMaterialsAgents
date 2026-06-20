#!/usr/bin/env bash
set -euo pipefail

# Dev-only: create a local virtualenv for running tests and linters.
#
# IMPORTANT: the installed plugin NEVER uses this venv. At runtime, agents call the system
# python3 with $CLAUDE_PLUGIN_ROOT/shared/scripts on sys.path, and those scripts are pure
# stdlib. This venv exists purely for `pytest` during development.

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 -m venv .venv
.venv/bin/pip install --upgrade pip >/dev/null
.venv/bin/pip install -r requirements-dev.txt

echo ""
echo "Dev venv ready."
echo "  Run tests:  .venv/bin/pytest"
echo "  Activate:   source .venv/bin/activate"
