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
CHART_DIR="$SCRIPT_DIR/chart"
TLS_HOST="${TLS_HOST:-}"
CERT_MANAGER_CLUSTER_ISSUER="${CERT_MANAGER_CLUSTER_ISSUER:-}"

kubectl() { command kubectl -n "$NS" "$@"; }

if [[ -z "$TLS_HOST" || "$TLS_HOST" == "<tls-host>" ]]; then
    echo "Error: TLS_HOST is required; the registry must be exposed over TLS." >&2
    exit 2
fi
if [[ -z "$CERT_MANAGER_CLUSTER_ISSUER" || "$CERT_MANAGER_CLUSTER_ISSUER" == "<cluster-issuer>" ]]; then
    echo "Error: CERT_MANAGER_CLUSTER_ISSUER is required; the registry must be exposed over TLS." >&2
    exit 2
fi

# The namespace must be provisioned by an administrator. Keep every operation
# namespace-scoped so this setup does not require cluster-wide permissions.
if ! kubectl get pods >/dev/null; then
    echo "Error: namespace '$NS' must already exist and be accessible." >&2
    exit 1
fi

if ! command -v helm >/dev/null 2>&1; then
    echo "Error: helm is required to deploy the Docker Build Factory." >&2
    exit 1
fi

echo "═══════════════════════════════════════════════════════"
echo "  Docker Build Factory — Setup"
echo "═══════════════════════════════════════════════════════"
echo ""
echo "  Namespace:  $NS"
echo "  Pod:        $POD"
echo "  Registry:   $REGISTRY"
echo "  Registry TLS: https://$TLS_HOST (ClusterIssuer: $CERT_MANAGER_CLUSTER_ISSUER)"
echo ""

# ── 1. Deploy the Helm release ─────────────────────────────────────────────

echo "→ Deploying Docker build pod and registry with Helm..."
# Adopt resources created by releases older than the Helm chart. Missing
# resources are expected on a clean install. These metadata-only operations are
# safe to repeat and prevent Helm from rejecting the migration.
for resource in pod/docker-build deployment/registry service/registry; do
    if kubectl get "$resource" >/dev/null 2>&1; then
        kubectl label "$resource" app.kubernetes.io/managed-by=Helm --overwrite
        kubectl annotate "$resource" \
            meta.helm.sh/release-name=docker-build \
            "meta.helm.sh/release-namespace=$NS" \
            --overwrite
    fi
done
helm_args=(
    upgrade --install docker-build "$CHART_DIR"
    --namespace "$NS"
    --wait
    --timeout 2m
)
helm_args+=(
    --set-string "ingress.host=$TLS_HOST"
    --set-string "certManager.clusterIssuer=$CERT_MANAGER_CLUSTER_ISSUER"
)
helm "${helm_args[@]}"

# Helm starts both workloads before waiting. Keep explicit checks to provide a
# stable readiness contract to callers of this script.
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
