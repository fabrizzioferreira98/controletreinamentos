from __future__ import annotations

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.api.http.relatorios import routes as relatorios_api


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
        "id": 51,
        "nome": "Operador Relatorios",
        "login": "rel_api",
        "email": "rel.api@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": '["relatorio_habilitacoes:view","relatorio_produtividade:view"]',
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
        json={"login": "rel_api", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 200


def test_api_relatorios_habilitacoes_returns_filterable_report_without_visual_fields(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        relatorios_api,
        "get_habilitacoes_report_data",
        lambda _db, **_kwargs: {
            "emitted_at": "02/04/2026 12:00",
            "summary": {"total_tripulantes": 2, "total_habilitacoes": 3, "total_em_dia": 1, "total_vencer_90": 1, "total_vencer_60": 1, "total_vencer_30": 1, "total_critico_15": 1, "total_vencido": 1},
            "filters": {"nome": "", "base": "SSA", "status": "vencido", "tipo": "", "ordenacao": "criticidade"},
            "options": {"status": [{"key": "vencido", "label": "Vencido"}], "tipos": [{"id": 2, "nome": "CQ IFR"}], "bases": [{"nome": "SSA"}]},
            "items": [
                {
                    "tripulante_id": 7,
                    "tripulante_nome": "Lucas Silva",
                    "base": "SSA",
                    "funcao_cargo": "",
                    "habilitacoes": [
                        {
                            "treinamento_id": 55,
                            "tipo_treinamento_id": 2,
                            "habilitacao_nome": "CQ IFR",
                            "data_vencimento": "02/04/2026",
                            "days_remaining": -1,
                            "days_remaining_label": "Vencida há 1 dia(s)",
                            "status_key": "vencido",
                            "status_label": "Vencido",
                            "pulse": True,
                            "is_placeholder": False,
                        }
                    ],
                }
            ],
        },
    )
    monkeypatch.setattr(relatorios_api, "get_db", lambda: object())

    response = client.get("/api/v1/relatorios/habilitacoes?base=SSA&status=vencido")

    assert response.status_code == 200
    payload = response.get_json()
    item = payload["report"]["items"][0]["habilitacoes"][0]
    assert payload["code"] == "relatorio_habilitacoes_ok"
    assert payload["report"]["emitted_at"] == "02/04/2026 12:00"
    assert item["status_key"] == "vencido"
    assert "status_class" not in item


def test_api_relatorios_produtividade_returns_table_data_and_filters(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        relatorios_api,
        "get_produtividade_report_data",
        lambda _db, **_kwargs: {
            "competencia": "2026-04",
            "competencia_label": "Abril/2026",
            "emitted_at": "02/04/2026 12:00",
            "filters": {"nome": "", "base": "", "funcao": "", "categoria": "", "ordenacao": "valor_final"},
            "options": {"competencias": ["2026-04"], "bases": ["SSA"], "funcoes": ["Comandante"], "categorias": ["Piloto"]},
            "summary": {"valor_total_mes": 1000.0},
            "items": [
                {
                    "tripulante_id": 7,
                    "tripulante_nome": "Lucas Silva",
                    "base": "SSA",
                    "categoria": "Piloto",
                    "funcao": "Comandante",
                    "total_missoes_validas": 4,
                    "total_pernoites": 2,
                    "piso_minimo_mensal": 500.0,
                    "total_produtividade": 5.0,
                    "valor_final_mes": 1000.0,
                    "criterio_fechamento": "Mensal",
                    "conferencia": None,
                }
            ],
        },
    )
    monkeypatch.setattr(relatorios_api, "get_db", lambda: object())

    response = client.get("/api/v1/relatorios/produtividade?competencia=2026-04")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == "relatorio_produtividade_ok"
    assert payload["report"]["items"][0]["tripulante_id"] == 7


def test_api_relatorios_produtividade_conferencias_marks_row(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        relatorios_api,
        "set_produtividade_conferencia",
        lambda _db, **kwargs: {
            "operation": "marked",
            "message": "Conferência registrada com sucesso.",
            "conferencia": {
                "tripulante_id": kwargs["tripulante_id"],
                "competencia": kwargs["competencia"],
                "conferido_por": kwargs["user_id"],
                "conferido_por_nome": "Operador Relatorios",
                "conferido_em": "2026-04-02T12:00:00",
            },
        },
    )
    monkeypatch.setattr(relatorios_api, "get_db", lambda: object())

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/relatorios/produtividade/conferencias",
        json={"tripulante_id": 7, "competencia": "2026-04", "action": "mark"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == "produtividade_conferencia_saved"
    assert payload["operation"] == "marked"
    assert payload["conferencia"]["tripulante_id"] == 7
