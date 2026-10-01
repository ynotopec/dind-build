#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
VENV_DIR="${VENV_DIR:-$HOME/venv/$PROJECT_NAME}"
UNIT_NAME="${PROJECT_NAME}-mcp.service"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_PATH="$UNIT_DIR/$UNIT_NAME"
CONFIGURE_HERMES=auto

for arg in "$@"; do
    case "$arg" in
        --hermes) CONFIGURE_HERMES=true ;;
        --no-hermes) CONFIGURE_HERMES=false ;;
        *) echo "Usage: $0 [--hermes|--no-hermes]" >&2; exit 2 ;;
    esac
done

if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.env"
    set +a
fi

if [[ -z "${KUBE_NAMESPACE:-}" || "$KUBE_NAMESPACE" == "<namespace>" ]]; then
    if [[ ! -f "$PROJECT_DIR/.env" ]]; then
        cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
        chmod 600 "$PROJECT_DIR/.env"
    fi
    echo "KUBE_NAMESPACE is required. Set it in $PROJECT_DIR/.env or export it, then rerun install.sh." >&2
    exit 2
fi

if [[ -z "${MCP_API_TOKEN:-}" || "$MCP_API_TOKEN" == \<*\> ]]; then
    MCP_API_TOKEN="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
fi

if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    umask 077
    {
        printf 'KUBE_NAMESPACE=%q\n' "$KUBE_NAMESPACE"
        printf 'MCP_API_TOKEN=%q\n' "$MCP_API_TOKEN"
        sed -n '/^#/p' "$PROJECT_DIR/.env.example"
    } >"$PROJECT_DIR/.env"
elif ! grep -Eq '^MCP_API_TOKEN=' "$PROJECT_DIR/.env" || grep -Eq '^MCP_API_TOKEN="?<[^>]+>"?$' "$PROJECT_DIR/.env"; then
    config_tmp="$(mktemp)"
    grep -Ev '^MCP_API_TOKEN=' "$PROJECT_DIR/.env" >"$config_tmp"
    printf 'MCP_API_TOKEN=%q\n' "$MCP_API_TOKEN" >>"$config_tmp"
    cat "$config_tmp" >"$PROJECT_DIR/.env"
    rm -f "$config_tmp"
fi
chmod 600 "$PROJECT_DIR/.env"

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required: https://docs.astral.sh/uv/getting-started/installation/" >&2
    exit 1
fi

mkdir -p "$(dirname "$VENV_DIR")" "$UNIT_DIR"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
uv venv --python "$PYTHON_BIN" "$VENV_DIR"
uv pip install --python "$VENV_DIR/bin/python" --upgrade -r "$PROJECT_DIR/mcp/requirements.txt"

HERMES_CONFIG="${HERMES_CONFIG:-$HOME/.hermes/config.yaml}"
if [[ "$CONFIGURE_HERMES" == auto ]]; then
    if [[ -d "$(dirname "$HERMES_CONFIG")" || -f "$HERMES_CONFIG" ]]; then
        CONFIGURE_HERMES=true
    else
        CONFIGURE_HERMES=false
    fi
fi

if [[ "$CONFIGURE_HERMES" == true ]]; then
    mkdir -p "$(dirname "$HERMES_CONFIG")"
    touch "$HERMES_CONFIG"
    chmod 600 "$HERMES_CONFIG"
    config_tmp="$(mktemp)"
    if grep -Eq '^  docker-build:[[:space:]]*$' "$HERMES_CONFIG"; then
        awk -v command="$PROJECT_DIR/stdio.sh" '
            /^  docker-build:[[:space:]]*$/ {
                print "  docker-build:"
                print "    command: " command
                print "    args: []"
                print "    timeout: 300"
                replacing=1
                next
            }
            replacing && /^(    |[[:space:]]*$)/ { next }
            { replacing=0; print }
        ' "$HERMES_CONFIG" >"$config_tmp"
    elif grep -Eq '^mcp_servers:[[:space:]]*$' "$HERMES_CONFIG"; then
            awk -v command="$PROJECT_DIR/stdio.sh" '
                { print }
                !inserted && /^mcp_servers:[[:space:]]*$/ {
                    print "  docker-build:"
                    print "    command: " command
                    print "    args: []"
                    print "    timeout: 300"
                    inserted=1
                }
            ' "$HERMES_CONFIG" >"$config_tmp"
    elif grep -Eq '^mcp_servers:[[:space:]]*\{[[:space:]]*\}[[:space:]]*$' "$HERMES_CONFIG"; then
            awk -v command="$PROJECT_DIR/stdio.sh" '
                /^mcp_servers:[[:space:]]*\{[[:space:]]*\}[[:space:]]*$/ {
                    print "mcp_servers:"
                    print "  docker-build:"
                    print "    command: " command
                    print "    args: []"
                    print "    timeout: 300"
                    next
                }
                { print }
            ' "$HERMES_CONFIG" >"$config_tmp"
    else
        cat "$HERMES_CONFIG" >"$config_tmp"
        [[ ! -s "$config_tmp" ]] || printf '\n' >>"$config_tmp"
        cat >>"$config_tmp" <<EOF
mcp_servers:
  docker-build:
    command: $PROJECT_DIR/stdio.sh
    args: []
    timeout: 300
EOF
    fi
    cat "$config_tmp" >"$HERMES_CONFIG"
    rm -f "$config_tmp"
    echo "Configured Hermes MCP server in $HERMES_CONFIG"
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
    systemctl --user enable "$UNIT_NAME"
    systemctl --user restart "$UNIT_NAME"
    if command -v loginctl >/dev/null 2>&1; then
        loginctl enable-linger "$(id -un)" >/dev/null 2>&1 || \
            echo "Could not enable user lingering; the service will start when the user logs in."
    fi
    AUTOSTART="systemd --user"
else
    echo "User systemd is unavailable; the unit was installed but not reloaded."
    if [[ "$CONFIGURE_HERMES" == true ]]; then
        AUTOSTART="Hermes stdio lifecycle"
    else
        AUTOSTART="unavailable"
    fi
fi

echo "Installed virtual environment: $VENV_DIR"
echo "Installed user service: $UNIT_NAME"
echo "Persistent startup: $AUTOSTART"
if [[ "$CONFIGURE_HERMES" == true ]]; then
    echo "Restart Hermes or open a new session to load the MCP server."
else
    echo "Hermes not detected; run '$0 --hermes' to configure it."
    if [[ "$AUTOSTART" == unavailable ]]; then
        echo "No supported supervisor was detected; configure the container runtime to execute $PROJECT_DIR/run.sh on restart." >&2
    fi
fi
