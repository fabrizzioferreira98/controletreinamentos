from __future__ import annotations

from datetime import date

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
        "id": 31,
        "nome": "Operador Dashboard",
        "login": "dash_api",
        "email": "dash.api@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": '["dashboard:view"]',
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch):
    row = _auth_user_row()
    fake_db = _SingleUserDB(row)
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)
    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "dash_api", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 200


def test_api_dashboard_summary_returns_contract_without_template_links(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        dashboard_api,
        "get_dashboard_summary_data",
        lambda _db: {
            "totals": {"tripulantes": 48, "equipamentos": 3, "tipos": 6, "treinamentos": 20},
            "summary": {"total": 20, "vencido": 2, "a_vencer": 5, "regular": 13, "sem_informacao": 0},
            "alerts": {"vencidos": 2, "vencem_hoje": 1, "em_7_dias": 1, "em_30_dias": 5},
        },
    )
    monkeypatch.setattr(dashboard_api, "get_db", lambda: object())

    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "dashboard_summary_ok"
    assert payload["dashboard"]["summary"]["a_vencer"] == 5
    assert payload["dashboard"]["alerts"]["vencem_hoje"] == 1


def test_api_dashboard_calendar_returns_contract_without_url_fields(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        dashboard_api,
        "get_dashboard_calendar_data",
        lambda _db: {
            "month_label": "Abril 2026",
            "weekday_labels": ["Seg", "Ter"],
            "today_label": "02/04/2026",
            "items_total": 1,
            "weeks": [
                [
                    {
                        "iso_date": "2026-04-02",
                        "day_number": 2,
                        "is_current_month": True,
                        "is_today": True,
                        "has_due": True,
                        "pulse": True,
                        "count": 1,
                        "items": [
                            {
                                "id": 91,
                                "tripulante_id": 7,
                                "tripulante_nome": "Lucas Silva",
                                "equipamento_nome": "AS350",
                                "tipo_treinamento_nome": "CQ IFR",
                                "data_vencimento": "02/04/2026",
                                "status": "a vencer",
                            }
                        ],
                    }
                ]
            ],
            "upcoming": [
                {
                    "id": 91,
                    "tripulante_id": 7,
                    "tripulante_nome": "Lucas Silva",
                    "equipamento_nome": "AS350",
                    "tipo_treinamento_nome": "CQ IFR",
                    "data_vencimento": "02/04/2026",
                    "status": "a vencer",
                }
            ],
        },
    )
    monkeypatch.setattr(dashboard_api, "get_db", lambda: object())

    response = client.get("/api/v1/dashboard/calendar")

    assert response.status_code == 200
    payload = response.get_json()
    item = payload["calendar"]["weeks"][0][0]["items"][0]
    assert payload["code"] == "dashboard_calendar_ok"
    assert item["id"] == 91
    assert "training_url" not in item
    assert "tripulante_url" not in item


def test_api_dashboard_critical_trainings_returns_collection(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        dashboard_api,
        "get_dashboard_critical_trainings_data",
        lambda _db, limit=8: {
            "items": [
                {
                    "id": 55,
                    "tripulante_id": 7,
                    "tripulante_nome": "Lucas Silva",
                    "equipamento_id": 3,
                    "equipamento_nome": "AS350",
                    "tipo_treinamento_id": 2,
                    "tipo_treinamento_nome": "CQ IFR",
                    "data_realizacao": date(2026, 4, 1),
                    "data_vencimento": date(2026, 4, 5),
                    "status": "a vencer",
                }
            ]
        },
    )
    monkeypatch.setattr(dashboard_api, "get_db", lambda: object())

    response = client.get("/api/v1/dashboard/critical-trainings?limit=5")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == "dashboard_critical_trainings_ok"
    assert payload["critical_trainings"]["items"][0]["id"] == 55
    assert payload["critical_trainings"]["items"][0]["data_realizacao"] == "2026-04-01"
    assert payload["critical_trainings"]["items"][0]["data_vencimento"] == "2026-04-05"


def test_api_dashboard_base_operations_returns_bases_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        dashboard_api,
        "build_bases_api_payload",
        lambda status_filter=None: {
            "success": True,
            "status": 200,
            "code": "bases_payload_ok",
            "bases": [
                {
                    "id": 1,
                    "nome": "Goiania",
                    "uf": "GO",
                    "latitude": -16.632,
                    "longitude": -49.221,
                    "ativa": 1,
                    "total_pilotos": 1,
                    "counts": {"ativo": 1},
                    "pilotos": [
                        {
                            "id": 77,
                            "nome": "Lucas Silva",
                            "matricula": "AB123",
                            "tripulante_id": 7,
                            "base_id": 1,
                            "base_nome": "Goiania",
                            "base_uf": "GO",
                            "status": "ativo",
                            "status_label": "Ativo",
                            "status_class": "status-green",
                            "status_raw": None,
                            "possui_foto": False,
                            "foto_url": "",
                            "iniciais": "LS",
                            "expiry_indicator": {},
                            "criado_em": "",
                            "criado_em_iso": None,
                        }
                    ],
                }
            ],
            "pilotos": [],
            "status_options": [{"key": "ativo", "label": "Ativo", "class": "status-green", "marker_class": "dot"}],
            "status_filter": status_filter or "",
        },
    )

    response = client.get("/api/v1/dashboard/base-operations")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "bases_payload_ok"
    assert payload["bases"][0]["nome"] == "Goiania"
    assert payload["bases"][0]["latitude"] == -16.632
    assert payload["bases"][0]["pilotos"][0]["tripulante_id"] == 7


def test_api_dashboard_weather_by_base_returns_aggregate_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        dashboard_api,
        "build_dashboard_weather_by_base",
        lambda: {
            "status": "available",
            "source": "AISWEB",
            "updatedAt": "2026-05-05T12:00:00Z",
            "updatedAtLabel": "Atualizado agora",
            "items": [
                {
                    "icaoCode": "SBGO",
                    "locationLabel": "Goiania",
                    "temperatureC": 24,
                    "windSpeedKt": 8,
                    "visibilityMeters": 10000,
                    "condition": "VMC",
                    "rawMetar": "SBGO 051200Z 09008KT 9999",
                    "rawTaf": "TAF SBGO",
                    "source": "AISWEB",
                    "status": "available",
                }
            ],
            "errors": [],
        },
    )

    response = client.get("/api/v1/dashboard/weather-by-base")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == "dashboard_weather_by_base_ok"
    assert payload["weather_by_base"]["source"] == "AISWEB"
    assert payload["weather_by_base"]["items"][0]["icaoCode"] == "SBGO"
    assert payload["weather_by_base"]["items"][0]["condition"] == "VMC"
    assert payload["weather_by_base"]["items"][0]["rawMetar"].startswith("SBGO")


def test_api_dashboard_notams_returns_unavailable_without_mock(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        dashboard_api,
        "build_dashboard_relevant_notams",
        lambda: {
            "status": "unavailable",
            "source": "not_configured",
            "updatedAt": "2026-05-05T12:00:00Z",
            "updatedAtLabel": "Ultima atualizacao indisponivel",
            "message": "Integracao real de NOTAM indisponivel.",
            "items": [],
        },
    )

    response = client.get("/api/v1/dashboard/notams")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == "dashboard_notams_unavailable"
    assert payload["notams"]["items"] == []
    assert payload["notams"]["source"] == "not_configured"
    assert "Pista 17R/35L fechada" not in response.get_data(as_text=True)


def test_api_dashboard_notams_returns_real_aisweb_items(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        dashboard_api,
        "build_dashboard_relevant_notams",
        lambda: {
            "status": "available",
            "source": "AISWEB",
            "updatedAt": "2026-05-05T12:00:00Z",
            "updatedAtLabel": "Atualizado agora",
            "message": "",
            "items": [
                {
                    "id": "11718183",
                    "code": "NAV",
                    "icao": "SBGO",
                    "description": "AUXILIO NAV INOP",
                    "updatedAt": "2026-05-05T12:00:00Z",
                    "updatedAtLabel": "05/05 12:00Z",
                    "validUntil": "2026-05-06T12:00:00Z",
                    "validUntilLabel": "06/05 12:00Z",
                    "severity": "critical",
                    "source": "AISWEB",
                }
            ],
        },
    )

    response = client.get("/api/v1/dashboard/notams")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == "dashboard_notams_ok"
    assert payload["notams"]["source"] == "AISWEB"
    assert payload["notams"]["items"][0]["id"] == "11718183"
    assert payload["notams"]["items"][0]["description"] == "AUXILIO NAV INOP"


def test_api_dashboard_operational_alerts_returns_ticker_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(dashboard_api, "get_dashboard_summary_data", lambda _db: {"alerts": {}, "summary": {}})
    monkeypatch.setattr(dashboard_api, "build_bases_api_payload", lambda status_filter=None: {"bases": []})
    monkeypatch.setattr(dashboard_api, "build_dashboard_relevant_notams", lambda: {"status": "available", "items": []})
    monkeypatch.setattr(
        dashboard_api,
        "build_dashboard_operational_alerts",
        lambda **_kwargs: {
            "status": "available",
            "source": "dashboard_operational_contracts",
            "items": [
                {
                    "id": "training-due-today",
                    "severity": "critical",
                    "label": "Vencem hoje",
                    "message": "1 treinamento vence hoje.",
                    "source": "dashboard_summary",
                }
            ],
            "updatedAt": "2026-05-05T12:00:00Z",
            "message": "",
        },
    )
    monkeypatch.setattr(dashboard_api, "get_db", lambda: object())

    response = client.get("/api/v1/dashboard/operational-alerts")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == "dashboard_operational_alerts_ok"
    alert = payload["operational_alerts"]["items"][0]
    assert alert["source"] == "dashboard_summary"
    assert alert["message"] == "1 treinamento vence hoje."
