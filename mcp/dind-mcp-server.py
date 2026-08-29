#!/usr/bin/env python3
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
import base64
import os
import shlex
import subprocess
import sys

from mcp.server.fastmcp import FastMCP

# ── K8s config ──────────────────────────────────────────────────────────────

NS = os.environ.get("KUBE_NAMESPACE", os.environ.get("DIND_NAMESPACE", "demo1"))
POD = "dind-build"
REGISTRY = "registry:5000"


# ── Helpers ─────────────────────────────────────────────────────────────────

def run_kubectl(args: list[str]) -> str:
    cmd = ["kubectl", "-n", NS] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    output = result.stdout.strip() or result.stderr.strip()
    if result.returncode:
        raise RuntimeError(f"kubectl exited with status {result.returncode}: {output or '(no output)'}")
    return output


def ensure_pod() -> bool:
    try:
        status = run_kubectl(["get", "pod", POD, "-o", "jsonpath={.status.phase}"])
    except RuntimeError:
        return False
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
    raise RuntimeError("Docker daemon did not become ready within 20 seconds")


# ── Tool implementations (pure functions) ──────────────────────────────────

def _dind_build(image_name: str, dockerfile_content: str = "FROM alpine:3.19\nRUN echo 'Hello'\nCMD [\"echo\", \"Hello\"]") -> str:
    """Build a Docker image inside the K8s DinD pod."""
    if not ensure_pod():
        raise RuntimeError("DinD pod not running. Deploy: kubectl apply -f dind-pod.yaml")
    ensure_dockerd()
    encoded = base64.b64encode(dockerfile_content.encode()).decode("ascii")
    cmd = (
        "rm -rf /tmp/dind-build && mkdir -p /tmp/dind-build && "
        f"printf %s {shlex.quote(encoded)} | base64 -d > /tmp/dind-build/Dockerfile && "
        f"docker build -t {shlex.quote(image_name)} /tmp/dind-build"
    )
    result = run_kubectl(["exec", POD, "--", "sh", "-c", cmd])
    return f"# Build result for {image_name}\n\n```\n{result}\n```"


def _dind_push(image_name: str, registry_url: str = REGISTRY) -> str:
    """Push an image to the local K8s registry (registry:5000)."""
    tagged = f"{registry_url}/{image_name}"
    ensure_dockerd()
    run_kubectl(["exec", POD, "--", "docker", "tag", image_name, tagged])
    result = run_kubectl(["exec", POD, "--", "docker", "push", tagged])
    return f"# Push result for {tagged}\n\n```\n{result}\n```"


def _dind_pull(image_name: str, registry_url: str = REGISTRY) -> str:
    """Pull an image from the local K8s registry."""
    full_image = f"{registry_url}/{image_name}"
    ensure_dockerd()
    result = run_kubectl(["exec", POD, "--", "docker", "pull", full_image])
    return f"# Pull result for {full_image}\n\n```\n{result}\n```"


def _dind_run(image_name_with_registry: str, command: str = "") -> str:
    """Run a container from the K8s registry."""
    ensure_dockerd()
    cmd_str = f"docker run --rm {shlex.quote(image_name_with_registry)}"
    if command:
        cmd_str += f" sh -c {shlex.quote(command)}"
    result = run_kubectl(["exec", POD, "--", "sh", "-c", cmd_str])
    return f"# Run result for {image_name_with_registry}\n\n```\n{result}\n```"


def _dind_list_images() -> str:
    """List all Docker images stored in the DinD pod."""
    result = run_kubectl(["exec", POD, "--", "docker", "images"])
    return f"# Docker images in DinD pod\n\nNamespace: {NS}\nPod: {POD}\n\n```\n{result}\n```"


def _dind_list_registry() -> str:
    """List all images stored in the K8s registry."""
    catalog = run_kubectl(["exec", POD, "--", "sh", "-c",
                          "wget -q -O- http://registry:5000/v2/_catalog"])
    return f"# Images in K8s registry\n\n```\n{catalog}\n```"


def _dind_cleanup() -> str:
    """Prune all unused Docker images from the DinD pod to free space."""
    result = run_kubectl(["exec", POD, "--", "docker", "system", "prune", "-f"])
    return f"# Cleanup done\n\nAll unused images pruned:\n```\n{result}\n```"


# ── Tool metadata table ───────────────────────────────────────────────────

TOOL_TABLE = {
    "dind_build": {
        "fn": _dind_build,
        "description": "Build a Docker image inside the K8s DinD pod.",
        "params": {
            "type": "object",
            "properties": {
                "image_name": {"type": "string", "description": "Name of the image to build"},
                "dockerfile_content": {
                    "type": "string",
                    "description": "Dockerfile content",
                    "default": "FROM alpine:3.19\nRUN echo 'Hello'\nCMD [\"echo\", \"Hello\"]"
                }
            },
            "required": ["image_name"]
        }
    },
    "dind_push": {
        "fn": _dind_push,
        "description": "Push an image to the local K8s registry (registry:5000).",
        "params": {
            "type": "object",
            "properties": {
                "image_name": {"type": "string", "description": "Name of the image to push"},
                "registry_url": {"type": "string", "description": "Registry URL", "default": REGISTRY}
            },
            "required": ["image_name"]
        }
    },
    "dind_pull": {
        "fn": _dind_pull,
        "description": "Pull an image from the local K8s registry.",
        "params": {
            "type": "object",
            "properties": {
                "image_name": {"type": "string", "description": "Name of the image to pull"},
                "registry_url": {"type": "string", "description": "Registry URL", "default": REGISTRY}
            },
            "required": ["image_name"]
        }
    },
    "dind_run": {
        "fn": _dind_run,
        "description": "Run a container from the K8s registry.",
        "params": {
            "type": "object",
            "properties": {
                "image_name_with_registry": {"type": "string", "description": "Full image name with registry"},
                "command": {"type": "string", "description": "Command to run inside the container", "default": ""}
            },
            "required": ["image_name_with_registry"]
        }
    },
    "dind_list_images": {
        "fn": _dind_list_images,
        "description": "List all Docker images stored in the DinD pod.",
        "params": {"type": "object", "properties": {}}
    },
    "dind_list_registry": {
        "fn": _dind_list_registry,
        "description": "List all images stored in the K8s registry.",
        "params": {"type": "object", "properties": {}}
    },
    "dind_cleanup": {
        "fn": _dind_cleanup,
        "description": "Prune all unused Docker images from the DinD pod to free space.",
        "params": {"type": "object", "properties": {}}
    }
}

TOOL_NAMES = list(TOOL_TABLE.keys())


def create_server(**settings) -> FastMCP:
    """Create a server using the SDK's documented public API."""
    server = FastMCP("dind-build-factory", **settings)
    for tool_name, tool_def in TOOL_TABLE.items():
        server.add_tool(
            tool_def["fn"], name=tool_name, description=tool_def["description"]
        )
    return server


# ── Stdio (Hermes Agent) ────────────────────────────────────────────────────

async def run_stdio():
    server = create_server()

    print("DinD Build Factory MCP Server (stdio)", file=sys.stderr)
    print(f"Namespace: {NS}  Tools: {', '.join(TOOL_NAMES)}", file=sys.stderr)
    await server.run_stdio_async()


# ── HTTP (Open WebUI — Streamable HTTP, stateless mode) ────────────────────

async def run_http(port: int = 8080):
    server = create_server(
        host="0.0.0.0",
        port=port,
        streamable_http_path="/mcp",
        stateless_http=True,
    )

    print("DinD Build Factory MCP Server (HTTP — stateless)", file=sys.stderr)
    print(f"Namespace: {NS}  Tools: {', '.join(TOOL_NAMES)}", file=sys.stderr)
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
