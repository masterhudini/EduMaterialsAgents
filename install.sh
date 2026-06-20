#!/usr/bin/env bash
set -euo pipefail

# Installer for the edu-materials-agents plugin.
# Installs into Claude Code and/or Codex. Adapted from the meta-factory reference installer.
#
# The plugin RUNTIME is pure stdlib — no virtualenv is installed or used. Agents call the
# system python3 with $CLAUDE_PLUGIN_ROOT/shared/scripts on sys.path. A dev venv (see
# scripts/dev-setup.sh) exists only for running the test suite locally and is NOT shipped.

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}"
CLAUDE_INSTALLED_JSON="${HOME}/.claude/plugins/installed_plugins.json"
PLUGIN_NAME="edu-materials-agents"

TARGET="all"
DRY_RUN=false

# Only these items ship to the install target. Dev-only files (tests/, scripts/,
# requirements-dev.txt, .venv/, .emagents/, inspiration/, docs/) are deliberately excluded.
PLUGIN_ITEMS=(skills agents commands shared plugin.json)

usage() {
  cat <<'USAGE'
Usage: install.sh [--all|--claude|--codex] [--dry-run]

Installs the edu-materials-agents plugin. Default target: --all
  --claude   install into Claude Code only
  --codex    install into Codex only
  --all      install into both (default)
  --dry-run  print actions without touching the filesystem
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

assert_writable_dir() {
  local dir="$1" probe_parent probe
  probe_parent="$dir"
  while [[ ! -d "$probe_parent" && "$probe_parent" != "/" ]]; do
    probe_parent="$(dirname "$probe_parent")"
  done
  probe="${probe_parent}/.${PLUGIN_NAME}-write-test.$$"
  if $DRY_RUN; then echo "DRY: check writable -> $probe_parent"; return; fi
  if ! touch "$probe" 2>/dev/null; then
    echo "ERROR: install target not writable: $probe_parent" >&2
    echo "  cd $REPO_ROOT && bash install.sh" >&2
    exit 1
  fi
  rm -f "$probe"
}

json_value() { python3 -c "import json; print(json.load(open('$1'))['$2'])"; }

copy_item() {
  local item="$1" dst="$2"
  if [[ -e "$REPO_ROOT/$item" ]]; then
    run cp -r "$REPO_ROOT/$item" "$dst/"
  else
    echo "Missing required install item: $item" >&2; exit 1
  fi
}

install_claude() {
  local version plugin_dst backup item tmp_dst
  version="$(json_value "$REPO_ROOT/plugin.json" version)"
  plugin_dst="${HOME}/.claude/plugins/cache/local/${PLUGIN_NAME}/${version}"
  assert_writable_dir "$(dirname "$plugin_dst")"

  if ! command -v claude >/dev/null; then
    if $DRY_RUN; then echo "WARN: Claude Code not in PATH; dry run continues."
    else echo "Claude Code not found in PATH" >&2; exit 1; fi
  fi

  tmp_dst="$(mktemp -d /tmp/${PLUGIN_NAME}-claude.XXXXXX)"
  for item in "${PLUGIN_ITEMS[@]}"; do copy_item "$item" "$tmp_dst"; done

  if ! $DRY_RUN; then
    python3 - <<PYEOF
import json
from pathlib import Path
Path("${tmp_dst}/package.json").write_text(
    json.dumps({"name": "${PLUGIN_NAME}", "version": "${version}"}, indent=2) + "\n")
PYEOF
  fi

  if [[ -d "$plugin_dst" ]]; then
    backup="${plugin_dst}.bak.$(date +%s)"
    echo "WARN: $plugin_dst exists. Backup -> $backup"
    run mv "$plugin_dst" "$backup"
  fi
  run mkdir -p "$(dirname "$plugin_dst")"
  run mv "$tmp_dst" "$plugin_dst"

  if ! $DRY_RUN; then
    python3 - <<PYEOF
import datetime, json
from pathlib import Path
path = Path("${CLAUDE_INSTALLED_JSON}")
now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
try:
    data = json.loads(path.read_text())
except FileNotFoundError:
    data = {"version": 2, "plugins": {}}
key = "${PLUGIN_NAME}@local"
existing = data["plugins"].get(key, [{}])
installed_at = existing[0].get("installedAt", now) if existing else now
data["plugins"][key] = [{"scope": "user", "installPath": "${plugin_dst}",
                         "version": "${version}", "installedAt": installed_at, "lastUpdated": now}]
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(data, indent=2) + "\n")
print(f"Registered ${PLUGIN_NAME}@local v{path}")
PYEOF
  fi
  echo "Installed Claude plugin v${version} -> $plugin_dst"
}

install_codex() {
  local version plugin_dst skill_dst backup item skill_dir name
  version="$(json_value "$REPO_ROOT/plugin.json" version)"
  plugin_dst="${CODEX_HOME}/plugins/${PLUGIN_NAME}"
  skill_dst="${CODEX_HOME}/skills"
  assert_writable_dir "$(dirname "$plugin_dst")"
  assert_writable_dir "$skill_dst"

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

  # Register local plugin in Codex marketplaces used by regular and API-key logins.
  if ! $DRY_RUN; then
    python3 - <<PYEOF
import json
from pathlib import Path

plugin_name = "${PLUGIN_NAME}"
plugin_path = f"./.codex/plugins/{plugin_name}"
plugin_entry = {
    "name": plugin_name,
    "source": {"source": "local", "path": plugin_path},
    "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
    "category": "Productivity",
}

for rel_path in (".agents/plugins/marketplace.json", ".agents/plugins/api_marketplace.json"):
    path = Path.home() / rel_path
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict):
            data = {}
    except FileNotFoundError:
        data = {}
    except json.JSONDecodeError:
        data = {}

    data.setdefault("name", "local-plugins")
    data.setdefault("interface", {"displayName": "Local Plugins"})
    plugins = data.setdefault("plugins", [])

    plugins = [p for p in plugins if p.get("name") != plugin_name]
    plugins.append(plugin_entry)
    data["plugins"] = plugins

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    print(f"Registered {plugin_name} in {path}")
PYEOF
  fi
  echo "Installed Codex plugin v${version} -> $plugin_dst"
}

case "$TARGET" in
  all) install_claude; install_codex ;;
  claude) install_claude ;;
  codex) install_codex ;;
esac

echo ""
echo "Installed skills: $(find "$REPO_ROOT/skills" -name SKILL.md 2>/dev/null | wc -l | tr -d ' ')"
echo "Agents:           $(find "$REPO_ROOT/agents" -type f -name '*.md' 2>/dev/null | wc -l | tr -d ' ')"
echo "Restart Claude Code / Codex CLI to activate."
