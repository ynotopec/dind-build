"""
DinD Build Factory MCP Server — expose Docker build via K8s DinD pod.

Tools available:
  dind_build          Build a Docker image in the DinD pod
  dind_push           Push image to the local K8s registry (registry:5000)
  dind_pull           Pull image from the local K8s registry
  dind_run            Run a container from the local registry
  dind_list_images    List images in the DinD pod
  dind_list_registry  List images in the K8s registry
  dind_cleanup        Prune unused images in the DinD pod

Usage (stdio):
  python dind-mcp-server.py  ← reads JSON-RPC from stdin, writes to stdout
"""

import asyncio
import subprocess
import json
import os
import sys

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool,
    TextContent,
    ListToolsResult,
    CallToolRequestParams,
    CallToolResult,
)

NS = os.environ.get("DIND_NAMESPACE", "demo1")
POD = "dind-build"
REGISTRY = "registry:5000"


# ── helpers ──────────────────────────────────────────────────────────────────

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


# ── tool definitions ─────────────────────────────────────────────────────────

TOOLS = [
    Tool(
        name="dind_build",
        description="Build a Docker image inside the K8s DinD pod",
        inputSchema={
            "type": "object",
            "properties": {
                "image_name": {
                    "type": "string",
                    "description": "Full image name (e.g. myapp:latest)",
                },
                "dockerfile_content": {
                    "type": "string",
                    "description": "Content of the Dockerfile to build",
                },
            },
            "required": ["image_name"],
        },
    ),
    Tool(
        name="dind_push",
        description="Push an image to the local K8s registry (registry:5000)",
        inputSchema={
            "type": "object",
            "properties": {
                "image_name": {
                    "type": "string",
                    "description": "Image name to push (e.g. myapp:latest)",
                },
                "registry_url": {
                    "type": "string",
                    "description": "Registry URL (default: registry:5000)",
                },
            },
            "required": ["image_name"],
        },
    ),
    Tool(
        name="dind_pull",
        description="Pull an image from the local K8s registry",
        inputSchema={
            "type": "object",
            "properties": {
                "image_name": {
                    "type": "string",
                    "description": "Image name to pull (e.g. myapp:latest)",
                },
                "registry_url": {
                    "type": "string",
                    "description": "Registry URL (default: registry:5000)",
                },
            },
            "required": ["image_name"],
        },
    ),
    Tool(
        name="dind_run",
        description="Run a container from the K8s registry",
        inputSchema={
            "type": "object",
            "properties": {
                "image_name_with_registry": {
                    "type": "string",
                    "description": "Full image name (e.g. registry:5000/myapp:latest)",
                },
                "command": {
                    "type": "string",
                    "description": "Optional command to override container CMD",
                },
            },
            "required": ["image_name_with_registry"],
        },
    ),
    Tool(
        name="dind_list_images",
        description="List all Docker images stored in the DinD pod",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="dind_list_registry",
        description="List all images stored in the K8s registry",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="dind_cleanup",
        description="Prune all unused Docker images from the DinD pod to free space",
        inputSchema={"type": "object", "properties": {}},
    ),
]


# ── request handlers ────────────────────────────────────────────────────────

async def list_tools(ctx, params):
    return ListToolsResult(tools=TOOLS)


async def call_tool(ctx, params):
    name = params.name
    arguments = params.arguments or {}

    try:
        if name == "dind_build":
            image_name = arguments.get("image_name", "")
            dockerfile_content = arguments.get(
                "dockerfile_content",
                "FROM alpine:3.19\nRUN echo 'Hello'\nCMD [\"echo\", \"Hello\"]",
            )
            if not ensure_pod():
                raise RuntimeError(
                    "DinD pod is not running. Deploy: kubectl apply -f dind-pod.yaml"
                )
            ensure_dockerd()
            cmd = (
                f"mkdir -p /tmp/dind-build && cd /tmp/dind-build && "
                f"cat > Dockerfile << 'DEOF'\n{dockerfile_content}\nDEOF\n"
                f"docker build -t {image_name} /tmp/dind-build"
            )
            result = run_kubectl(["exec", POD, "--", "sh", "-c", cmd])
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"# Build result for {image_name}\n\n```\n{result}\n```",
                    )
                ]
            )

        elif name == "dind_push":
            image_name = arguments.get("image_name", "")
            registry_url = arguments.get("registry_url", REGISTRY)
            tagged = f"{registry_url}/{image_name}"
            ensure_dockerd()
            run_kubectl(["exec", POD, "--", "sh", "-c", f"docker tag {image_name} {tagged}"])
            result = run_kubectl(["exec", POD, "--", "sh", "-c", f"docker push {tagged}"])
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"# Push result for {tagged}\n\n```\n{result}\n```",
                    )
                ]
            )

        elif name == "dind_pull":
            image_name = arguments.get("image_name", "")
            registry_url = arguments.get("registry_url", REGISTRY)
            full_image = f"{registry_url}/{image_name}"
            ensure_dockerd()
            result = run_kubectl(["exec", POD, "--", "sh", "-c", f"docker pull {full_image}"])
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"# Pull result for {full_image}\n\n```\n{result}\n```",
                    )
                ]
            )

        elif name == "dind_run":
            image_name_with_registry = arguments.get("image_name_with_registry", "")
            command = arguments.get("command", "")
            ensure_dockerd()
            if command:
                cmd_str = f"docker run --rm {image_name_with_registry} {command}"
            else:
                cmd_str = f"docker run --rm {image_name_with_registry}"
            result = run_kubectl(["exec", POD, "--", "sh", "-c", cmd_str])
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"# Run result for {image_name_with_registry}\n\n```\n{result}\n```",
                    )
                ]
            )

        elif name == "dind_list_images":
            result = run_kubectl(["exec", POD, "--", "docker", "images"])
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"# Docker images in DinD pod\n\nNamespace: {NS}\nPod: {POD}\n\n```\n{result}\n```",
                    )
                ]
            )

        elif name == "dind_list_registry":
            catalog = run_kubectl(
                ["exec", POD, "--", "sh", "-c",
                 "wget -q -O- http://registry:5000/v2/_catalog"]
            )
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"# Images in K8s registry\n\n```\n{catalog}\n```",
                    )
                ]
            )

        elif name == "dind_cleanup":
            result = run_kubectl(["exec", POD, "--", "docker", "system", "prune", "-f"])
            return CallToolResult(
                content=[
                    TextContent(
                        type="text",
                        text=f"# Cleanup done\n\nAll unused images pruned:\n```\n{result}\n```",
                    )
                ]
            )

        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Error: {str(e)}")]
        )


# ── main ─────────────────────────────────────────────────────────────────────

async def main():
    # CRITICAL: Pass on_list_tools and on_call_tool to the Server constructor
    # This is what makes the MCP library route requests to our handlers
    app = Server(
        "dind-build-factory",
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )

    print("DinD Build Factory MCP Server v0.1.0", file=sys.stderr)
    print(f"Namespace: {NS}  Pod: {POD}  Registry: {REGISTRY}", file=sys.stderr)
    print("Tools:", file=sys.stderr)
    for t in TOOLS:
        print(f"  {t.name}: {t.description}", file=sys.stderr)
    print(file=sys.stderr)

    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="dind-build-factory",
                server_version="0.1.0",
                capabilities=app.get_capabilities(),
            ),
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
