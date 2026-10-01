#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="$(basename "$PROJECT_DIR")"
VENV_DIR="${VENV_DIR:-$HOME/venv/$PROJECT_NAME}"

if [[ -f "$PROJECT_DIR/.env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_DIR/.env"
    set +a
fi

: "${KUBE_NAMESPACE:?KUBE_NAMESPACE must be set in .env or the environment}"
: "${MCP_API_TOKEN:?MCP_API_TOKEN must be set in .env or the environment}"

host="${1:-${MCP_HOST:-127.0.0.1}}"
port="${2:-${MCP_PORT:-}}"

if [[ -z "$port" ]]; then
    port="$("$VENV_DIR/bin/python" - <<'PY'
import socket

with socket.socket() as sock:
    sock.bind(("", 0))
    print(sock.getsockname()[1])
PY
)"
fi

exec "$VENV_DIR/bin/python" "$PROJECT_DIR/mcp/docker-build-mcp-server.py" \
    --http --host "$host" --port "$port"
