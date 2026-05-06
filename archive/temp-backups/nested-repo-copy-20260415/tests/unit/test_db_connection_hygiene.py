from flask import Flask, g

from backend.src.controle_treinamentos.db import connection as db_connection


class _FakeConn:
    def __init__(self, *, closed=0, tx_status=0, rollback_raises=False):
        self.closed = closed
        self._tx_status = tx_status
        self._rollback_raises = rollback_raises
        self.rollback_calls = 0
        self.close_calls = 0

    def get_transaction_status(self):
        return self._tx_status

    def rollback(self):
        self.rollback_calls += 1
        if self._rollback_raises:
            raise RuntimeError("rollback_failed")

    def close(self):
        self.close_calls += 1


class _FakePool:
    def __init__(self, *connections):
        self._connections = list(connections)
        self.put_calls = []

    def getconn(self):
        return self._connections.pop(0)

    def putconn(self, conn, close=False):
        self.put_calls.append((conn, close))


class _FlakyPool:
    def __init__(self, connection):
        self._connection = connection
        self._first = True
        self.put_calls = []

    def getconn(self):
        if self._first:
            self._first = False
            raise RuntimeError("temporary_db_failure")
        return self._connection

    def putconn(self, conn, close=False):
        self.put_calls.append((conn, close))

    def closeall(self):
        return None


def _make_app():
    app = Flask(__name__)
    app.config.update(TESTING=True, DATABASE_URL="postgresql://user:pass@localhost:5432/app")
    return app


def test_close_db_discards_connection_when_rollback_fails(monkeypatch):
    app = _make_app()
    conn = _FakeConn(rollback_raises=True)
    pool = _FakePool()

    with app.app_context():
        g._pg_conn = conn
        g.db = object()
        monkeypatch.setattr(db_connection, "_pg_pool", pool)
        monkeypatch.setattr(db_connection, "_is_connection_broken", lambda _conn: False)

        db_connection.close_db()

    assert pool.put_calls == [(conn, True)]


def test_get_db_discards_broken_pool_connection_and_retries(monkeypatch):
    app = _make_app()
    broken = _FakeConn(closed=1)
    healthy = _FakeConn(closed=0)
    pool = _FakePool(broken, healthy)

    with app.app_context():
        monkeypatch.setattr(db_connection, "_pg_pool", pool)
        monkeypatch.setattr(db_connection, "_pg_pool_config", {"min_conn": 1, "max_conn": 20})

        db = db_connection.get_db()
        assert db is not None
        assert g._pg_conn is healthy
        assert pool.put_calls == [(broken, True)]

        db_connection.close_db()


def test_get_db_recycles_pool_and_retries_once_on_transient_pool_failure(monkeypatch):
    app = _make_app()
    healthy = _FakeConn(closed=0)
    created_pools = []
    factory_calls = {"count": 0}

    def _factory(_min_conn, _max_conn, _url, **_kwargs):
        factory_calls["count"] += 1
        if factory_calls["count"] == 1:
            pool = _FlakyPool(healthy)
        else:
            pool = _FakePool(healthy)
        created_pools.append(pool)
        return pool

    with app.app_context():
        monkeypatch.setattr(db_connection, "_pg_pool", None)
        monkeypatch.setattr(db_connection, "_pg_pool_config", None)
        monkeypatch.setattr(db_connection, "ThreadedConnectionPool", _factory)

        db = db_connection.get_db()
        assert db is not None
        assert g._pg_conn is healthy
        assert len(created_pools) == 2

        db_connection.close_db()
