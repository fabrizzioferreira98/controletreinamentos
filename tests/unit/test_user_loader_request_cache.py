import time

from flask import Flask, session

from backend.src.controle_treinamentos.models import User


class _FakeCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeDB:
    def __init__(self, row):
        self._row = row
        self.calls = 0

    def execute(self, _query, _params):
        self.calls += 1
        return _FakeCursor(self._row)


def test_user_get_uses_request_local_cache(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["AUTH_SNAPSHOT_MAX_AGE_SECONDS"] = 300
    row = {
        "id": 7,
        "nome": "Operador",
        "login": "operador",
        "email": "op@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": "[]",
    }
    fake_db = _FakeDB(row)

    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    with app.test_request_context("/"):
        first = User.get(7)
        second = User.get(7)

    assert first is not None
    assert second is not None
    assert fake_db.calls == 1


def test_user_get_keeps_recent_session_snapshot(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["AUTH_SNAPSHOT_REFRESH_INTERVAL_SECONDS"] = 300
    now = int(time.time())
    row = {
        "id": 8,
        "nome": "Operador",
        "login": "operador",
        "email": "op@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": "[]",
    }
    fake_db = _FakeDB(row)

    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    with app.test_request_context("/"):
        session["auth_user_snapshot"] = {
            "id": "8",
            "nome": "Operador",
            "login": "operador",
            "email": "op@local.test",
            "perfil": "operador",
            "ativo": 1,
            "permissao_modulos_json": "[]",
            "captured_at": now,
        }
        session["auth_user_snapshot_ts"] = now

        user = User.get(8)

        assert user is not None
        assert session["auth_user_snapshot_ts"] == now
        assert fake_db.calls == 1


def test_user_get_refreshes_stale_session_snapshot(monkeypatch):
    app = Flask(__name__)
    app.secret_key = "test-secret"
    app.config["AUTH_SNAPSHOT_REFRESH_INTERVAL_SECONDS"] = 30
    now = int(time.time())
    row = {
        "id": 9,
        "nome": "Operador Novo",
        "login": "operador",
        "email": "op@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": "[]",
    }
    fake_db = _FakeDB(row)

    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    with app.test_request_context("/"):
        session["auth_user_snapshot"] = {
            "id": "9",
            "nome": "Operador Antigo",
            "login": "operador",
            "email": "op@local.test",
            "perfil": "operador",
            "ativo": 1,
            "permissao_modulos_json": "[]",
            "captured_at": now - 60,
        }
        session["auth_user_snapshot_ts"] = now - 60

        user = User.get(9)

        assert user is not None
        assert session["auth_user_snapshot"]["nome"] == "Operador Novo"
        assert session["auth_user_snapshot_ts"] >= now
