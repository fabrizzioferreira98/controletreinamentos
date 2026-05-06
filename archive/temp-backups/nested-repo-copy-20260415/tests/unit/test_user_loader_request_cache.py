from flask import Flask

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
