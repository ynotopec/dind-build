#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
VENV_DIR="${VENV_DIR:-$HOME/venv/$PROJECT_NAME}"
UNIT_NAME="${PROJECT_NAME}-mcp.service"
UNIT_PATH="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/$UNIT_NAME"
HERMES_CONFIG="${HERMES_CONFIG:-$HOME/.hermes/config.yaml}"

systemd_available=false
if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
    systemd_available=true
    systemctl --user disable --now "$UNIT_NAME" >/dev/null 2>&1 || true
fi
rm -f "$UNIT_PATH"
rm -rf "$VENV_DIR"
if [[ -f "$HERMES_CONFIG" ]] && grep -Eq '^  docker-build:[[:space:]]*$' "$HERMES_CONFIG"; then
    config_tmp="$(mktemp)"
    awk '
        /^  docker-build:[[:space:]]*$/ { removing=1; next }
        removing && /^(    |[[:space:]]*$)/ { next }
        { removing=0; print }
    ' "$HERMES_CONFIG" >"$config_tmp"
    cat "$config_tmp" >"$HERMES_CONFIG"
    rm -f "$config_tmp"
    echo "Removed docker-build from $HERMES_CONFIG"
fi
if [[ "$systemd_available" == true ]]; then
    systemctl --user daemon-reload
fi

echo "Removed $UNIT_NAME and $VENV_DIR"
echo "Kept project files and $PROJECT_DIR/.env"
