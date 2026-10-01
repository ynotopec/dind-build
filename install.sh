#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
VENV_DIR="${VENV_DIR:-$HOME/venv/$PROJECT_NAME}"
UNIT_NAME="${PROJECT_NAME}-mcp.service"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_PATH="$UNIT_DIR/$UNIT_NAME"

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

mkdir -p "$(dirname "$VENV_DIR")" "$UNIT_DIR"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
uv venv --python "$PYTHON_BIN" "$VENV_DIR"
uv pip install --python "$VENV_DIR/bin/python" --upgrade -r "$PROJECT_DIR/mcp/requirements.txt"

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    chmod 600 "$PROJECT_DIR/.env"
    echo "Created $PROJECT_DIR/.env; configure it before starting the service."
fi

cat >"$UNIT_PATH" <<EOF
[Unit]
Description=Docker Build MCP server
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/run.sh
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
    systemctl --user daemon-reload
    if systemctl --user is-active --quiet "$UNIT_NAME"; then
        systemctl --user restart "$UNIT_NAME"
    fi
else
    echo "User systemd is unavailable; the unit was installed but not reloaded."
fi

echo "Installed virtual environment: $VENV_DIR"
echo "Installed user service: $UNIT_NAME"
echo "Start it with: systemctl --user enable --now $UNIT_NAME"
