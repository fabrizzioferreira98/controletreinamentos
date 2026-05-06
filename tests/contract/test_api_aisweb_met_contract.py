from __future__ import annotations

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.api.http.dashboard import routes as dashboard_api


class _SingleCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _SingleUserDB:
    def __init__(self, row):
        self._row = row

    def execute(self, _query, _params):
        return _SingleCursor(self._row)


def _auth_user_row():
    return {
        "id": 32,
        "nome": "Operador Meteorologia",
        "login": "weather_api",
        "email": "weather.api@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": '["dashboard:view"]',
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch):
    fake_db = _SingleUserDB(_auth_user_row())
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)
    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "weather_api", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 200


def test_api_aisweb_met_returns_clean_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    def _fake_get_aisweb_met(icao_code):
        assert icao_code == "SBGO"
        return {
            "icaoCode": "SBGO",
            "locationLabel": "Goi\u00e2nia",
            "temperatureC": 27,
            "windDirection": "120",
            "windSpeedKt": 12,
            "condition": "UNKNOWN",
            "rawMetar": "SBGO 170900Z 12012KT 9999 FEW030 27/18 Q1015",
            "rawTaf": "TAF SBGO 170900Z 1712/1812 12010KT CAVOK",
            "observedAt": "2026-04-17T09:00:00Z",
            "updatedAtLabel": "Atualizado agora",
            "source": "AISWEB",
            "status": "available",
        }

    monkeypatch.setattr(dashboard_api, "get_aisweb_met", _fake_get_aisweb_met)

    response = client.get("/api/aisweb/met?icaoCode=SBGO")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "aisweb_met_ok"
    assert payload["weather"]["temperatureC"] == 27
    assert payload["weather"]["windDirection"] == "120"
    assert payload["weather"]["windSpeedKt"] == 12
    assert payload["weather"]["rawMetar"].startswith("SBGO 170900Z")
    assert payload["weather"]["rawTaf"].startswith("TAF SBGO")


def test_api_aisweb_met_rejects_invalid_icao(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    response = client.get("/api/aisweb/met?icaoCode=SB1")

    assert response.status_code == 400
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["code"] == "aisweb_met_invalid_icao"
