"""
Hard CI gate that fails if the SLICE-21 Kubernetes observability manifests
silently lose the GlitchTip integration or break the telemetry wiring.

This is the cluster twin of `tests_glitchtip_compose_integrity.py`. That test
guards the docker-compose stack; this one guards the equivalent Kubernetes
manifests under `k8s/obs/` and `k8s/network/`. It enforces the same structural
guarantees from CLAUDE.md's "ABSOLUTE — Never disable or remove the GlitchTip
integration" rule, expressed in Kubernetes terms:

  1. All FOUR GlitchTip workloads exist — the `glitchtip-init` Job, the
     `glitchtip-migrate` Job, the `glitchtip` web Deployment, and the
     `glitchtip-worker` Deployment.
  2. `glitchtip-init` runs the idempotent CREATE-DATABASE step so a dropped
     `glitchtip` Postgres database is recreated on the next apply.
  3. `glitchtip-migrate` runs GlitchTip's shipped migration script and waits
     for the database to exist first (an init container), enforcing the
     init -> migrate order.
  4. The GlitchTip workloads never blank their connection settings —
     `DATABASE_URL` and `REDIS_URL` carry a non-empty literal, and `SECRET_KEY`
     is sourced from a Secret, never an empty literal.
  5. The otel-collector keeps the GlitchTip (sentry) exporter FIRST in the
     traces pipeline, enables the profiles feature gate, and exports profiles
     to Pyroscope.
  6. Pyroscope stays pinned to the Mint helper node.
  7. The cross-namespace NetworkPolicies that let the app push telemetry into
     the collector (ports 4317/4318) and let GlitchTip reach the cache and the
     backend metrics endpoint (ports 6379/8000) are not silently severed.

The test reads only YAML files in the repo and does not require Kubernetes,
the live cluster, or any database. It runs as a plain `SimpleTestCase`.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from django.test import SimpleTestCase


def _resolve_repo_root() -> Path:
    """Find the repo root whether run on the host or inside a container.

    On the host this file is at ``<repo>/backend/apps/audit/...`` so the repo
    root is ``parents[3]``. Inside the backend-quality container ``__file__`` is
    ``/app/apps/audit/...`` (``./backend`` is mounted as ``/app``) and the full
    repo is mounted at ``/repo`` via the ``REPO_ROOT`` env var. We try that env
    var first, then walk parents, looking for the marker ``k8s`` directory.
    Mirrors ``tests_glitchtip_compose_integrity.py``.
    """
    env_root = os.environ.get("REPO_ROOT")
    if env_root and (Path(env_root) / "k8s").is_dir():
        return Path(env_root)
    here = Path(__file__).resolve()
    for candidate in (here.parents[3], here.parents[2]):
        if (candidate / "k8s").is_dir():
            return candidate
    return here.parents[3]


REPO_ROOT = _resolve_repo_root()
K8S_OBS = REPO_ROOT / "k8s" / "obs"
K8S_NETWORK = REPO_ROOT / "k8s" / "network"

INIT_JOB_PATH = K8S_OBS / "50-glitchtip-init-job.yaml"
MIGRATE_JOB_PATH = K8S_OBS / "51-glitchtip-migrate-job.yaml"
GLITCHTIP_WEB_PATH = K8S_OBS / "52-glitchtip.yaml"
GLITCHTIP_WORKER_PATH = K8S_OBS / "53-glitchtip-worker.yaml"
OTEL_PATH = K8S_OBS / "22-otel-collector.yaml"
PYROSCOPE_PATH = K8S_OBS / "40-pyroscope.yaml"
OBS_NETPOL_PATH = K8S_OBS / "03-netpol.yaml"
APP_OBS_INGRESS_PATH = K8S_NETWORK / "xf-app-allow-obs-ingress.yaml"

MINT_HOSTNAME = "minthelper01-lenovo-c50-30"


def _load_docs(path: Path) -> list[dict]:
    """Load every document from a (possibly multi-doc) k8s YAML file.

    Returns the list of dict documents, skipping the empty (None) documents
    that `---` separators can produce.
    """
    with path.open("r", encoding="utf-8") as fh:
        return [doc for doc in yaml.safe_load_all(fh) if doc is not None]


def _find_doc(docs: list[dict], kind: str, name: str) -> dict | None:
    """Return the first doc matching (kind, metadata.name), or None."""
    for doc in docs:
        if doc.get("kind") == kind and doc.get("metadata", {}).get("name") == name:
            return doc
    return None


def _pod_spec(workload: dict) -> dict:
    """Return the pod spec (`spec.template.spec`) of a Deployment or Job."""
    return workload["spec"]["template"]["spec"]


def _main_container(workload: dict) -> dict:
    """Return the first (main) container of a Deployment or Job."""
    return _pod_spec(workload)["containers"][0]


def _env_map(container: dict) -> dict[str, dict]:
    """Map env var name -> its full entry dict for one container."""
    return {entry["name"]: entry for entry in container.get("env", [])}


class GlitchtipK8sIntegrityTests(SimpleTestCase):
    """Structural guards over the SLICE-21 observability manifests."""

    def test_all_four_glitchtip_workloads_present(self):
        """The four ABSOLUTE-protected GlitchTip workloads must all exist."""
        cases = (
            (INIT_JOB_PATH, "Job", "glitchtip-init"),
            (MIGRATE_JOB_PATH, "Job", "glitchtip-migrate"),
            (GLITCHTIP_WEB_PATH, "Deployment", "glitchtip"),
            (GLITCHTIP_WORKER_PATH, "Deployment", "glitchtip-worker"),
        )
        for path, kind, name in cases:
            with self.subTest(workload=name):
                doc = _find_doc(_load_docs(path), kind, name)
                self.assertIsNotNone(
                    doc,
                    msg=(
                        f"{path.name} is missing the `{name}` {kind}. See "
                        "CLAUDE.md's ABSOLUTE rule on the GlitchTip integration "
                        "— this workload must not be removed."
                    ),
                )

    def test_glitchtip_init_creates_database_idempotently(self):
        """`glitchtip-init` must create the DB only if it does not exist yet."""
        job = _find_doc(_load_docs(INIT_JOB_PATH), "Job", "glitchtip-init")
        args = " ".join(str(a) for a in _main_container(job).get("args", []))
        self.assertIn(
            "CREATE DATABASE",
            args,
            msg=(
                "`glitchtip-init` must run a CREATE DATABASE step. Without it a "
                "dropped or missing `glitchtip` database silently breaks the "
                "dashboard."
            ),
        )
        self.assertIn(
            "WHERE datname='glitchtip'",
            args,
            msg=(
                "`glitchtip-init` must check existence first so it is idempotent "
                "(skips when the DB already exists). Without the check the job "
                "errors on every apply after the first."
            ),
        )

    def test_glitchtip_migrate_runs_script_and_waits_for_db(self):
        """`glitchtip-migrate` runs the migrate script after a wait-for-db init."""
        job = _find_doc(_load_docs(MIGRATE_JOB_PATH), "Job", "glitchtip-migrate")
        command = " ".join(str(c) for c in _main_container(job).get("command", []))
        self.assertIn(
            "run-migrate.sh",
            command,
            msg=(
                "`glitchtip-migrate` must invoke the GlitchTip image's shipped "
                "migration script (`./bin/run-migrate.sh`). Anything else risks "
                "running the wrong migrations or skipping partition setup."
            ),
        )
        init_containers = _pod_spec(job).get("initContainers") or []
        self.assertGreaterEqual(
            len(init_containers),
            1,
            msg=(
                "`glitchtip-migrate` must have a wait-for-db initContainer. "
                "Kubernetes Jobs cannot 'wait for the other Job', so this init "
                "container enforces the init -> migrate ordering."
            ),
        )

    def test_glitchtip_workloads_never_blank_connection_env(self):
        """DATABASE_URL/REDIS_URL stay non-empty; SECRET_KEY comes from a Secret."""
        workloads = (
            ("glitchtip", _find_doc(_load_docs(GLITCHTIP_WEB_PATH), "Deployment", "glitchtip")),
            ("glitchtip-worker", _find_doc(_load_docs(GLITCHTIP_WORKER_PATH), "Deployment", "glitchtip-worker")),
            ("glitchtip-migrate", _find_doc(_load_docs(MIGRATE_JOB_PATH), "Job", "glitchtip-migrate")),
        )
        for name, workload in workloads:
            with self.subTest(workload=name):
                env = _env_map(_main_container(workload))

                for key in ("DATABASE_URL", "REDIS_URL"):
                    self.assertIn(
                        key,
                        env,
                        msg=f"`{name}` must define the `{key}` env var.",
                    )
                    value = env[key].get("value")
                    self.assertTrue(
                        value,
                        msg=(
                            f"`{name}` has a blank `{key}`. The GlitchTip "
                            "connection settings must never be blanked — see the "
                            "ABSOLUTE GlitchTip rule in CLAUDE.md."
                        ),
                    )

                self.assertIn(
                    "SECRET_KEY",
                    env,
                    msg=f"`{name}` must define the `SECRET_KEY` env var.",
                )
                secret_ref = (env["SECRET_KEY"].get("valueFrom") or {}).get("secretKeyRef")
                self.assertTrue(
                    secret_ref,
                    msg=(
                        f"`{name}` must source `SECRET_KEY` from a Secret "
                        "(valueFrom.secretKeyRef), never an empty literal value."
                    ),
                )

    def test_otel_collector_keeps_sentry_first_and_profiles_wired(self):
        """Sentry stays the FIRST traces exporter; profiles go to Pyroscope."""
        docs = _load_docs(OTEL_PATH)
        config_map = _find_doc(docs, "ConfigMap", "otelcol-config")
        self.assertIsNotNone(config_map, msg="otelcol-config ConfigMap is missing.")

        config = yaml.safe_load(config_map["data"]["config.yaml"])

        exporters = config.get("exporters") or {}
        self.assertIn(
            "sentry",
            exporters,
            msg=(
                "The otel-collector must define the `sentry` exporter — that is "
                "the ABSOLUTE-protected GlitchTip error path."
            ),
        )
        self.assertIn(
            "otlp/pyroscope",
            exporters,
            msg="The otel-collector must define the `otlp/pyroscope` exporter.",
        )

        traces_exporters = (
            config.get("service", {})
            .get("pipelines", {})
            .get("traces", {})
            .get("exporters", [])
        )
        self.assertTrue(traces_exporters, msg="traces pipeline has no exporters.")
        self.assertEqual(
            traces_exporters[0],
            "sentry",
            msg=(
                "`sentry` must be the FIRST exporter in the traces pipeline so "
                "errors always reach GlitchTip. Got: "
                f"{traces_exporters!r}"
            ),
        )

        deployment = _find_doc(docs, "Deployment", "otel-collector")
        self.assertIsNotNone(deployment, msg="otel-collector Deployment is missing.")
        args = " ".join(str(a) for a in _main_container(deployment).get("args", []))
        self.assertIn(
            "--feature-gates=service.profilesSupport",
            args,
            msg=(
                "The otel-collector must enable the profiles feature gate so the "
                "profiles pipeline can run and forward to Pyroscope."
            ),
        )

    def test_pyroscope_pinned_to_mint_helper(self):
        """Pyroscope is the one profiling tool pinned to the Mint helper node."""
        deployment = _find_doc(_load_docs(PYROSCOPE_PATH), "Deployment", "pyroscope")
        self.assertIsNotNone(deployment, msg="pyroscope Deployment is missing.")
        node_selector = _pod_spec(deployment).get("nodeSelector") or {}
        self.assertEqual(
            node_selector.get("kubernetes.io/hostname"),
            MINT_HOSTNAME,
            msg=(
                "Pyroscope must stay pinned to the Mint helper "
                f"(`{MINT_HOSTNAME}`) per the migration design. Got node "
                f"selector: {node_selector!r}"
            ),
        )

    def test_obs_netpol_allows_app_telemetry_ports(self):
        """xf-obs must accept OTLP traffic (4317/4318) from the app namespace."""
        policy = _find_doc(
            _load_docs(OBS_NETPOL_PATH),
            "NetworkPolicy",
            "allow-xf-app-telemetry",
        )
        self.assertIsNotNone(
            policy,
            msg="The `allow-xf-app-telemetry` NetworkPolicy is missing.",
        )
        ports = {
            rule_port["port"]
            for rule in policy["spec"]["ingress"]
            for rule_port in rule.get("ports", [])
        }
        for expected in (4317, 4318):
            self.assertIn(
                expected,
                ports,
                msg=(
                    f"`allow-xf-app-telemetry` must allow ingress on port "
                    f"{expected} so the app can push telemetry into the "
                    "collector. Got ports: "
                    f"{sorted(ports)}"
                ),
            )

    def test_app_netpol_allows_obs_to_reach_cache_and_metrics(self):
        """xf-app must let xf-obs reach the cache (6379) and metrics (8000)."""
        policy = _find_doc(
            _load_docs(APP_OBS_INGRESS_PATH),
            "NetworkPolicy",
            "allow-obs-ingress",
        )
        self.assertIsNotNone(
            policy,
            msg="The `allow-obs-ingress` NetworkPolicy is missing.",
        )
        ports = {
            rule_port["port"]
            for rule in policy["spec"]["ingress"]
            for rule_port in rule.get("ports", [])
        }
        for expected in (8000, 6379):
            self.assertIn(
                expected,
                ports,
                msg=(
                    f"`allow-obs-ingress` must allow ingress on port {expected} "
                    "so the monitoring tools can reach the backend metrics "
                    "endpoint (8000) and the cache (6379). Got ports: "
                    f"{sorted(ports)}"
                ),
            )
