"""
Hard CI gate that fails if the GlitchTip integration is silently disabled.

Background: the integration was lost previously when an unidentified agent
removed the credentials and the dashboard stopped capturing errors. The blind
spot went unnoticed for weeks. This test enforces the structural guarantees
documented in CLAUDE.md's "ABSOLUTE — Never disable or remove the GlitchTip
integration" rule:

  1. `docker-compose.yml` declares all three GlitchTip services
     (`glitchtip-init`, `glitchtip`, `glitchtip-worker`) at the top level.
  2. None of them are gated behind `profiles: ["debug"]` (default-on).
  3. `glitchtip-init` runs the idempotent CREATE-DATABASE step so a dropped
     `glitchtip` Postgres database is recreated on the next stack boot.
  4. `.env.example` documents every credential the SDK and the sync task
     read at runtime — so a future operator who refreshes their `.env` from
     the example file gets working defaults to fill in.

The test reads only files in the repo (`docker-compose.yml`, `.env.example`)
and does not require Docker, the live stack, or any database. It runs as a
plain `SimpleTestCase` in <100 ms.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from django.test import SimpleTestCase


def _resolve_repo_root() -> Path:
    """Locate docker-compose.yml on host OR inside the backend container.

    On the host, this file lives at `<repo>/backend/apps/audit/...` so the
    repo root is `parents[3]`. Inside the backend container `__file__` is
    `/app/apps/audit/...` because `./backend` is mounted as `/app`; the full
    repo is mounted read-only at `/repo` (set via `REPO_ROOT` env var in
    docker-compose.yml). We try that env var first, then walk parents
    looking for the compose file.
    """
    env_root = os.environ.get("REPO_ROOT")
    if env_root and (Path(env_root) / "docker-compose.yml").exists():
        return Path(env_root)
    here = Path(__file__).resolve()
    for candidate in (here.parents[3], here.parents[2]):
        if (candidate / "docker-compose.yml").exists():
            return candidate
    raise FileNotFoundError("Could not locate repo root (docker-compose.yml).")


REPO_ROOT = _resolve_repo_root()
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"

REQUIRED_SERVICES = (
    "glitchtip-init",
    "glitchtip-migrate",
    "glitchtip",
    "glitchtip-worker",
    "pyroscope",
    "otel-collector",
)
REQUIRED_ENV_KEYS = (
    "ERROR_TRACKING_DSN",
    "GLITCHTIP_DSN",
    "GLITCHTIP_API_URL",
    "GLITCHTIP_API_TOKEN",
    "GLITCHTIP_ORG_SLUG",
    "GLITCHTIP_PROJECT_SLUG",
)


class GlitchtipComposeIntegrityTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        with COMPOSE_PATH.open("r", encoding="utf-8") as fh:
            cls.compose = yaml.safe_load(fh)
        cls.env_example_text = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")

    def test_compose_file_exists_and_parses(self):
        self.assertIsInstance(self.compose, dict)
        self.assertIn("services", self.compose)

    def test_all_three_glitchtip_services_present(self):
        services = self.compose["services"]
        for name in REQUIRED_SERVICES:
            self.assertIn(
                name,
                services,
                msg=(
                    f"docker-compose.yml is missing the `{name}` service. "
                    "See CLAUDE.md ABSOLUTE rule on the GlitchTip integration "
                    "— this service must not be removed."
                ),
            )

    def test_no_profile_gating_on_glitchtip_services(self):
        services = self.compose["services"]
        for name in ("glitchtip", "glitchtip-worker", "pyroscope", "otel-collector"):
            profiles = services[name].get("profiles") or []
            self.assertEqual(
                list(profiles),
                [],
                msg=(
                    f"`{name}` has `profiles: {profiles!r}` set. The integration "
                    "must boot on a default `docker compose up` so its absence "
                    "is visible immediately. Remove the profiles gate."
                ),
            )

    def test_pyroscope_localhost_only_port_binding(self):
        pyroscope = self.compose["services"]["pyroscope"]
        ports = pyroscope.get("ports") or []
        self.assertTrue(
            any("127.0.0.1:" in str(p) for p in ports),
            msg=(
                "`pyroscope` ports must be 127.0.0.1-bound — exposing the "
                "profiling UI to the world is a leak risk. Got: "
                f"{ports!r}"
            ),
        )

    def test_otel_collector_localhost_only_port_binding(self):
        col = self.compose["services"]["otel-collector"]
        ports = col.get("ports") or []
        self.assertTrue(
            ports and all("127.0.0.1:" in str(p) for p in ports),
            msg=(
                "`otel-collector` ports must all be 127.0.0.1-bound. "
                f"Got: {ports!r}"
            ),
        )

    def test_glitchtip_depends_on_migrate(self):
        glitchtip = self.compose["services"]["glitchtip"]
        depends = glitchtip.get("depends_on") or {}
        self.assertIn(
            "glitchtip-migrate",
            depends,
            msg=(
                "`glitchtip` must `depends_on` `glitchtip-migrate` so the DB "
                "schema exists before the dashboard starts. Otherwise every "
                "endpoint returns 500 with `relation does not exist` errors."
            ),
        )
        condition = depends["glitchtip-migrate"].get("condition")
        self.assertEqual(
            condition,
            "service_completed_successfully",
            msg=(
                "`glitchtip` must wait until `glitchtip-migrate` has *finished* "
                "(condition: service_completed_successfully)."
            ),
        )

    def test_migrate_service_runs_run_migrate_script(self):
        migrate = self.compose["services"]["glitchtip-migrate"]
        cmd = migrate.get("command") or ""
        self.assertIn(
            "run-migrate.sh",
            cmd,
            msg=(
                "`glitchtip-migrate` must invoke the GlitchTip image's shipped "
                "migration script (`./bin/run-migrate.sh`). Anything else risks "
                "running the wrong migrations or skipping partition setup."
            ),
        )
        depends = migrate.get("depends_on") or {}
        self.assertIn(
            "glitchtip-init",
            depends,
            msg=(
                "`glitchtip-migrate` must wait for `glitchtip-init` so the DB "
                "exists before migrations attempt to create tables in it."
            ),
        )

    def test_glitchtip_init_creates_database_idempotently(self):
        init = self.compose["services"]["glitchtip-init"]
        cmd = init.get("command") or ""
        self.assertIn(
            "CREATE DATABASE",
            cmd,
            msg=(
                "`glitchtip-init` must run a CREATE DATABASE step. Without it, "
                "a dropped or missing `glitchtip` Postgres DB silently breaks "
                "the dashboard."
            ),
        )
        self.assertIn(
            "glitchtip",
            cmd,
            msg="`glitchtip-init` command must reference the `glitchtip` DB name.",
        )
        self.assertIn(
            "WHERE datname='glitchtip'",
            cmd,
            msg=(
                "`glitchtip-init` must check existence first so it is idempotent "
                "(skips when the DB already exists). Without the existence check "
                "the command errors on every boot after the first."
            ),
        )

    def test_env_example_documents_every_glitchtip_key(self):
        for key in REQUIRED_ENV_KEYS:
            self.assertRegex(
                self.env_example_text,
                rf"(?m)^{key}=",
                msg=(
                    f"`.env.example` is missing a line for `{key}`. Operators "
                    "who refresh `.env` from the example will silently lose "
                    "the integration."
                ),
            )
