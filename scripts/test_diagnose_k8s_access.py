"""Tests for the KUBE PLAN Kubernetes access diagnostic."""

from __future__ import annotations

import subprocess
import unittest

import diagnose_k8s_access as diag


def _completed(args: list[str], returncode: int, stdout: str = "", stderr: str = ""):
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


class DiagnoseK8sAccessTests(unittest.TestCase):
    def test_when_all_probes_pass_then_diagnosis_passes(self) -> None:
        def runner(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
            if args[:3] == ["kubectl", "config", "view"]:
                return _completed(args, 0, stdout="https://192.0.2.10:6443\n")
            return _completed(args, 0, stdout="ok\n")

        results = diag.run_diagnostics(runner, tcp_checker=lambda host, port, timeout: None)

        self.assertTrue(all(result.ok for result in results))
        self.assertTrue(all(result.message.startswith("PASS:") for result in results))

    def test_when_node_probe_times_out_then_hint_names_network_and_credentials(self) -> None:
        def runner(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
            if args[:3] == ["kubectl", "get", "nodes"]:
                raise subprocess.TimeoutExpired(args, timeout=timeout)
            if args[:3] == ["kubectl", "config", "view"]:
                return _completed(args, 0, stdout="https://192.0.2.10:6443\n")
            return _completed(args, 0, stdout="ok\n")

        results = diag.run_diagnostics(runner, tcp_checker=lambda host, port, timeout: None)

        self.assertFalse(results[-1].ok)
        self.assertIn("timed out after 60 seconds", results[-1].message)
        self.assertIn("network route", results[-1].message)
        self.assertIn("credentials", results[-1].message)

    def test_when_kubectl_is_missing_then_diagnosis_fails_plainly(self) -> None:
        def runner(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError

        results = diag.run_diagnostics(runner)

        self.assertFalse(results[0].ok)
        self.assertIn("kubectl is not installed", results[0].message)

    def test_when_api_tcp_port_is_closed_then_diagnosis_names_port(self) -> None:
        def runner(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
            if args[:3] == ["kubectl", "config", "view"]:
                return _completed(args, 0, stdout="https://192.0.2.10:6443\n")
            return _completed(args, 0, stdout="ok\n")

        def tcp_checker(host: str, port: int, timeout: int) -> None:
            raise OSError("connection refused")

        results = diag.run_diagnostics(runner, tcp_checker=tcp_checker)

        self.assertFalse(results[2].ok)
        self.assertIn("192.0.2.10:6443", results[2].message)
        self.assertIn("did not accept a connection", results[2].message)


if __name__ == "__main__":
    unittest.main()
