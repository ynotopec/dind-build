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

exec "$VENV_DIR/bin/python" "$PROJECT_DIR/mcp/docker-build-mcp-server.py"
