#!/usr/bin/env python3
"""
Docker Build Factory MCP Server — dual transport.

  Stdio   → for MCP clients (python3 docker-build-mcp-server.py)
  HTTP    → for HTTP MCP clients (python3 docker-build-mcp-server.py --http [--port 8000])

Streamable HTTP endpoint: http://<server>:<port>/mcp

K8s config:
  export KUBE_NAMESPACE="<namespace>"
"""

import argparse
import asyncio
import base64
import logging
import os
import re
import secrets
import shlex
import shutil
import subprocess
import time
import uuid

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings

# Preserve the inherited PATH while supporting user-local kubectl installs.
os.environ["PATH"] = f"{os.path.expanduser('~')}/bin:{os.environ.get('PATH', '')}"

# ── K8s config ──────────────────────────────────────────────────────────────

# Load .env from the repository root (the script's parent directory) when the
# launcher does not source it itself. Existing environment variables always win.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
try:
    with open(os.path.join(_REPO_ROOT, ".env")) as _fh:
        for _line in _fh:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _key, _val = _line.split("=", 1)
            _key = _key.strip().lstrip("export ")
            _val = _val.strip().strip('"').strip("'")
            os.environ.setdefault(_key, _val)
except OSError:
    pass

# Look for kubectl in the usual user-local install locations; container images
# frequently install it outside the inherited PATH of the MCP client process.
KUBECTL_CANDIDATE_DIRS = [
    os.path.expanduser("~/.local/bin"),
    os.path.expanduser("~/bin"),
    "/usr/local/bin",
    "/usr/bin",
    "/opt/homebrew/bin",
]


def find_kubectl() -> str:
    """Resolve the kubectl binary path, falling back to common install dirs."""
    found = shutil.which("kubectl")
    if found:
        return found
    for directory in KUBECTL_CANDIDATE_DIRS:
        candidate = os.path.join(directory, "kubectl")
        if os.access(candidate, os.X_OK):
            return candidate
    return "kubectl"


NS = os.environ.get("KUBE_NAMESPACE")
POD = "docker-build"
REGISTRY = "registry:5000"
DOCKER_INFO_ATTEMPTS = 5
DOCKER_INFO_TIMEOUT_SECONDS = 5
IMAGE_NAME_PATTERN = re.compile(
    r"^(?=.{1,255}$)"
    r"(?:[a-z0-9]+(?:[._-][a-z0-9]+)*(?::[0-9]+)?/)*"
    r"[a-z0-9]+(?:[._-][a-z0-9]+)*"
    r"(?::[A-Za-z0-9_][A-Za-z0-9_.-]{0,127})?$"
)

logging.basicConfig(
    level=os.environ.get("DOCKER_BUILD_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s level=%(levelname)s logger=%(name)s message=%(message)s",
)
LOGGER = logging.getLogger("docker-build")


class StaticTokenVerifier:
    """Verify the single bearer token configured for this private MCP API."""

    def __init__(self, token: str):
        self.token = token

    async def verify_token(self, token: str) -> AccessToken | None:
        if not secrets.compare_digest(token, self.token):
            return None
        return AccessToken(token=token, client_id="mcp-client", scopes=[])


# ── Helpers ─────────────────────────────────────────────────────────────────

def run_kubectl(args: list[str], timeout: int = 120) -> str:
    if not NS:
        raise RuntimeError("KUBE_NAMESPACE must be set")
    cmd = [find_kubectl(), "-n", NS] + args
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"kubectl timed out after {timeout} seconds") from exc
    if result.returncode:
        error = result.stderr.strip() or result.stdout.strip() or "(no output)"
        LOGGER.error("kubectl failed status=%d error=%s", result.returncode, error)
        raise RuntimeError(f"kubectl exited with status {result.returncode}: {error}")
    return result.stdout.strip()


def validate_image_name(image_name: str) -> str:
    """Validate a Docker image reference before invoking Docker."""
    if not IMAGE_NAME_PATTERN.fullmatch(image_name):
        raise ValueError(
            "Invalid image name; use lowercase repository components and an "
            "optional Docker tag (for example, registry:5000/team/app:v1)"
        )
    return image_name


def ensure_pod() -> bool:
    try:
        status = run_kubectl([
            "get", "pod", POD, "-o",
            "jsonpath={.status.conditions[?(@.type=='Ready')].status}",
        ])
    except RuntimeError:
        return False
    return status == "True"


def ensure_dockerd():
    """Try bounded Docker checks without restarting the pod-managed daemon."""
    for attempt in range(1, DOCKER_INFO_ATTEMPTS + 1):
        try:
            run_kubectl(
                ["exec", POD, "--", "docker", "info"],
                timeout=DOCKER_INFO_TIMEOUT_SECONDS,
            )
            return
        except RuntimeError:
            if attempt < DOCKER_INFO_ATTEMPTS:
                time.sleep(1)
    raise RuntimeError("Docker daemon is unavailable; inspect the Docker build pod logs")


# ── Tool implementations (pure functions) ──────────────────────────────────

def _docker_build(image_name: str, dockerfile_content: str = "FROM alpine:3.19\nRUN echo 'Hello'\nCMD [\"echo\", \"Hello\"]") -> str:
    """Build a Docker image inside the K8s Docker build pod."""
    validate_image_name(image_name)
    if not ensure_pod():
        raise RuntimeError("Docker build pod not running. Deploy: kubectl apply -f docker-build-pod.yaml")
    ensure_dockerd()
    encoded = base64.b64encode(dockerfile_content.encode()).decode("ascii")
    build_dir = f"/tmp/docker-build-{uuid.uuid4().hex}"
    cmd = (
        f"mkdir -p {shlex.quote(build_dir)} && "
        f"trap 'rm -rf {shlex.quote(build_dir)}' EXIT; "
        f"printf %s {shlex.quote(encoded)} | base64 -d > {shlex.quote(build_dir)}/Dockerfile && "
        f"docker build -t {shlex.quote(image_name)} {shlex.quote(build_dir)}"
    )
    result = run_kubectl(["exec", POD, "--", "sh", "-c", cmd], timeout=600)
    return f"# Build result for {image_name}\n\n```\n{result}\n```"


def _docker_push(image_name: str, registry_url: str = REGISTRY) -> str:
    """Push an image to the local K8s registry (registry:5000)."""
    validate_image_name(image_name)
    tagged = f"{registry_url}/{image_name}"
    validate_image_name(tagged)
    ensure_dockerd()
    run_kubectl(["exec", POD, "--", "docker", "tag", image_name, tagged])
    result = run_kubectl(["exec", POD, "--", "docker", "push", tagged])
    return f"# Push result for {tagged}\n\n```\n{result}\n```"


def _docker_pull(image_name: str, registry_url: str = REGISTRY) -> str:
    """Pull an image from the local K8s registry."""
    validate_image_name(image_name)
    full_image = f"{registry_url}/{image_name}"
    validate_image_name(full_image)
    ensure_dockerd()
    result = run_kubectl(["exec", POD, "--", "docker", "pull", full_image])
    return f"# Pull result for {full_image}\n\n```\n{result}\n```"


def _docker_run(image_name_with_registry: str, command: str = "") -> str:
    """Run a container from the K8s registry."""
    validate_image_name(image_name_with_registry)
    ensure_dockerd()
    cmd_str = f"docker run --rm {shlex.quote(image_name_with_registry)}"
    if command:
        cmd_str += f" sh -c {shlex.quote(command)}"
    result = run_kubectl(["exec", POD, "--", "sh", "-c", cmd_str])
    return f"# Run result for {image_name_with_registry}\n\n```\n{result}\n```"


def _docker_list_images() -> str:
    """List all Docker images stored in the Docker build pod."""
    result = run_kubectl(["exec", POD, "--", "docker", "images"])
    return f"# Docker images in Docker build pod\n\nNamespace: {NS}\nPod: {POD}\n\n```\n{result}\n```"


def _docker_list_registry() -> str:
    """List all images stored in the K8s registry."""
    catalog = run_kubectl(["exec", POD, "--", "sh", "-c",
                          "wget -q -O- http://registry:5000/v2/_catalog"])
    return f"# Images in K8s registry\n\n```\n{catalog}\n```"


def _docker_cleanup() -> str:
    """Prune all unused Docker images from the Docker build pod to free space."""
    result = run_kubectl(["exec", POD, "--", "docker", "system", "prune", "-f"])
    return f"# Cleanup done\n\nAll unused images pruned:\n```\n{result}\n```"


# ── Tool metadata table ───────────────────────────────────────────────────

TOOL_TABLE = {
    "docker_build": {
        "fn": _docker_build,
        "description": "Build a Docker image inside the K8s Docker build pod.",
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
    "docker_push": {
        "fn": _docker_push,
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
    "docker_pull": {
        "fn": _docker_pull,
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
    "docker_run": {
        "fn": _docker_run,
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
    "docker_list_images": {
        "fn": _docker_list_images,
        "description": "List all Docker images stored in the Docker build pod.",
        "params": {"type": "object", "properties": {}}
    },
    "docker_list_registry": {
        "fn": _docker_list_registry,
        "description": "List all images stored in the K8s registry.",
        "params": {"type": "object", "properties": {}}
    },
    "docker_cleanup": {
        "fn": _docker_cleanup,
        "description": "Prune all unused Docker images from the Docker build pod to free space.",
        "params": {"type": "object", "properties": {}}
    }
}

TOOL_NAMES = list(TOOL_TABLE.keys())


def create_server(**settings) -> FastMCP:
    """Create a server using the SDK's documented public API."""
    server = FastMCP("docker-build-factory", **settings)
    for tool_name, tool_def in TOOL_TABLE.items():
        server.add_tool(
            tool_def["fn"], name=tool_name, description=tool_def["description"]
        )
    return server


# ── Stdio transport ────────────────────────────────────────────────────

async def run_stdio():
    server = create_server()

    LOGGER.info("transport=stdio namespace=%s tools=%s", NS, ",".join(TOOL_NAMES))
    await server.run_stdio_async()


# ── HTTP (Streamable HTTP, stateless mode) ────────────────────

async def run_http(host: str = "127.0.0.1", port: int = 8000):
    api_token = os.environ.get("MCP_API_TOKEN")
    if not api_token:
        raise RuntimeError("MCP_API_TOKEN must be set for HTTP transport")
    public_url = os.environ.get("MCP_PUBLIC_URL", f"http://127.0.0.1:{port}").rstrip("/")
    server = create_server(
        host=host,
        port=port,
        streamable_http_path="/mcp",
        stateless_http=True,
        token_verifier=StaticTokenVerifier(api_token),
        auth=AuthSettings(
            issuer_url=public_url,
            resource_server_url=f"{public_url}/mcp",
        ),
    )

    LOGGER.info(
        "transport=http mode=stateless namespace=%s tools=%s url=http://%s:%d/mcp",
        NS,
        ",".join(TOOL_NAMES),
        host,
        port,
    )
    await server.run_streamable_http_async()


# ── Main ─────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description="Docker Build Factory MCP Server")
    parser.add_argument("--http", action="store_true", help="Run in HTTP mode")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="HTTP bind address (default: 127.0.0.1; use an authenticated proxy for remote access)",
    )
    parser.add_argument("--port", type=int, default=8000, help="HTTP port (default: 8000)")
    args = parser.parse_args()

    if args.http:
        await run_http(args.host, args.port)
    else:
        await run_stdio()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        LOGGER.info("server stopped")
