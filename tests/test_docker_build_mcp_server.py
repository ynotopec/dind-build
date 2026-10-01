import importlib.util
import inspect
import subprocess
import unittest
from pathlib import Path
from unittest.mock import call, patch


MODULE_PATH = Path(__file__).parents[1] / "mcp" / "docker-build-mcp-server.py"
SPEC = importlib.util.spec_from_file_location("docker_build_mcp_server", MODULE_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class BrandingTests(unittest.TestCase):
    def test_uses_docker_build_resource_and_tool_names(self):
        self.assertEqual(SERVER.POD, "docker-build")
        self.assertEqual(
            SERVER.TOOL_NAMES,
            [
                "docker_build",
                "docker_push",
                "docker_pull",
                "docker_run",
                "docker_list_images",
                "docker_list_registry",
                "docker_cleanup",
            ],
        )


class KubectlTests(unittest.TestCase):
    @patch.object(SERVER, "NS", None)
    def test_run_kubectl_requires_namespace(self):
        with self.assertRaisesRegex(RuntimeError, "KUBE_NAMESPACE must be set"):
            SERVER.run_kubectl(["get", "pods"])

    @patch.object(SERVER, "NS", "test-namespace")
    @patch.object(SERVER.subprocess, "run")
    def test_run_kubectl_uses_argument_list_and_timeout(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, " ready \n", "")

        result = SERVER.run_kubectl(["get", "pod", "docker-build"], timeout=9)

        self.assertEqual(result, "ready")
        run.assert_called_once_with(
            [SERVER.find_kubectl(), "-n", SERVER.NS, "get", "pod", "docker-build"],
            capture_output=True,
            text=True,
            timeout=9,
            check=False,
        )

    @patch.object(SERVER, "NS", "test-namespace")
    @patch.object(SERVER.subprocess, "run")
    def test_run_kubectl_reports_timeout(self, run):
        run.side_effect = subprocess.TimeoutExpired("kubectl", 3)

        with self.assertRaisesRegex(RuntimeError, "timed out after 3 seconds"):
            SERVER.run_kubectl(["get", "pod", "docker-build"], timeout=3)


class FindKubectlTests(unittest.TestCase):
    def test_find_kubectl_prefers_path_lookup(self):
        with patch.object(SERVER.shutil, "which", return_value="/usr/bin/kubectl"):
            self.assertEqual(SERVER.find_kubectl(), "/usr/bin/kubectl")

    def test_find_kubectl_falls_back_to_candidate_dirs(self):
        with patch.object(SERVER.shutil, "which", return_value=None):
            with patch.object(SERVER.os.path, "isfile", return_value=False), \
                 patch.object(SERVER.os, "access", return_value=False):
                # No candidate exists: return the bare command so subprocess
                # raises the usual FileNotFoundError.
                self.assertEqual(SERVER.find_kubectl(), "kubectl")

    def test_run_kubectl_resolves_kubectl_path(self):
        with patch.object(SERVER, "find_kubectl", return_value="/opt/kubectl"), \
             patch.object(SERVER, "NS", "test-namespace"), \
             patch.object(SERVER.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "ok", "")
            SERVER.run_kubectl(["get", "pods"])
            self.assertEqual(run.call_args.args[0][0], "/opt/kubectl")


class EnvFileTests(unittest.TestCase):
    def test_env_file_is_loaded_from_repo_root(self):
        env_path = Path(SERVER.__file__).parents[1] / ".env"
        if not env_path.exists():
            self.skipTest("no .env file present")
        # If KUBE_NAMESPACE exists in .env, the module must have picked it up
        # (setdefault semantics: pre-existing env vars win).
        import os as _os
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                key = key.strip().lstrip("export ")
                val = val.strip().strip('"').strip("'")
                expected = _os.environ.get(key, val)
                self.assertEqual(SERVER.os.environ.get(key), expected)


class ReadinessTests(unittest.TestCase):
    @patch.object(SERVER, "run_kubectl", return_value="True")
    def test_ensure_pod_checks_ready_condition(self, run_kubectl):
        self.assertTrue(SERVER.ensure_pod())
        self.assertIn("conditions", run_kubectl.call_args.args[0][-1])

    @patch.object(SERVER.time, "sleep")
    @patch.object(SERVER, "run_kubectl")
    def test_ensure_dockerd_retries_without_restarting_daemon(self, run_kubectl, sleep):
        run_kubectl.side_effect = [RuntimeError("not ready"), "docker info"]

        SERVER.ensure_dockerd()

        self.assertEqual(
            run_kubectl.call_args_list,
            [
                call(
                    ["exec", SERVER.POD, "--", "docker", "info"],
                    timeout=SERVER.DOCKER_INFO_TIMEOUT_SECONDS,
                ),
                call(
                    ["exec", SERVER.POD, "--", "docker", "info"],
                    timeout=SERVER.DOCKER_INFO_TIMEOUT_SECONDS,
                ),
            ],
        )
        sleep.assert_called_once_with(1)


class ImageNameTests(unittest.TestCase):
    def test_accepts_namespaced_image_with_registry_and_tag(self):
        self.assertEqual(
            SERVER.validate_image_name("registry:5000/team/app:v1.2"),
            "registry:5000/team/app:v1.2",
        )

    def test_rejects_path_traversal_and_uppercase_repository(self):
        for image_name in ("../../etc:latest", "Team/App:latest", "app@sha256:bad"):
            with self.subTest(image_name=image_name):
                with self.assertRaises(ValueError):
                    SERVER.validate_image_name(image_name)

    @patch.object(SERVER, "ensure_dockerd")
    def test_all_image_tools_reject_invalid_names_before_kubectl(self, ensure_dockerd):
        invalid_calls = (
            (SERVER._docker_build, ("../../build:latest",)),
            (SERVER._docker_push, ("../../push:latest",)),
            (SERVER._docker_pull, ("../../pull:latest",)),
            (SERVER._docker_run, ("../../run:latest",)),
        )

        for tool, args in invalid_calls:
            with self.subTest(tool=tool.__name__):
                with self.assertRaises(ValueError):
                    tool(*args)

        ensure_dockerd.assert_not_called()

    @patch.object(SERVER, "ensure_dockerd")
    def test_push_and_pull_reject_invalid_registry_before_kubectl(self, ensure_dockerd):
        for tool in (SERVER._docker_push, SERVER._docker_pull):
            with self.subTest(tool=tool.__name__):
                with self.assertRaises(ValueError):
                    tool("team/app:v1", registry_url="bad registry")

        ensure_dockerd.assert_not_called()


class HttpSecurityTests(unittest.TestCase):
    def test_http_binds_to_loopback_by_default(self):
        default_host = inspect.signature(SERVER.run_http).parameters["host"].default
        self.assertEqual(default_host, "127.0.0.1")


class HttpAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    async def test_static_token_verifier_accepts_only_configured_token(self):
        verifier = SERVER.StaticTokenVerifier("expected-token")

        accepted = await verifier.verify_token("expected-token")
        rejected = await verifier.verify_token("other-token")

        self.assertEqual(accepted.client_id, "mcp-client")
        self.assertIsNone(rejected)

    async def test_http_transport_requires_api_token(self):
        with patch.dict(SERVER.os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "MCP_API_TOKEN must be set"):
                await SERVER.run_http()


if __name__ == "__main__":
    unittest.main()
