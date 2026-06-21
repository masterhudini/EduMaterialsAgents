#!/usr/bin/env bash
set -euo pipefail

# Installer for the edu-materials-agents plugin.
#
# The repo is source of truth, but the installed plugin is a generated host-specific bundle.
# Build output lives under dist/ and is safe to delete/regenerate.
#
# The plugin RUNTIME is pure stdlib — no virtualenv is installed or used. Agents call the
# system python3. The dev venv (scripts/dev-setup.sh) exists only for running tests locally
# and is NOT shipped.

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_NAME="edu-materials-agents"
MARKETPLACE_NAME="edu-materials"      # must match plugin.manifest.json marketplace.name
CODEX_MARKETPLACE_NAME="local-plugins"
CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}"
BUILD_SCRIPT="$REPO_ROOT/scripts/build-plugin.py"
CLAUDE_MARKETPLACE_ROOT="$REPO_ROOT/dist/claude"
CODEX_MARKETPLACE_ROOT="$REPO_ROOT/dist/codex"
CODEX_PLUGIN_SRC="$CODEX_MARKETPLACE_ROOT/plugins/$PLUGIN_NAME"
CODEX_PLUGIN_DST="$CODEX_HOME/plugins/$PLUGIN_NAME"
CODEX_LOCAL_MARKETPLACE="${HOME}/.agents/plugins/marketplace.json"

TARGET="all"
DRY_RUN=false

usage() {
  cat <<'USAGE'
Usage: install.sh [--all|--claude|--codex] [--dry-run]

Builds and installs/registers the edu-materials-agents plugin. Default target: --all
  --claude   build dist/claude and install from that Claude Code marketplace
  --codex    build dist/codex, copy it into ~/.codex/plugins, and register under Local Plugins
  --all      both (default)
  --dry-run  print install actions; still validates build inputs
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) TARGET="all"; shift ;;
    --claude) TARGET="claude"; shift ;;
    --codex) TARGET="codex"; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage >&2; exit 1 ;;
  esac
done

run() { if $DRY_RUN; then echo "DRY: $*"; else "$@"; fi; }

build() {
  local host="$1"
  if [[ ! -x "$BUILD_SCRIPT" ]]; then
    chmod +x "$BUILD_SCRIPT"
  fi
  "$BUILD_SCRIPT" --host "$host"
}

install_claude() {
  build claude
  if ! command -v claude >/dev/null; then
    echo "Claude Code CLI ('claude') not found in PATH" >&2; exit 1
  fi
  # Idempotent: drop any prior registration of this marketplace, then add the generated
  # marketplace root. The repo itself is not the installed production plugin.
  run claude plugin marketplace remove "$MARKETPLACE_NAME" >/dev/null 2>&1 || true
  run claude plugin marketplace add "$CLAUDE_MARKETPLACE_ROOT"
  run claude plugin install "${PLUGIN_NAME}@${MARKETPLACE_NAME}"
  echo "Claude: installed ${PLUGIN_NAME}@${MARKETPLACE_NAME} from $CLAUDE_MARKETPLACE_ROOT."
  echo "Run /reload-plugins (or restart)."
}

install_codex() {
  build codex
  if ! command -v codex >/dev/null; then
    echo "Codex CLI ('codex') not found in PATH" >&2; exit 1
  fi
  run mkdir -p "$CODEX_HOME/plugins"
  run rm -rf "$CODEX_PLUGIN_DST"
  run cp -R "$CODEX_PLUGIN_SRC" "$CODEX_PLUGIN_DST"
  if $DRY_RUN; then
    echo "DRY: register ${PLUGIN_NAME} in ${CODEX_LOCAL_MARKETPLACE}"
  else
    python3 - "$CODEX_LOCAL_MARKETPLACE" "$PLUGIN_NAME" <<'PYEOF'
import json
import sys
from pathlib import Path

marketplace_path = Path(sys.argv[1])
plugin_name = sys.argv[2]
entry = {
    "name": plugin_name,
    "source": {"source": "local", "path": f"./.codex/plugins/{plugin_name}"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Developer Tools",
}

try:
    data = json.loads(marketplace_path.read_text())
except (FileNotFoundError, json.JSONDecodeError):
    data = {}

data.setdefault("name", "local-plugins")
data.setdefault("interface", {"displayName": "Local Plugins"})
plugins = [p for p in data.get("plugins", []) if p.get("name") != plugin_name]
plugins.append(entry)
data["plugins"] = plugins

marketplace_path.parent.mkdir(parents=True, exist_ok=True)
marketplace_path.write_text(json.dumps(data, indent=2) + "\n")
PYEOF
  fi
  run codex plugin add "${PLUGIN_NAME}@${CODEX_MARKETPLACE_NAME}"
  # Migration cleanup for older installs that registered a dedicated Codex marketplace.
  if $DRY_RUN; then
    echo "DRY: codex plugin remove ${PLUGIN_NAME}@${MARKETPLACE_NAME}"
    echo "DRY: codex plugin marketplace remove ${MARKETPLACE_NAME}"
  else
    codex plugin remove "${PLUGIN_NAME}@${MARKETPLACE_NAME}" >/dev/null 2>&1 || true
    codex plugin marketplace remove "$MARKETPLACE_NAME" >/dev/null 2>&1 || true
  fi
  echo "Codex: installed ${PLUGIN_NAME}@${CODEX_MARKETPLACE_NAME} from $CODEX_PLUGIN_DST."
  echo "Codex: removed legacy ${MARKETPLACE_NAME} marketplace if it was configured."
  echo "Start a new Codex thread so the plugin's skills and MCP tools are loaded."
}

case "$TARGET" in
  all) install_claude; install_codex ;;
  claude) install_claude ;;
  codex) install_codex ;;
esac

echo ""
echo "Source skills: $(find "$REPO_ROOT/skills" -name SKILL.md 2>/dev/null | wc -l | tr -d ' ')  Source agents: $(find "$REPO_ROOT/agents" -type f -name '*.md' ! -name 'README.md' 2>/dev/null | wc -l | tr -d ' ')"
