import importlib.util
import inspect
import subprocess
import unittest
from pathlib import Path
from unittest.mock import call, patch


MODULE_PATH = Path(__file__).parents[1] / "mcp" / "dind-mcp-server.py"
SPEC = importlib.util.spec_from_file_location("dind_mcp_server", MODULE_PATH)
SERVER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SERVER)


class KubectlTests(unittest.TestCase):
    @patch.object(SERVER.subprocess, "run")
    def test_run_kubectl_uses_argument_list_and_timeout(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, " ready \n", "")

        result = SERVER.run_kubectl(["get", "pod", "dind-build"], timeout=9)

        self.assertEqual(result, "ready")
        run.assert_called_once_with(
            ["kubectl", "-n", SERVER.NS, "get", "pod", "dind-build"],
            capture_output=True,
            text=True,
            timeout=9,
            check=False,
        )

    @patch.object(SERVER.subprocess, "run")
    def test_run_kubectl_reports_timeout(self, run):
        run.side_effect = subprocess.TimeoutExpired("kubectl", 3)

        with self.assertRaisesRegex(RuntimeError, "timed out after 3 seconds"):
            SERVER.run_kubectl(["get", "pod", "dind-build"], timeout=3)


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


class HttpSecurityTests(unittest.TestCase):
    def test_http_binds_to_loopback_by_default(self):
        default_host = inspect.signature(SERVER.run_http).parameters["host"].default
        self.assertEqual(default_host, "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
