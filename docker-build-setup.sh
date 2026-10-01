#!/usr/bin/env bash
# docker-build-setup.sh — Deploy the Docker Build Factory on any K8s cluster.
#
# Usage:
#   KUBE_NAMESPACE="<namespace>" ./docker-build-setup.sh
#
# This deploys:
#   1. Docker build pod (docker builder inside K8s)
#   2. K8s registry (local push/pull endpoint)
#
# Then prints the client (agent) configuration.

set -euo pipefail

NS="${KUBE_NAMESPACE:?KUBE_NAMESPACE must be set}"
POD="docker-build"
REGISTRY="registry:5000"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

kubectl() { command kubectl -n "$NS" "$@"; }

# The namespace must be provisioned by an administrator. Keep every operation
# namespace-scoped so this setup does not require cluster-wide permissions.
if ! kubectl get pods >/dev/null; then
    echo "Error: namespace '$NS' must already exist and be accessible." >&2
    exit 1
fi

echo "═══════════════════════════════════════════════════════"
echo "  Docker Build Factory — Setup"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "  Namespace:  $NS"
echo "  Pod:        $POD"
echo "  Registry:   $REGISTRY"
echo ""

# ── 1. Deploy Docker build pod ──────────────────────────────────────────────────────

echo "→ Deploying Docker build pod..."
kubectl apply -f "$SCRIPT_DIR/docker-build-pod.yaml"

# ── 2. Deploy K8s registry ─────────────────────────────────────────────────

echo "→ Deploying K8s registry..."
kubectl apply -f "$SCRIPT_DIR/registry.yaml"

# Applying both resources before waiting lets Kubernetes start them in
# parallel, reducing cold-start latency.
kubectl wait pod/"$POD" --for=condition=ready --timeout=60s
echo "  ✓ Pod $POD ready."
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
echo "  Docker build pod and K8s registry are now running."
echo ""
echo "  ── CLIENT (Agent) ───────────────────────────────"
echo "  1. $SCRIPT_DIR/install.sh"
echo "  2. Add the following entry to your MCP client configuration:"
echo ""
echo '    {'
echo '      "mcpServers": {'
echo '        "docker-build": {'
echo "          \"command\": \"$HOME/venv/$(basename "$SCRIPT_DIR")/bin/python\","
echo "          \"args\": [\"$SCRIPT_DIR/mcp/docker-build-mcp-server.py\"],"
echo "          \"env\": {\"KUBE_NAMESPACE\": \"$NS\"}"
echo '        }'
echo '      }'
echo '    }'
echo ""
echo "  3. Restart the agent."
echo ""
echo "  ── FIRST BUILD ─────────────────────────────────"
echo "  ./docker-build.sh myapp:latest /path/to/project/"
echo ""
echo "═══════════════════════════════════════════════════════"
