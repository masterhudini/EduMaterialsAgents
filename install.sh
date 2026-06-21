#!/usr/bin/env bash
set -euo pipefail

# Cross-platform installer entry point for POSIX shells.
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Python 3 is required to build and install edu-materials-agents." >&2
  exit 1
fi

exec "$PYTHON_BIN" "$REPO_ROOT/scripts/install_plugin.py" "$@"
