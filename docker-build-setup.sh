#!/usr/bin/env bash
# docker-build-setup.sh — Deploy the Docker Build Factory on any K8s cluster.
#
# Usage:
#   ./docker-build-setup.sh [namespace]
#
# Examples:
#   ./docker-build-setup.sh                       # defaults
#   ./docker-build-setup.sh my-namespace          # custom namespace
#
# This deploys:
#   1. Docker build pod (docker builder inside K8s)
#   2. K8s registry (local push/pull endpoint)
#
# Then prints the client (agent) configuration.

set -euo pipefail

NS="${1:-demo1}"
POD="docker-build"
REGISTRY="registry:5000"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

kubectl() { command kubectl -n "$NS" "$@"; }

# The namespace argument is part of the setup contract, so create it on the
# first installation on a cluster.
command kubectl get namespace "$NS" >/dev/null 2>&1 || command kubectl create namespace "$NS"

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
echo "  1. python3 -m pip install -r '$SCRIPT_DIR/mcp/requirements.txt'"
echo "  2. Add to ~/.hermes/config.yaml:"
echo ""
echo "    mcp_servers:"
echo "      docker-build:"
echo "        command: python3"
echo "        args: ['$SCRIPT_DIR/mcp/docker-build-mcp-server.py']"
echo "        timeout: 300"
echo ""
echo "  3. Restart the agent."
echo ""
echo "  ── FIRST BUILD ─────────────────────────────────"
echo "  ./docker-build.sh myapp:latest /path/to/project/"
echo ""
echo "═══════════════════════════════════════════════════════"
