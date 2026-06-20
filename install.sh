#!/usr/bin/env bash
set -euo pipefail

# Installer for the edu-materials-agents plugin.
#
# Claude Code: registers this repo as a LOCAL MARKETPLACE via the official `claude plugin` CLI
# (the supported path that surfaces in /plugin) — no hand-editing of Claude's JSON registries.
# Codex: copies the plugin into ~/.codex and registers it in the Codex local marketplaces.
#
# The plugin RUNTIME is pure stdlib — no virtualenv is installed or used. Agents call the
# system python3 with $CLAUDE_PLUGIN_ROOT/shared/scripts on sys.path. The dev venv
# (scripts/dev-setup.sh) exists only for running tests locally and is NOT shipped.

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}"
PLUGIN_NAME="edu-materials-agents"
MARKETPLACE_NAME="edu-materials"      # must match name in .claude-plugin/marketplace.json

TARGET="all"
DRY_RUN=false

# What ships to Codex (Claude is handled by the CLI from REPO_ROOT). Dev-only files
# (tests/, scripts/, requirements-dev.txt, .venv/, .emagents/, inspiration/, docs/, mocks/)
# are deliberately excluded.
PLUGIN_ITEMS=(.claude-plugin skills agents commands shared)

usage() {
  cat <<'USAGE'
Usage: install.sh [--all|--claude|--codex] [--dry-run]

Installs the edu-materials-agents plugin. Default target: --all
  --claude   register as a local marketplace in Claude Code (via the claude CLI)
  --codex    install into Codex
  --all      both (default)
  --dry-run  print actions without changing anything
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

json_value() { python3 -c "import json; print(json.load(open('$1'))['$2'])"; }

copy_item() {
  local item="$1" dst="$2"
  if [[ -e "$REPO_ROOT/$item" ]]; then
    run cp -r "$REPO_ROOT/$item" "$dst/"
  else
    echo "Missing install item: $item" >&2; exit 1
  fi
}

install_claude() {
  if ! command -v claude >/dev/null; then
    echo "Claude Code CLI ('claude') not found in PATH" >&2; exit 1
  fi
  # Idempotent: drop any prior registration of this marketplace, then add it fresh from the
  # repo (which carries .claude-plugin/marketplace.json), and install the plugin from it.
  run claude plugin marketplace remove "$MARKETPLACE_NAME" >/dev/null 2>&1 || true
  run claude plugin marketplace add "$REPO_ROOT"
  run claude plugin install "${PLUGIN_NAME}@${MARKETPLACE_NAME}"
  echo "Claude: installed ${PLUGIN_NAME}@${MARKETPLACE_NAME}. Run /reload-plugins (or restart)."
}

install_codex() {
  local version plugin_dst skill_dst backup item skill_dir name
  version="$(json_value "$REPO_ROOT/.claude-plugin/plugin.json" version)"
  plugin_dst="${CODEX_HOME}/plugins/${PLUGIN_NAME}"
  skill_dst="${CODEX_HOME}/skills"

  if [[ -d "$plugin_dst" ]]; then
    backup="${plugin_dst}.bak.$(date +%s)"
    echo "WARN: $plugin_dst exists. Backup -> $backup"
    run mv "$plugin_dst" "$backup"
  fi
  run mkdir -p "$plugin_dst" "$skill_dst"
  for item in "${PLUGIN_ITEMS[@]}"; do copy_item "$item" "$plugin_dst"; done

  # Mirror each SKILL.md dir into Codex's flat skills dir (by dir name).
  if [[ -d "$REPO_ROOT/skills" ]]; then
    while IFS= read -r skill_md; do
      skill_dir="$(dirname "$skill_md")"
      name="$(basename "$skill_dir")"
      run rm -rf "$skill_dst/$name"
      run cp -r "$skill_dir" "$skill_dst/$name"
      echo "skill -> $skill_dst/$name"
    done < <(find "$REPO_ROOT/skills" -name SKILL.md)
  fi

  if ! $DRY_RUN; then
    python3 - <<PYEOF
import json
from pathlib import Path
plugin_name = "${PLUGIN_NAME}"
plugin_entry = {
    "name": plugin_name,
    "source": {"source": "local", "path": f"./.codex/plugins/{plugin_name}"},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity",
}
for rel in (".agents/plugins/marketplace.json", ".agents/plugins/api_marketplace.json"):
    path = Path.home() / rel
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict): data = {}
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    data.setdefault("name", "local-plugins")
    data.setdefault("interface", {"displayName": "Local Plugins"})
    plugins = [p for p in data.get("plugins", []) if p.get("name") != plugin_name]
    plugins.append(plugin_entry)
    data["plugins"] = plugins
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Registered {plugin_name} in {path}")
PYEOF
  fi
  echo "Codex: installed v${version} -> $plugin_dst"
}

case "$TARGET" in
  all) install_claude; install_codex ;;
  claude) install_claude ;;
  codex) install_codex ;;
esac

echo ""
echo "Skills: $(find "$REPO_ROOT/skills" -name SKILL.md 2>/dev/null | wc -l | tr -d ' ')  Agents: $(find "$REPO_ROOT/agents" -type f -name '*.md' ! -name 'README.md' 2>/dev/null | wc -l | tr -d ' ')"
