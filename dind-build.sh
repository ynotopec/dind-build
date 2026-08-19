#!/usr/bin/env bash
# dind-build.sh — Build Docker images from inside K8s using DinD.
# Usage: ./dind-build.sh IMAGE_NAME [BUILD_CONTEXT_DIR]
#   IMAGE_NAME    : full image name (e.g. ghcr.io/ynotopec/myapp:latest)
#   BUILD_CONTEXT : directory containing the Dockerfile (default: .)
set -euo pipefail

NAMESPACE="dind-build-ns"
POD_NAME="dind-build"
DOCKER_IMAGE="docker:24-dind"

image_name="${1:?Usage: dind-build.sh IMAGE_NAME [BUILD_CONTEXT_DIR]}"
build_context="${2:-.}"

kubectl() { command kubectl -n "$NAMESPACE" "$@"; }

# 0. Ensure namespace exists
kubectl get ns "$NAMESPACE" &>/dev/null || kubectl create namespace "$NAMESPACE"

# 1. Deploy pod (idempotent)
if kubectl get pod "$POD_NAME" &>/dev/null; then
    echo "[✓] Pod $POD_NAME already exists."
else
    echo "[→] Deploying DinD pod..."
    cat <<'YAML' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: dind-build
  labels:
    app: dind-build
spec:
  containers:
  - name: docker
    image: docker:24-dind
    command: ["sleep", "3600"]
    securityContext:
      privileged: true
    volumeMounts:
    - name: docker-storage
      mountPath: /var/lib/docker
  volumes:
  - name: docker-storage
    emptyDir:
      sizeLimit: 5Gi
YAML
    echo "[→] Waiting for pod to be ready..."
    kubectl wait pod/dind-build --for=condition=ready --timeout=60s
    echo "[✓] Pod ready."
fi

# 2. Start dockerd if not running
if kubectl exec "$POD_NAME" -- sh -c 'pgrep dockerd >/dev/null 2>&1' &>/dev/null; then
    echo "[✓] dockerd is running."
else
    echo "[→] Starting dockerd..."
    kubectl exec "$POD_NAME" -- sh -c 'dockerd &>/var/log/dockerd.log &'
    echo "[→] Waiting for dockerd..."
    for i in $(seq 1 10); do
        if kubectl exec "$POD_NAME" -- sh -c 'docker info >/dev/null 2>&1' &>/dev/null; then
            echo "[✓] dockerd is ready."
            break
        fi
        sleep 2
    done
    echo "[✓] dockerd is running."
fi

# 3. Prune old images to free space
echo "[→] Pruning old images..."
kubectl exec "$POD_NAME" -- docker system prune -f &>/dev/null

# 4. Build
echo "[→] Building $image_name from $build_context ..."
kubectl exec -it "$POD_NAME" -- docker build -t "$image_name" "$build_context"

# 5. Verify
echo "[→] Verifying image..."
kubectl exec "$POD_NAME" -- docker images "$image_name"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  Build complete: $image_name"
echo "  To push:  kubectl -n $NAMESPACE exec $POD_NAME -- docker push $image_name"
echo "  To run:   kubectl -n $NAMESPACE exec $POD_NAME -- docker run --rm $image_name"
echo "═══════════════════════════════════════════════════"
