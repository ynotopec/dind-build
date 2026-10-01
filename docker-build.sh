#!/usr/bin/env bash
# docker-build.sh — Build Docker images from inside K8s using a Docker build pod.
# Usage: ./docker-build.sh IMAGE_NAME [BUILD_CONTEXT_DIR]
#   IMAGE_NAME    : full image name (e.g. myapp:latest)
#   BUILD_CONTEXT : directory containing the Dockerfile (default: .)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NS="${DOCKER_BUILD_NAMESPACE:-demo1}"
POD_NAME="docker-build"
REGISTRY_HOST="registry:5000"

image_name="${1:?Usage: docker-build.sh IMAGE_NAME [BUILD_CONTEXT_DIR]}"
build_context="${2:-.}"

# Fail locally before incurring any Kubernetes round trips.
if [[ ! -f "$build_context/Dockerfile" ]]; then
    echo "[✗] No Dockerfile found in $build_context" >&2
    exit 1
fi

kubectl() { command kubectl -n "$NS" "$@"; }

# 1. Deploy pod (idempotent, only if it doesn't exist)
if kubectl get pod "$POD_NAME" &>/dev/null; then
    echo "[✓] Pod $POD_NAME already exists."
else
    echo "[→] Deploying Docker build pod to namespace $NS..."
    kubectl apply -f "$SCRIPT_DIR/docker-build-pod.yaml"
fi
echo "[→] Waiting for pod and Docker daemon to be ready..."
kubectl wait pod/"$POD_NAME" --for=condition=ready --timeout=60s
echo "[✓] Pod ready."

# Keep Docker's layer cache by default. Pruning before every build makes repeat
# builds slower; constrained environments can opt in explicitly.
if [[ "${DOCKER_BUILD_PRUNE_BEFORE_BUILD:-false}" == "true" ]]; then
    echo "[→] Pruning unused Docker data..."
    kubectl exec "$POD_NAME" -- docker system prune -f &>/dev/null
fi

# Stream the context directly instead of creating a local tarball and then
# making kubectl cp package that tarball a second time. A unique remote
# directory also allows concurrent builds.
BUILD_DIR="$(kubectl exec "$POD_NAME" -- mktemp -d /tmp/docker-build.XXXXXX)"
cleanup() {
    kubectl exec "$POD_NAME" -- rm -rf -- "$BUILD_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "[→] Copying build context to pod..."
tar -C "$build_context" -cf - . | kubectl exec -i "$POD_NAME" -- tar -C "$BUILD_DIR" -xf -

# Build while retaining daemon-side layers for low-latency repeat builds.
echo "[→] Building $image_name from $BUILD_DIR ..."
kubectl exec "$POD_NAME" -- docker build -t "$image_name" "$BUILD_DIR"

# 6. Verify
echo "[→] Verifying image..."
kubectl exec "$POD_NAME" -- docker images "$image_name"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  Build complete: $image_name"
echo "  To push:  kubectl -n $NS exec $POD_NAME -- docker push $REGISTRY_HOST/$image_name"
echo "  To run:   kubectl -n $NS exec $POD_NAME -- docker run --rm $image_name"
echo "═══════════════════════════════════════════════════"
