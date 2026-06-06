"""Content tests for the SonarQube + sonar-scanner + sonar-autoscan
services in docker-compose.yml.

The Edit tool happily writes anything; these tests catch the kinds of
mistakes that have already bitten us during this session:

  - `working_dir: /tmp/sonar-src` was a permission trap because Docker
    creates the directory as root before the scanner-cli user (uid 1000)
    can write into it. The bash command must `cd /tmp/sonar-src`
    instead.
  - `wget` is not in the sonar-scanner-cli image. The wait loop must use
    `curl`.
  - YAML `>` fold turns a multi-line `mkdir -p\n  /tmp/a\n  /tmp/b\n`
    with deeper indentation on the args into two separate commands —
    one with no args. mkdir must stay on a single line.
  - SonarQube moved from Mint to Dell on 2026-06-05
    (docs/specs/fr-mint-quality-tool-placement.md). Both `sonarqube`
    and `sonar-autoscan` now carry the `dell-quality` profile so a
    default `docker compose up` on Windows starts neither. Because the
    dependent (`sonar-autoscan`) is gated by the same profile as its
    dependency (`sonarqube`), the default config stays valid — Compose
    only enforces a `depends_on` target when the dependent itself is
    active. The manual `sonar-scanner` no longer declares `depends_on`
    on sonarqube; it reaches Mint over the network via SONAR_HOST_URL.

These tests would have caught each bug in seconds.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from django.test import SimpleTestCase


REPO_ROOT = Path("/repo")
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"


def _load_compose() -> dict:
    with COMPOSE_PATH.open() as fh:
        return yaml.safe_load(fh)


class SonarqubeServiceDellQualityTests(SimpleTestCase):
    """`sonarqube` runs on Dell, gated behind the
    `dell-quality` profile so a default `docker compose up` on Windows
    does not start it."""

    def setUp(self) -> None:
        self.compose = _load_compose()
        self.services = self.compose["services"]

    def test_sonarqube_service_exists(self) -> None:
        self.assertIn("sonarqube", self.services)

    def test_sonarqube_gated_to_dell_quality_profile(self) -> None:
        sonarqube = self.services["sonarqube"]
        self.assertIn("profiles", sonarqube, (
            "sonarqube must carry the dell-quality profile so it does not "
            "start on Windows; Dell runs it via start-dell-sonar-tools.ps1."
        ))
        self.assertIn("dell-quality", sonarqube["profiles"])

    def test_sonarqube_can_bind_to_dell_lan(self) -> None:
        sonarqube = self.services["sonarqube"]
        self.assertIn("${SONAR_BIND_ADDR:-127.0.0.1}:9000:9000", sonarqube["ports"])

    def test_sonarqube_has_restart_policy(self) -> None:
        sonarqube = self.services["sonarqube"]
        self.assertEqual(sonarqube.get("restart"), "unless-stopped")


class SonarScannerServiceTests(SimpleTestCase):
    """The one-shot `sonar-scanner` service runs on Dell (with the
    SonarQube server) via the dell-quality profile, and must not regress to a
    broken working_dir."""

    def setUp(self) -> None:
        self.compose = _load_compose()
        self.scanner = self.compose["services"]["sonar-scanner"]

    def test_one_shot_scanner_gated_to_dell_quality_profile(self) -> None:
        self.assertIn("profiles", self.scanner)
        self.assertIn("dell-quality", self.scanner["profiles"])

    def test_no_working_dir_trap(self) -> None:
        """`working_dir: /tmp/sonar-src` would re-introduce the perm bug."""
        self.assertNotEqual(
            self.scanner.get("working_dir"), "/tmp/sonar-src",
            "working_dir creates /tmp/sonar-src as root before the "
            "scanner-cli user can write into it — use `cd` inside the "
            "script instead."
        )

    def test_script_cds_into_staging_dir(self) -> None:
        script = " ".join(self.scanner["command"])
        self.assertIn("cd /tmp/sonar-src", script,
                      "scanner must cd into /tmp/sonar-src before running")


class SonarAutoscanServiceTests(SimpleTestCase):
    """The Dell-hosted `sonar-autoscan` service — every sanity check the
    runtime bugs taught us, encoded as a test."""

    def setUp(self) -> None:
        self.compose = _load_compose()
        self.autoscan = self.compose["services"]["sonar-autoscan"]
        # The YAML `command` is a list with a single folded scalar element.
        self.script = " ".join(self.autoscan["command"])

    # ── smoke ──────────────────────────────────────────────────────
    def test_smoke_service_is_defined(self) -> None:
        self.assertIn("image", self.autoscan)
        self.assertEqual(self.autoscan["image"],
                         "sonarsource/sonar-scanner-cli:latest")

    def test_smoke_gated_to_mint_quality_profile(self) -> None:
        self.assertIn("profiles", self.autoscan)
        self.assertIn("dell-quality", self.autoscan["profiles"])

    def test_smoke_restart_policy_survives_reboots(self) -> None:
        self.assertEqual(self.autoscan.get("restart"), "unless-stopped")

    def test_smoke_depends_on_sonarqube(self) -> None:
        depends = self.autoscan.get("depends_on", {})
        self.assertIn("sonarqube", depends,
                      "autoscan must wait for sonarqube to start")

    # ── edge cases ─────────────────────────────────────────────────
    def test_edge_case_uses_curl_not_wget(self) -> None:
        """wget is not in the sonar-scanner-cli image — caused a stuck
        wait loop during session debugging."""
        self.assertIn("curl ", self.script)
        self.assertNotIn("wget ", self.script,
                         "wget is not available in scanner-cli image")

    def test_edge_case_mkdir_args_on_one_line(self) -> None:
        """YAML `>` fold splits `mkdir -p` from its args when args are
        indented deeper — turns it into `mkdir -p\n` (no args) which
        fails with `missing operand`. Keep mkdir args on one line."""
        self.assertIn(
            "mkdir -p /tmp/sonar-src/backend /tmp/sonar-src/frontend",
            self.script,
            "mkdir args must stay on one line after YAML folding",
        )

    def test_edge_case_interval_zero_idles_loop(self) -> None:
        """`SONAR_AUTOSCAN_INTERVAL_SECONDS=0` lets operators disable
        the loop without removing the service."""
        self.assertIn("INTERVAL", self.script)
        self.assertIn("= \"0\"", self.script,
                      "script must branch on INTERVAL == 0")
        self.assertIn("auto-scan disabled", self.script.lower(),
                      "must log a disabled state for visibility")

    def test_edge_case_failed_scan_does_not_kill_loop(self) -> None:
        """A scanner crash must not exit the container — the next loop
        cycle should retry. Look for `|| echo` fallback after the scan."""
        self.assertIn("scan failed, will retry next cycle", self.script)

    # ── resource release ───────────────────────────────────────────
    def test_resource_release_temp_dir_purged_each_loop(self) -> None:
        """`rm -rf /tmp/sonar-src` at the top of each loop iteration
        prevents disk leaks across hours of scans."""
        # The string appears twice in the script (the wait line + the
        # loop body). Counting matters: zero would be a bug.
        self.assertGreaterEqual(self.script.count("rm -rf /tmp/sonar-src"), 1)

    # ── latency ────────────────────────────────────────────────────
    def test_latency_interval_is_documented_and_default_30min(self) -> None:
        """Default 1800s = 30 min is the documented cadence. A regression
        to 0 or to a tiny value would be a runtime cost regression."""
        env = self.autoscan["environment"]
        # Compose substitutes `${SONAR_AUTOSCAN_INTERVAL_SECONDS:-1800}`
        # → "1800" at render time, but the raw YAML still contains the
        # default after the dash. Check the raw script.
        self.assertIn("${SONAR_AUTOSCAN_INTERVAL_SECONDS:-1800}",
                      env["SONAR_AUTOSCAN_INTERVAL_SECONDS"])

    # ── e2e ────────────────────────────────────────────────────────
    def test_e2e_passes_through_required_env(self) -> None:
        env = self.autoscan["environment"]
        for key in ("SONAR_HOST_URL", "SONAR_TOKEN",
                    "SONAR_AUTOSCAN_INTERVAL_SECONDS"):
            self.assertIn(key, env, f"{key} must be passed to autoscan")

    def test_e2e_mounts_repo_for_scanner(self) -> None:
        volumes = self.autoscan["volumes"]
        # Repo bind-mount (read-only is fine, scanner only reads)
        repo_mounts = [v for v in volumes if v.startswith(".:") or v.startswith("./:")]
        self.assertTrue(repo_mounts, "autoscan must bind-mount the repo")
        # First repo mount must be read-only for safety
        self.assertTrue(any(":ro" in v for v in repo_mounts),
                        "repo mount should be :ro (scanner is read-only)")

    def test_e2e_writes_to_shared_scanner_cache(self) -> None:
        """Both sonar-scanner and sonar-autoscan share the
        sonar_scanner_cache volume so the analyzer cache is reused
        instead of redownloaded each run."""
        volumes = self.autoscan["volumes"]
        cache_mounts = [v for v in volumes if "sonar_scanner_cache" in v]
        self.assertTrue(cache_mounts)
