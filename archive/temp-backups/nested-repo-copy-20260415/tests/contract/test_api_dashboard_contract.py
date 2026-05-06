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
        "id": 31,
        "nome": "Operador Dashboard",
        "login": "dash_api",
        "email": "dash.api@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": '["dashboard:view","tv_vencimentos:view","tv_produtividade:view"]',
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
            "alerts": {"vencidos": 2, "em_7_dias": 1, "em_30_dias": 5},
        },
    )
    monkeypatch.setattr(dashboard_api, "get_db", lambda: object())

    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "dashboard_summary_ok"
    assert payload["dashboard"]["summary"]["a_vencer"] == 5


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
                    "data_realizacao": "2026-04-01",
                    "data_vencimento": "2026-04-05",
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


def test_api_tv_vencimentos_returns_panel_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        dashboard_api,
        "get_tv_vencimentos_data",
        lambda _db, base_filter="": {
            "generated_at": {"iso": "2026-04-02T10:00:00-03:00", "label": "02/04/2026 10:00:00"},
            "base_filter": base_filter,
            "summary": {"total_tripulantes": 48, "total_habilitacoes": 20, "total_em_dia": 10, "total_vencer_90": 8, "total_vencer_60": 6, "total_vencer_30": 4, "total_critico_15": 2, "total_vencido": 1},
            "proximos_vencimentos": [],
            "critical_trainings": [],
            "expired_trainings": [],
            "ranking_bases": [],
            "ranking_tripulantes": [],
            "alerts": [{"level": "high", "message": "teste"}],
        },
    )
    monkeypatch.setattr(dashboard_api, "get_db", lambda: object())

    response = client.get("/api/v1/tv/vencimentos?base=SSA")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == "tv_vencimentos_ok"
    assert payload["panel"]["base_filter"] == "SSA"


def test_api_tv_produtividade_returns_panel_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        dashboard_api,
        "get_tv_produtividade_data",
        lambda _db, competencia="": {
            "competencia": "2026-04",
            "competencia_label": "Abril/2026",
            "updated_at": "02/04/2026 10:00:00",
            "summary": {"valor_total_mes": 1000.0},
            "rows": [
                {
                    "tripulante_id": 7,
                    "tripulante_nome": "Lucas Silva",
                    "base": "SSA",
                    "categoria": "Piloto",
                    "funcao": "Comandante",
                    "total_missoes_validas": 4,
                    "total_pernoites": 2,
                    "total_produtividade": 5.0,
                    "valor_final_mes": 1000.0,
                    "criterio_fechamento": "Mensal",
                }
            ],
        },
    )
    monkeypatch.setattr(dashboard_api, "get_db", lambda: object())

    response = client.get("/api/v1/tv/produtividade?competencia=2026-04")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == "tv_produtividade_ok"
    assert payload["panel"]["rows"][0]["tripulante_id"] == 7
