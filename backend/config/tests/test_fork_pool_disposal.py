"""Regression: the Celery fork hook must DISPOSE the psycopg 3 pool, not just
close the connection.

With ``DATABASES["default"]["OPTIONS"]["pool"]`` set, ``os.fork()`` (used by
Celery's prefork worker pool) duplicates the parent's live TCP sockets, and the
pool's background maintenance thread does not survive the fork. Calling
``conn.close()`` only RETURNS the current connection to the *inherited* pool; it
leaves those duplicated sockets in place. Two forked workers can then be handed
the same server connection and interleave on the wire — surfacing as
``OperationalError: sending query failed`` / ``DatabaseError: lost
synchronization with server`` and then ``InvalidSavepointSpecification`` /
``InvalidCursorName`` as savepoints and server-side cursors created on one
process's view of the socket vanish from another's.

Disposing the pool (``close_pool``) drops the inherited pool entirely so psycopg
builds a fresh per-process pool on first use, isolating each fork.

Source: psycopg 3 docs "Pool and forking"; Django ticket #14241.
"""

from unittest import mock

from django.test import SimpleTestCase


class ForkPoolDisposalTests(SimpleTestCase):
    """The ``worker_process_init`` hook disposes every connection pool."""

    @staticmethod
    def _run_hook(conns):
        from config.celery import _close_db_connections_on_fork

        with mock.patch("django.db.connections.all", return_value=conns):
            _close_db_connections_on_fork()

    def test_fork_hook_disposes_pool_on_each_connection(self):
        conn = mock.MagicMock()
        self._run_hook([conn])
        conn.close_pool.assert_called_once()

    def test_fork_hook_disposes_pool_even_when_close_raises(self):
        conn = mock.MagicMock()
        conn.close.side_effect = RuntimeError("socket already dead after fork")
        self._run_hook([conn])
        conn.close_pool.assert_called_once()

    def test_fork_hook_survives_connection_without_close_pool(self):
        # A non-pooled / older backend may lack close_pool; must not raise.
        conn = mock.MagicMock(spec=["close"])
        self._run_hook([conn])  # no exception == pass
