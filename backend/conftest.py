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
def django_db_setup(request, django_test_environment, django_db_blocker):
    """Session-scoped DB setup that evicts monitoring connections on teardown.

    Overrides pytest-django's default ``django_db_setup`` fixture to:
    1. Evict stale monitoring connections BEFORE setup (clears any leftover
       connections from a previous failed teardown).
    2. Evict monitoring connections again BEFORE teardown so that Django's
       DROP DATABASE command succeeds even when postgres-exporter reconnected
       during the session.

    This is necessary because postgres-exporter connects to every database in
    the cluster, including test_xf_linker.  Without this override, teardown
    fails with "database is being accessed by other users" and test_xf_linker
    persists across sessions, causing the NEXT session to fail at setup.
    See AutoIssue #20181 and paper-trail #304.
    """
    from django.test.utils import setup_databases, teardown_databases

    _kill_monitoring_connections_to_test_db()
    with django_db_blocker.unblock():
        old_config = setup_databases(
            verbosity=request.config.option.verbose,
            interactive=False,
        )
    yield

    with django_db_blocker.unblock():
        # Kill monitoring connections AND drop the test DB in a single
        # transaction to prevent the exporter from reconnecting between the
        # two steps.  After this the test DB is gone; teardown_databases is
        # called with the DB already absent, which is a no-op for Django.
        try:
            import psycopg
            from django.conf import settings

            db = settings.DATABASES["default"]
            test_db_name = f"test_{db.get('NAME', 'xf_linker')}"
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
