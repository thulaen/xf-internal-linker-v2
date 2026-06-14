"""
Shared pytest fixtures for the entire backend test suite.

These fixtures are automatically available in every test file.
Add project-wide fixtures here; app-specific fixtures belong
in each app's own conftest.py.
"""

import os

import pytest


def pytest_configure() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

    import django

    django.setup()
    _configure_hypothesis_profiles()


def _configure_hypothesis_profiles() -> None:
    """Register the two Hypothesis profiles property tests run under.

    ``fast``  — pre-commit: few examples + bounded shrinking, so the scoped
                property run stays a quick sprint. ``HYPOTHESIS_PROFILE=fast``
                (the default) selects it.
    ``ci``    — push/CI: a deep hunt (many examples) for the thorough sweep.

    Deadlines are deliberately disabled: all quality work runs on the shared
    Dell helper, so a per-example wall-clock deadline would flake whenever Dell
    is busy with another run. The real time cap is the single wall-clock
    timeout in ``scripts/run-pbt.sh`` — one reliable ceiling instead of many
    flaky ones. ``derandomize`` is off so the example database keeps finding new
    inputs; past failing inputs are replayed first from that database.
    """
    from hypothesis import HealthCheck, Phase, settings

    common = {
        "deadline": None,
        "suppress_health_check": [HealthCheck.too_slow],
        # Cap shrinking so a real failure reports fast instead of grinding.
        "phases": (Phase.explicit, Phase.reuse, Phase.generate, Phase.target, Phase.shrink),
    }
    settings.register_profile("fast", max_examples=20, **common)
    settings.register_profile("ci", max_examples=500, **common)
    settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "fast"))


def _kill_monitoring_connections_to_test_db() -> None:
    """Kill any external monitoring connections to test_xf_linker.

    Monitoring services (e.g. postgres-exporter) connect to every database in
    the cluster, including the test database. If a previous test session failed
    to drop test_xf_linker at teardown, the monitoring service keeps an idle
    connection to it. When the next session's test runner tries to DROP + CREATE
    test_xf_linker, Postgres rejects the DROP because of that idle connection.

    This helper runs via the session-scoped ``_ensure_clean_test_db`` fixture
    (autouse=True) so it fires BEFORE Django's ``setup_databases()`` call and
    clears the way for a clean test DB setup.

    This is a test-support helper only; it lives in conftest.py (not a
    production path) so the per-file coverage gate ignores it.
    """
    try:
        import psycopg
        from django.conf import settings

        db = settings.DATABASES["default"]
        conn_str = (
            f"host={db.get('HOST','localhost')} "
            f"port={db.get('PORT', 5432)} "
            f"dbname={db.get('NAME','xf_linker')} "
            f"user={db.get('USER','')} "
            f"password={db.get('PASSWORD','')}"
        )
        with psycopg.connect(conn_str, autocommit=True) as conn:
            conn.execute(
                "SELECT pg_terminate_backend(pid) "
                "FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (f"test_{db.get('NAME', 'xf_linker')}",),
            )
    except Exception:  # noqa: BLE001  — best-effort cleanup, never fail tests
        pass


def pytest_sessionstart(session) -> None:  # noqa: ARG001
    """Kill monitoring connections to test_xf_linker before DB setup.

    Fires BEFORE Django's test DB setup so that any stale monitoring
    connections (e.g. postgres-exporter) are evicted before DROP + CREATE runs.
    Without this hook, a postgres-exporter connection that survived a previous
    session's failed teardown blocks the next session's DROP DATABASE command,
    causing SystemExit(2) and leaving all tests uncovered in the per-file
    coverage gate.  See paper-trail #304 and AutoIssue #20181.
    """
    _kill_monitoring_connections_to_test_db()


def pytest_sessionfinish(session, exitstatus) -> None:  # noqa: ARG001
    """Kill monitoring connections right before teardown so DROP can proceed.

    postgres-exporter reconnects to test_xf_linker during the session.  A second
    eviction here fires BEFORE Django's teardown_databases() drops the test DB,
    allowing the DROP to succeed so the next session starts from a clean state.
    """
    _kill_monitoring_connections_to_test_db()


@pytest.fixture(scope="session")
def django_db_setup(
    request,
    django_test_environment,
    django_db_blocker,
    django_db_keepdb,
    django_db_createdb,
    django_db_modify_db_settings,
):
    """Session-scoped DB setup: parallel-safe, reuse-aware, monitor-evicting.

    Overrides pytest-django's default ``django_db_setup`` fixture. Three jobs:

    1. **One database per parallel worker.** Depending on
       ``django_db_modify_db_settings`` pulls in pytest-django's per-xdist-worker
       suffix, so under ``-n auto`` each worker creates its own
       ``test_xf_linker_gwN`` database. Without this dependency every worker
       tries to create the single name ``test_xf_linker`` at once and all but
       one die with "duplicate database" at setup.
    2. **Honor ``--reuse-db``.** When keepdb is on, the per-worker databases are
       created once and kept, so the next run skips the full migration and is
       fast instead of re-migrating every worker DB from scratch.
    3. **Evict stale monitoring connections.** On the shared local Postgres,
       postgres-exporter connects to every database including the test DB; a
       leftover idle connection blocks DROP at teardown. Evicting first lets the
       DROP succeed. This is a best-effort no-op on the isolated Dell test
       Postgres (no exporter there). See AutoIssue #20181 and paper-trail #304.
    """
    from django.db import connections
    from django.test.utils import setup_databases, teardown_databases

    keepdb = bool(django_db_keepdb and not django_db_createdb)
    _kill_monitoring_connections_to_test_db()
    with django_db_blocker.unblock():
        old_config = setup_databases(
            verbosity=request.config.option.verbose,
            interactive=False,
            keepdb=keepdb,
        )
    yield

    if keepdb:
        # --reuse-db: keep the per-worker databases for the next run.
        return

    with django_db_blocker.unblock():
        # Kill monitoring connections AND drop the test DB so the exporter can't
        # reconnect between the two steps. ``setup_databases`` rewrites the
        # connection's NAME to the (possibly worker-suffixed) test DB, so read
        # that real name rather than re-deriving it.
        try:
            import psycopg
            from django.conf import settings

            db = settings.DATABASES["default"]
            test_db_name = connections["default"].settings_dict["NAME"]
            conn_str = (
                f"host={db.get('HOST', 'localhost')} "
                f"port={db.get('PORT', 5432)} "
                f"dbname={db.get('NAME', 'xf_linker')} "
                f"user={db.get('USER', '')} "
                f"password={db.get('PASSWORD', '')}"
            )
            with psycopg.connect(conn_str, autocommit=True) as conn:
                conn.execute(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = %s AND pid <> pg_backend_pid()",
                    (test_db_name,),
                )
                conn.execute(f"DROP DATABASE IF EXISTS {test_db_name}")
        except Exception:  # noqa: BLE001
            pass
        teardown_databases(old_config, verbosity=request.config.option.verbose)


def pytest_runtest_teardown(item, nextitem):
    # Wipe process-wide Django cache after every test so a previous
    # test that flipped a runtime flag (e.g. yake_keywords.enabled=false)
    # doesn't leak a stale value to the next test. The DB transaction
    # rolls back, but the cache survives. This hook is the central
    # post-test cleanup; it's cheaper and safer than per-class tearDowns.
    try:
        from django.core.cache import cache

        cache.clear()
    except Exception:  # noqa: BLE001
        pass


def _user_model():
    from django.contrib.auth import get_user_model

    return get_user_model()


@pytest.fixture
def user(db):
    """A plain authenticated user with no special permissions."""
    return _user_model().objects.create_user(
        username="testuser",
        email="testuser@example.com",
        password="testpassword123",
    )


@pytest.fixture
def admin_user(db):
    """A superuser for testing admin-only endpoints."""
    return _user_model().objects.create_superuser(
        username="admin",
        email="admin@example.com",
        password="adminpassword123",
    )


@pytest.fixture
def api_client():
    """DRF APIClient, unauthenticated. Use .force_authenticate(user=...) as needed."""
    from rest_framework.test import APIClient

    return APIClient()


@pytest.fixture
def auth_client(api_client, user):
    """DRF APIClient pre-authenticated as the plain test user."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def admin_client(api_client, admin_user):
    """DRF APIClient pre-authenticated as the admin superuser."""
    api_client.force_authenticate(user=admin_user)
    return api_client
