#!/usr/bin/env bash
# dind-build.sh — Build Docker images from inside K8s using DinD pod.
# Usage: ./dind-build.sh IMAGE_NAME [BUILD_CONTEXT_DIR]
#   IMAGE_NAME    : full image name (e.g. ghcr.io/ynotopec/myapp:latest)
#   BUILD_CONTEXT : directory containing the Dockerfile (default: .)
set -euo pipefail

NS="${DIND_NAMESPACE:-demo1}"
POD_NAME="dind-build"
REGISTRY_HOST="registry:5000"

image_name="${1:?Usage: dind-build.sh IMAGE_NAME [BUILD_CONTEXT_DIR]}"
build_context="${2:-.}"

kubectl() { command kubectl -n "$NS" "$@"; }

# 1. Deploy pod (idempotent)
if kubectl get pod "$POD_NAME" &>/dev/null; then
    echo "[✓] Pod $POD_NAME already exists."
else
    echo "[→] Deploying DinD pod to namespace $NS..."
    kubectl apply -f dind-pod.yaml
    echo "[→] Waiting for pod to be ready..."
    kubectl wait pod/dind-build --for=condition=ready --timeout=60s
    echo "[✓] Pod ready."
fi

# 2. Start dockerd with insecure-registry flag
echo "[→] Starting dockerd with insecure registry $REGISTRY_HOST..."
kubectl exec "$POD_NAME" -- sh -c '
echo "[→] Stopping dockerd if running..."
pkill dockerd 2>/dev/null || true
sleep 2

echo "[→] Starting dockerd with insecure registry..."
dockerd --insecure-registry '"$REGISTRY_HOST"' &>/var/log/dockerd.log &

echo "[→] Waiting for dockerd to be ready..."
for i in $(seq 1 15); do
    if docker info >/dev/null 2>&1; then
        echo "[✓] dockerd is ready."
        exit 0
    fi
    sleep 2
done
echo "[✗] dockerd failed to start"
exit 1
'

# 3. Prune old images to free space
echo "[→] Pruning old images..."
kubectl exec "$POD_NAME" -- docker system prune -f &>/dev/null

# 4. Copy build context into the pod using tar
BUILD_DIR="dind-build-tmp"
echo "[→] Copying build context to pod..."
mkdir -p "$BUILD_DIR"
if [ -f "$build_context/Dockerfile" ]; then
    tar cf "/tmp/$BUILD_DIR.tar" -C "$build_context" .
    kubectl cp "/tmp/$BUILD_DIR.tar" "$POD_NAME:/tmp/$BUILD_DIR.tar"
    kubectl exec "$POD_NAME" -- sh -c "mkdir -p /tmp/$BUILD_DIR && tar xf /tmp/$BUILD_DIR.tar -C /tmp/$BUILD_DIR"
    rm -f "/tmp/$BUILD_DIR.tar"
else
    echo "[✗] No Dockerfile found in $build_context"
    rm -rf "$BUILD_DIR"
    exit 1
fi

# 5. Build
echo "[→] Building $image_name from /tmp/$BUILD_DIR ..."
kubectl exec "$POD_NAME" -- docker build -t "$image_name" "/tmp/$BUILD_DIR"

# 6. Verify
echo "[→] Verifying image..."
kubectl exec "$POD_NAME" -- docker images "$image_name"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  Build complete: $image_name"
echo "  To push:  kubectl -n $NS exec $POD_NAME -- docker push $REGISTRY_HOST/$image_name"
echo "  To run:   kubectl -n $NS exec $POD_NAME -- docker run --rm $image_name"
echo "═══════════════════════════════════════════════════"
