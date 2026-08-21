#!/home/ai-agent/.hermes/hermes-agent/venv/bin/python3
"""
DinD Build Factory MCP Server — dual transport.

  Stdio   → for Hermes Agent (python3 dind-mcp-server.py)
  HTTP    → for Open WebUI (python3 dind-mcp-server.py --http [--port 8080])

Open WebUI configuration:
  Admin Settings → Integrations → + Add Server → Type: MCP (Streamable HTTP)
  Server URL: http://<server>:<port>/mcp

K8s config:
  export KUBE_NAMESPACE=demo1   # default: demo1
"""

import argparse
import asyncio
import subprocess
import sys
import os

from mcp.server.fastmcp import FastMCP

# ── K8s config ──────────────────────────────────────────────────────────────

NS = os.environ.get("KUBE_NAMESPACE", os.environ.get("DIND_NAMESPACE", "demo1"))
POD = "dind-build"
REGISTRY = "registry:5000"


# ── Helpers ─────────────────────────────────────────────────────────────────

def run_kubectl(args: list[str]) -> str:
    cmd = ["kubectl", "-n", NS] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return result.stdout.strip() or result.stderr.strip()


def ensure_pod() -> bool:
    status = run_kubectl(["get", "pod", POD, "-o", "jsonpath={.status.phase}"])
    return status == "Running"


def ensure_dockerd():
    run_kubectl(["exec", POD, "--", "sh", "-c",
                 "pkill dockerd 2>/dev/null || true; dockerd --insecure-registry registry:5000 &>/var/log/dockerd.log &"])
    import time
    for _ in range(10):
        result = run_kubectl(["exec", POD, "--", "sh", "-c",
                              "docker info >/dev/null 2>&1 && echo OK || echo FAIL"])
        if "OK" in result:
            return
        time.sleep(2)


# ── Stdio (Hermes Agent) ────────────────────────────────────────────────────

async def run_stdio():
    server = FastMCP("dind-build-factory")

    @server.tool()
    def dind_build(image_name: str, dockerfile_content: str = "FROM alpine:3.19\nRUN echo 'Hello'\nCMD [\"echo\", \"Hello\"]") -> str:
        """Build a Docker image inside the K8s DinD pod."""
        if not ensure_pod():
            raise RuntimeError("DinD pod not running. Deploy: kubectl apply -f dind-pod.yaml")
        ensure_dockerd()
        cmd = (
            f"mkdir -p /tmp/dind-build && cd /tmp/dind-build && "
            f"cat > Dockerfile << 'DEOF'\n{dockerfile_content}\nDEOF\n"
            f"docker build -t {image_name} /tmp/dind-build"
        )
        result = run_kubectl(["exec", POD, "--", "sh", "-c", cmd])
        return f"# Build result for {image_name}\n\n```\n{result}\n```"

    @server.tool()
    def dind_push(image_name: str, registry_url: str = REGISTRY) -> str:
        """Push an image to the local K8s registry (registry:5000)."""
        tagged = f"{registry_url}/{image_name}"
        ensure_dockerd()
        run_kubectl(["exec", POD, "--", "sh", "-c", f"docker tag {image_name} {tagged}"])
        result = run_kubectl(["exec", POD, "--", "sh", "-c", f"docker push {tagged}"])
        return f"# Push result for {tagged}\n\n```\n{result}\n```"

    @server.tool()
    def dind_pull(image_name: str, registry_url: str = REGISTRY) -> str:
        """Pull an image from the local K8s registry."""
        full_image = f"{registry_url}/{image_name}"
        ensure_dockerd()
        result = run_kubectl(["exec", POD, "--", "sh", "-c", f"docker pull {full_image}"])
        return f"# Pull result for {full_image}\n\n```\n{result}\n```"

    @server.tool()
    def dind_run(image_name_with_registry: str, command: str = "") -> str:
        """Run a container from the K8s registry."""
        ensure_dockerd()
        cmd_str = f"docker run --rm {image_name_with_registry} {command}" if command else f"docker run --rm {image_name_with_registry}"
        result = run_kubectl(["exec", POD, "--", "sh", "-c", cmd_str])
        return f"# Run result for {image_name_with_registry}\n\n```\n{result}\n```"

    @server.tool()
    def dind_list_images() -> str:
        """List all Docker images stored in the DinD pod."""
        result = run_kubectl(["exec", POD, "--", "docker", "images"])
        return f"# Docker images in DinD pod\n\nNamespace: {NS}\nPod: {POD}\n\n```\n{result}\n```"

    @server.tool()
    def dind_list_registry() -> str:
        """List all images stored in the K8s registry."""
        catalog = run_kubectl(["exec", POD, "--", "sh", "-c",
                              "wget -q -O- http://registry:5000/v2/_catalog"])
        return f"# Images in K8s registry\n\n```\n{catalog}\n```"

    @server.tool()
    def dind_cleanup() -> str:
        """Prune all unused Docker images from the DinD pod to free space."""
        result = run_kubectl(["exec", POD, "--", "docker", "system", "prune", "-f"])
        return f"# Cleanup done\n\nAll unused images pruned:\n```\n{result}\n```"

    print(f"DinD Build Factory MCP Server (stdio)", file=sys.stderr)
    print(f"Namespace: {NS}  Tools: dind_build, dind_push, dind_pull, dind_run, dind_list_images, dind_list_registry, dind_cleanup", file=sys.stderr)

    await server.run_stdio_async()


# ── HTTP (Open WebUI — Streamable HTTP, stateless mode) ────────────────────

async def run_http(port: int = 8080):
    server = FastMCP(
        "dind-build-factory",
        host="0.0.0.0",
        port=port,
        streamable_http_path="/mcp",
        json_response=True,
        stateless_http=True,
    )

    @server.tool()
    def dind_build(image_name: str, dockerfile_content: str = "FROM alpine:3.19\nRUN echo 'Hello'\nCMD [\"echo\", \"Hello\"]") -> str:
        """Build a Docker image inside the K8s DinD pod."""
        if not ensure_pod():
            raise RuntimeError("DinD pod not running. Deploy: kubectl apply -f dind-pod.yaml")
        ensure_dockerd()
        cmd = (
            f"mkdir -p /tmp/dind-build && cd /tmp/dind-build && "
            f"cat > Dockerfile << 'DEOF'\n{dockerfile_content}\nDEOF\n"
            f"docker build -t {image_name} /tmp/dind-build"
        )
        result = run_kubectl(["exec", POD, "--", "sh", "-c", cmd])
        return f"# Build result for {image_name}\n\n```\n{result}\n```"

    @server.tool()
    def dind_push(image_name: str, registry_url: str = REGISTRY) -> str:
        """Push an image to the local K8s registry (registry:5000)."""
        tagged = f"{registry_url}/{image_name}"
        ensure_dockerd()
        run_kubectl(["exec", POD, "--", "sh", "-c", f"docker tag {image_name} {tagged}"])
        result = run_kubectl(["exec", POD, "--", "sh", "-c", f"docker push {tagged}"])
        return f"# Push result for {tagged}\n\n```\n{result}\n```"

    @server.tool()
    def dind_pull(image_name: str, registry_url: str = REGISTRY) -> str:
        """Pull an image from the local K8s registry."""
        full_image = f"{registry_url}/{image_name}"
        ensure_dockerd()
        result = run_kubectl(["exec", POD, "--", "sh", "-c", f"docker pull {full_image}"])
        return f"# Pull result for {full_image}\n\n```\n{result}\n```"

    @server.tool()
    def dind_run(image_name_with_registry: str, command: str = "") -> str:
        """Run a container from the K8s registry."""
        ensure_dockerd()
        cmd_str = f"docker run --rm {image_name_with_registry} {command}" if command else f"docker run --rm {image_name_with_registry}"
        result = run_kubectl(["exec", POD, "--", "sh", "-c", cmd_str])
        return f"# Run result for {image_name_with_registry}\n\n```\n{result}\n```"

    @server.tool()
    def dind_list_images() -> str:
        """List all Docker images stored in the DinD pod."""
        result = run_kubectl(["exec", POD, "--", "docker", "images"])
        return f"# Docker images in DinD pod\n\nNamespace: {NS}\nPod: {POD}\n\n```\n{result}\n```"

    @server.tool()
    def dind_list_registry() -> str:
        """List all images stored in the K8s registry."""
        catalog = run_kubectl(["exec", POD, "--", "sh", "-c",
                              "wget -q -O- http://registry:5000/v2/_catalog"])
        return f"# Images in K8s registry\n\n```\n{catalog}\n```"

    @server.tool()
    def dind_cleanup() -> str:
        """Prune all unused Docker images from the DinD pod to free space."""
        result = run_kubectl(["exec", POD, "--", "docker", "system", "prune", "-f"])
        return f"# Cleanup done\n\nAll unused images pruned:\n```\n{result}\n```"

    print(f"DinD Build Factory MCP Server (HTTP — stateless)", file=sys.stderr)
    print(f"Namespace: {NS}  Tools: dind_build, dind_push, dind_pull, dind_run, dind_list_images, dind_list_registry, dind_cleanup", file=sys.stderr)
    print(f"URL: http://0.0.0.0:{port}/mcp", file=sys.stderr)

    await server.run_streamable_http_async()


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="DinD Build Factory MCP Server")
    parser.add_argument("--http", action="store_true", help="Run HTTP mode (for Open WebUI)")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port (default: 8080)")
    args = parser.parse_args()

    if args.http:
        await run_http(args.port)
    else:
        await run_stdio()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Server stopped.")
