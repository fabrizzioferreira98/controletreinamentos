from __future__ import annotations

from datetime import datetime

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.blueprints.admin import routes as admin_routes
from backend.src.controle_treinamentos.blueprints.cadastros import routes_treinamentos, routes_tripulante_views
from backend.src.controle_treinamentos.blueprints.relatorios import routes as relatorios_routes


class _SingleCursor:
    def __init__(self, *, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _SingleUserDB:
    def __init__(self, row):
        self._row = row

    def execute(self, _query, _params):
        return _SingleCursor(row=self._row)


class _AuditExportDB:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _query, _params=None):
        return _SingleCursor(rows=self._rows)


class _TripulanteLookupDB:
    def __init__(self, row):
        self._row = row

    def execute(self, _query, _params=None):
        return _SingleCursor(row=self._row)


def _auth_user_row():
    return {
        "id": 41,
        "nome": "Operador PDF",
        "login": "export_pdf_contracts",
        "email": "export.pdf@local.test",
        "perfil": "gestora",
        "ativo": 1,
        "permissao_modulos_json": (
            '["dashboard:view","auditoria:view","relatorio_habilitacoes:view",'
            '"relatorio_produtividade:view"]'
        ),
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
        json={"login": "export_pdf_contracts", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 200


def test_auditoria_export_pdf_returns_real_pdf(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(admin_routes, "get_db", lambda: _AuditExportDB([
        {
            "id": 1,
            "entidade": "usuario",
            "acao": "create",
            "entidade_id": 9,
            "realizado_por": 41,
            "realizado_por_nome": "Operador PDF",
            "realizado_por_login": "export_pdf_contracts",
            "payload_anterior": None,
            "payload_novo": {"nome": "Novo Usuário"},
            "observacao": "Criado manualmente",
            "realizado_em": datetime(2026, 4, 3, 10, 30),
        }
    ]))
    monkeypatch.setattr(admin_routes, "build_auditoria_pdf", lambda **_kwargs: b"%PDF-auditoria")

    response = client.get("/auditoria/export.pdf?entidade=usuario", follow_redirects=False)

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.get_data() == b"%PDF-auditoria"
    assert "attachment; filename=" in (response.headers.get("Content-Disposition", "") or "")
    assert response.headers.get("Cache-Control") == "no-store"


def test_habilitacoes_export_pdf_returns_real_pdf(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(routes_treinamentos, "get_db", lambda: object())
    monkeypatch.setattr(
        routes_treinamentos,
        "build_habilitacoes_consolidadas_context",
        lambda *_args, **_kwargs: {
            "summary": {"total_tripulantes": 1, "total_habilitacoes": 2},
            "tripulantes_grouped": [
                {
                    "tripulante_nome": "Lucas Silva",
                    "base": "SP",
                    "funcao_cargo": "Comandante",
                    "habilitacoes": [
                        {
                            "habilitacao_nome": "Recurrent",
                            "data_vencimento": "10/10/2026",
                            "days_remaining_label": "190 dias",
                            "status_label": "Regular",
                            "status_key": "em_dia",
                        }
                    ],
                }
            ],
        },
    )
    monkeypatch.setattr(routes_treinamentos, "build_habilitacoes_consolidado_pdf", lambda **_kwargs: b"%PDF-habilitacoes")

    response = client.get("/treinamentos/consolidado/export.pdf?status=regular", follow_redirects=False)

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.get_data() == b"%PDF-habilitacoes"
    assert "attachment; filename=" in (response.headers.get("Content-Disposition", "") or "")
    assert response.headers.get("Cache-Control") == "no-store"


def test_produtividade_export_pdf_returns_real_pdf(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(relatorios_routes, "get_db", lambda: object())
    monkeypatch.setattr(
        relatorios_routes,
        "calculate_competencia_consolidada",
        lambda *_args, **_kwargs: {
            "competencia": "2026-04",
            "summary": {
                "total_tripulantes": 1,
                "total_missoes": 3,
                "total_pernoites": 2,
                "total_pago_piso": 0,
                "total_pago_produtividade": 1250,
                "valor_total_consolidado": 1250,
            },
            "rows": [
                {
                    "tripulante_nome": "Lucas Silva",
                    "base": "SP",
                    "total_missoes_validas": 3,
                    "total_pernoites_cobertura": 1,
                    "total_pernoites_operacionais_elegiveis": 1,
                    "total_produtividade": 1250,
                    "valor_final_mes": 1250,
                    "criterio_fechamento": "produtividade",
                }
            ],
        },
    )
    monkeypatch.setattr(relatorios_routes, "build_produtividade_consolidado_pdf", lambda **_kwargs: b"%PDF-produtividade")

    response = client.get("/produtividade/export.pdf?competencia=2026-04", follow_redirects=False)

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.get_data() == b"%PDF-produtividade"
    assert "attachment; filename=" in (response.headers.get("Content-Disposition", "") or "")
    assert response.headers.get("Cache-Control") == "no-store"


def test_produtividade_tripulante_export_pdf_returns_real_pdf(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        routes_tripulante_views,
        "get_db",
        lambda: _TripulanteLookupDB(
            {
                "id": 7,
                "nome": "Lucas Silva",
                "base": "SP",
                "funcao_operacional": "comandante",
                "categoria_operacional": "A",
                "sdea_ativo": True,
                "instrutor_ativo": False,
                "checador_ativo": False,
                "elegivel_adicional_excepcional": False,
            }
        ),
    )
    monkeypatch.setattr(
        routes_tripulante_views,
        "calculate_tripulante_competencia",
        lambda *_args, **_kwargs: {
            "tripulante_nome": "Lucas Silva",
            "base": "SP",
            "funcao": "comandante",
            "categoria": "A",
            "piso_minimo_mensal": 1000,
            "total_produtividade": 1500,
            "valor_final_mes": 1500,
            "criterio_fechamento": "produtividade",
        },
    )
    monkeypatch.setattr(routes_tripulante_views, "build_produtividade_tripulante_pdf", lambda **_kwargs: b"%PDF-prod-trip")

    response = client.get("/produtividade/tripulantes/7/export.pdf?competencia=2026-04", follow_redirects=False)

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.get_data() == b"%PDF-prod-trip"
    assert "attachment; filename=" in (response.headers.get("Content-Disposition", "") or "")
    assert response.headers.get("Cache-Control") == "no-store"


def test_tripulante_report_export_pdf_returns_real_pdf(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        routes_tripulante_views,
        "get_db",
        lambda: _TripulanteLookupDB(
            {
                "id": 7,
                "nome": "Lucas Silva",
                "cpf": "12345678901",
                "licenca_anac": "ANAC123",
                "email": "lucas@local.test",
                "telefone": "11999999999",
                "base": "SP",
                "status": "Ativo",
                "possui_foto": False,
            }
        ),
    )
    monkeypatch.setattr(
        routes_tripulante_views,
        "fetch_training_rows",
        lambda *_args, **_kwargs: [
            {
                "equipamento_nome": "King Air",
                "tipo_treinamento_nome": "Recurrent",
                "data_realizacao": "2026-04-01",
                "data_vencimento": "2027-04-01",
                "status_calculado": "regular",
                "observacao": "OK",
            }
        ],
    )
    monkeypatch.setattr(routes_tripulante_views, "summarize_training_status", lambda _rows: {"total": 1, "vencido": 0, "a vencer": 0, "regular": 1})
    monkeypatch.setattr(routes_tripulante_views, "build_tripulante_treinamentos_pdf", lambda **_kwargs: b"%PDF-tripulante")

    response = client.get("/tripulantes/7/relatorio/export.pdf", follow_redirects=False)

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.get_data() == b"%PDF-tripulante"
    assert "attachment; filename=" in (response.headers.get("Content-Disposition", "") or "")
    assert response.headers.get("Cache-Control") == "no-store"
