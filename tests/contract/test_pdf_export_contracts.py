from __future__ import annotations

from datetime import datetime

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.blueprints.admin import routes as admin_routes
from backend.src.controle_treinamentos.blueprints.admin import routes_operacional
from backend.src.controle_treinamentos.blueprints.cadastros import routes_treinamentos, routes_tripulante_views


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


class _NoopAuditDB:
    def __init__(self):
        self.conn = self
        self.commits = 0
        self.rollbacks = 0

    def execute(self, _query, _params=None):
        return _SingleCursor()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class _AuditExportDB(_NoopAuditDB):
    def __init__(self, rows):
        super().__init__()
        self._rows = rows

    def execute(self, _query, _params=None):
        return _SingleCursor(rows=self._rows)


class _TripulanteLookupDB(_NoopAuditDB):
    def __init__(self, row):
        super().__init__()
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
        "permissao_modulos_json": '["dashboard:view","auditoria:view","relatorio_habilitacoes:view","monitoramento:view"]',
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

    monkeypatch.setattr(
        admin_routes,
        "get_db",
        lambda: _AuditExportDB(
            [
                {
                    "id": 1,
                    "entidade": "usuario",
                    "acao": "create",
                    "entidade_id": 9,
                    "realizado_por": 41,
                    "realizado_por_nome": "Operador PDF",
                    "realizado_por_login": "export_pdf_contracts",
                    "payload_anterior": None,
                    "payload_novo": {"nome": "Novo Usuario"},
                    "observacao": "Criado manualmente",
                    "realizado_em": datetime(2026, 4, 3, 10, 30),
                }
            ]
        ),
    )
    monkeypatch.setattr(admin_routes, "build_auditoria_pdf", lambda **_kwargs: b"%PDF-auditoria\n%%EOF")

    response = client.get("/auditoria/export.pdf?entidade=usuario", follow_redirects=False)

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.get_data() == b"%PDF-auditoria\n%%EOF"
    assert "attachment; filename=" in (response.headers.get("Content-Disposition", "") or "")
    assert response.headers.get("Cache-Control") == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Document-Policy"] == "auditoria_export_pdf"
    assert response.headers["X-Document-Kind"] == "pdf_export"
    assert response.headers["X-Document-Storage"] == "temporary_response"


def test_user_guide_pdf_returns_temporary_document_policy(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(routes_operacional, "build_user_guide_pdf", lambda **_kwargs: b"%PDF-user-guide\n%%EOF")
    monkeypatch.setattr(routes_operacional, "audit_document_generation", lambda **_kwargs: None)

    response = client.get("/manual/usuario.pdf", follow_redirects=False)

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.get_data() == b"%PDF-user-guide\n%%EOF"
    assert response.headers.get("Cache-Control") == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Document-Policy"] == "user_guide_pdf"
    assert response.headers["X-Document-Kind"] == "temporary_document"
    assert response.headers["X-Document-Storage"] == "temporary_response"


def test_habilitacoes_export_pdf_returns_real_pdf(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(routes_treinamentos, "get_db", lambda: object())
    monkeypatch.setattr(routes_treinamentos, "audit_document_generation", lambda **_kwargs: None)
    captured_pdf_kwargs = {}
    monkeypatch.setattr(
        routes_treinamentos,
        "get_habilitacoes_report_data",
        lambda *_args, **_kwargs: {
            "emitted_at": "02/04/2026 12:00",
            "summary": {"total_tripulantes": 1, "total_habilitacoes": 2},
            "filters": {"nome": "", "base": "SSA", "status": "vencido", "tipo": "", "ordenacao": "vencimento"},
            "options": {
                "status": [{"key": "vencido", "label": "Vencido", "badge_class": "status-critical"}],
                "tipos": [{"id": 2, "nome": "CQ IFR"}],
                "bases": [{"nome": "SSA", "uf": "BA"}],
            },
            "items": [
                {
                    "tripulante_id": 7,
                    "tripulante_nome": "Lucas Silva",
                    "base": "SSA",
                    "funcao_cargo": "Comandante",
                    "habilitacoes": [
                        {
                            "treinamento_id": 55,
                            "tipo_treinamento_id": 2,
                            "habilitacao_nome": "Recurrent",
                            "data_vencimento": "10/10/2026",
                            "days_remaining": 190,
                            "days_remaining_label": "190 dias",
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

    def _build_habilitacoes_pdf(**kwargs):
        captured_pdf_kwargs["kwargs"] = kwargs
        return b"%PDF-habilitacoes\n%%EOF"

    monkeypatch.setattr(routes_treinamentos, "build_habilitacoes_consolidado_pdf", _build_habilitacoes_pdf)

    response = client.get(
        "/treinamentos/consolidado/export.pdf?base=SSA&status=vencido&ordenacao=vencimento",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.get_data() == b"%PDF-habilitacoes\n%%EOF"
    assert captured_pdf_kwargs["kwargs"]["emitted_at"] == "02/04/2026 12:00"
    assert captured_pdf_kwargs["kwargs"]["filtros_aplicados"] == {
        "nome": "-",
        "base": "SSA",
        "status": "vencido",
        "tipo": "-",
        "ordenacao": "vencimento",
    }
    assert captured_pdf_kwargs["kwargs"]["tripulantes_grouped"][0]["base"] == "SSA"
    assert captured_pdf_kwargs["kwargs"]["tripulantes_grouped"][0]["habilitacoes"][0]["status_class"] == "status-critical"
    assert "attachment; filename=" in (response.headers.get("Content-Disposition", "") or "")
    assert response.headers.get("Cache-Control") == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Document-Policy"] == "habilitacoes_export_pdf"
    assert response.headers["X-Document-Kind"] == "pdf_export"
    assert response.headers["X-Document-Layout"] == "reportlab.a4.branded.v1"
    assert response.headers["X-Document-Signature"] == "unsigned_system_generated"


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
    monkeypatch.setattr(routes_tripulante_views, "build_tripulante_treinamentos_pdf", lambda **_kwargs: b"%PDF-tripulante\n%%EOF")

    response = client.get("/tripulantes/7/relatorio/export.pdf", follow_redirects=False)

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.get_data() == b"%PDF-tripulante\n%%EOF"
    assert "attachment; filename=" in (response.headers.get("Content-Disposition", "") or "")
    assert response.headers.get("Cache-Control") == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Document-Policy"] == "tripulante_treinamentos_export_pdf"
    assert response.headers["X-Document-Kind"] == "pdf_export"
