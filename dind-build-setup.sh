#!/usr/bin/env bash
# dind-build-setup.sh — Deploy the entire DinD Build Factory on any K8s cluster.
#
# Usage:
#   ./dind-build-setup.sh [namespace]
#
# Examples:
#   ./dind-build-setup.sh                       # defaults
#   ./dind-build-setup.sh my-namespace           # custom namespace
#
# This deploys:
#   1. DinD pod (docker builder inside K8s)
#   2. K8s registry (local push/pull endpoint)
#
# Then prints the client (agent) configuration.

set -euo pipefail

NS="${1:-demo1}"
POD="dind-build"
REGISTRY="registry:5000"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

kubectl() { command kubectl -n "$NS" "$@"; }

echo "═══════════════════════════════════════════════════════"
echo "  DinD Build Factory — Setup"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "  Namespace:  $NS"
echo "  Pod:        $POD"
echo "  Registry:   $REGISTRY"
echo ""

# ── 1. Deploy DinD pod ──────────────────────────────────────────────────────

echo "→ Deploying DinD pod..."
kubectl apply -f "$SCRIPT_DIR/dind-pod.yaml"
kubectl wait pod/"$POD" --for=condition=ready --timeout=60s
echo "  ✓ Pod $POD ready."

# ── 2. Deploy K8s registry ─────────────────────────────────────────────────

echo "→ Deploying K8s registry..."
kubectl apply -f "$SCRIPT_DIR/registry.yaml"
kubectl wait deployment/registry --for=condition=Available --timeout=60s
echo "  ✓ Registry deployed."

# ── 3. Test ─────────────────────────────────────────────────────────────────

echo "→ Testing..."
TEST_RESULT=$(kubectl exec "$POD" -- sh -c 'wget -q -O- http://registry:5000/v2/_catalog' 2>&1) || {
    echo "  ⚠ Registry not reachable from pod"
    exit 1
}
echo "  ✓ Registry reachable: $TEST_RESULT"

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  ✓ Factory deployed!"
echo ""
echo "  ── SERVER (done) ──────────────────────────────────"
echo "  DinD pod and K8s registry are now running."
echo ""
echo "  ── CLIENT (Agent) ───────────────────────────────"
echo "  1. python3 -m pip install -r '$SCRIPT_DIR/mcp/requirements.txt'"
echo "  2. Add to ~/.hermes/config.yaml:"
echo ""
echo "    mcp_servers:"
echo "      dind-build:"
echo "        command: python3"
echo "        args: ['$SCRIPT_DIR/mcp/dind-mcp-server.py']"
echo "        timeout: 300"
echo ""
echo "  3. Restart the agent."
echo ""
echo "  ── FIRST BUILD ─────────────────────────────────"
echo "  ./dind-build.sh myapp:latest /path/to/project/"
echo ""
echo "═══════════════════════════════════════════════════════"
