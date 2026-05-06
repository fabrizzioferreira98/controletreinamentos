from __future__ import annotations

import json

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.api.http.financeiro import routes as financeiro_routes
from backend.src.controle_treinamentos.auth import FINANCE_PERMISSION_KEYS


class _SingleCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _SingleUserDB:
    def __init__(self, row):
        self._row = row

    def execute(self, _query, _params=None):
        return _SingleCursor(self._row)


def _auth_user_row(*, permissions, login: str = "finance_individual_report_user"):
    return {
        "id": 951,
        "nome": "Finance Individual Report User",
        "login": login,
        "email": f"{login}@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": json.dumps(sorted(permissions)),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch, *, permissions, login: str = "finance_individual_report_user") -> str:
    fake_db = _SingleUserDB(_auth_user_row(permissions=permissions, login=login))
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": login, "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 200
    return client.get("/api/v1/session").get_json()["csrf_token"]


def _headers(*, request_id: str = "finance-individual-report") -> dict:
    return {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-Request-ID": request_id,
        "X-Correlation-ID": f"{request_id}-correlation",
    }


def _assert_envelope(response, *, status: int, success: bool):
    assert response.status_code == status
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["success"] is success
    assert payload["status"] == status
    assert payload["code"]
    assert payload["message"]
    assert payload["request_id"]
    assert payload["correlation_id"]
    return payload


def test_individual_report_requires_authentication_and_export_permission(monkeypatch):
    app = create_app()
    anonymous = app.test_client()

    response = anonymous.get(
        "/api/v1/financeiro/relatorios/individual.pdf?tipo=horaria&competencia=2026-04&tripulante_id=135",
        headers=_headers(request_id="individual-report-anonymous"),
    )
    payload = _assert_envelope(response, status=401, success=False)
    assert payload["code"] == "auth_required"

    no_scope_client = app.test_client()
    _authenticate_client(
        no_scope_client,
        monkeypatch,
        permissions={"finance:bonuses:read"},
        login="finance_individual_report_no_export",
    )
    response = no_scope_client.get(
        "/api/v1/financeiro/relatorios/individual.pdf?tipo=horaria&competencia=2026-04&tripulante_id=135",
        headers=_headers(request_id="individual-report-forbidden"),
    )
    payload = _assert_envelope(response, status=403, success=False)
    assert payload["code"] == "forbidden"


def test_individual_report_streams_pdf_and_delegates_query_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_individual_report_authorized",
    )
    calls = []

    def _report(**kwargs):
        calls.append(kwargs)
        return {
            "content": b"%PDF-individual\n%%EOF",
            "filename": "relatorio-bonificacao-horaria-2026-04-comandante-qa.pdf",
            "mimetype": "application/pdf",
        }

    monkeypatch.setattr(financeiro_routes, "gerar_relatorio_financeiro_individual_pdf", _report)

    response = client.get(
        "/api/v1/financeiro/relatorios/individual.pdf?tipo=horaria&competencia=2026-04&tripulante_id=135&funcao=comandante",
        headers={**_headers(request_id="individual-report-ok"), "Accept": "application/pdf"},
    )

    assert response.status_code == 200
    assert response.content_type.startswith("application/pdf")
    assert response.data == b"%PDF-individual\n%%EOF"
    assert response.headers["Content-Length"] == str(len(b"%PDF-individual\n%%EOF"))
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Document-Policy"] == "finance_individual_report_pdf"
    assert "relatorio-bonificacao-horaria-2026-04-comandante-qa.pdf" in response.headers["Content-Disposition"]
    assert calls == [
        {
            "tipo": "horaria",
            "competencia": "2026-04",
            "tripulante_id": 135,
            "funcao": "comandante",
            "status": None,
            "incluir_obsoletos": False,
            "actor_user_id": 951,
            "request_id": "individual-report-ok",
            "correlation_id": "individual-report-ok-correlation",
            "source_endpoint": "/api/v1/financeiro/relatorios/individual.pdf",
        }
    ]


def test_journey_grid_pdf_streams_closed_response_with_content_length(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_journey_grid_pdf_authorized",
    )
    calls = []
    pdf_bytes = b"%PDF-grid\n%%EOF"

    def _report(**kwargs):
        calls.append(kwargs)
        return {
            "content": pdf_bytes,
            "filename": "lancamentos-jornada-2026-04.pdf",
            "mimetype": "application/pdf",
        }

    monkeypatch.setattr(financeiro_routes, "exportar_grade_jornada_pdf", _report)

    response = client.get(
        "/api/v1/financeiro/lancamentos-jornada.pdf?competencia=2026-04",
        headers={**_headers(request_id="journey-grid-pdf-ok"), "Accept": "application/pdf"},
    )

    assert response.status_code == 200
    assert response.content_type.startswith("application/pdf")
    assert response.data == pdf_bytes
    assert response.headers["Content-Length"] == str(len(pdf_bytes))
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Document-Policy"] == "finance_journey_grid_pdf"
    assert "lancamentos-jornada-2026-04.pdf" in response.headers["Content-Disposition"]
    assert calls == [
        {
            "competencia": "2026-04",
            "funcao": None,
            "tripulante_id": None,
            "status": None,
            "actor_user_id": 951,
            "request_id": "journey-grid-pdf-ok",
            "correlation_id": "journey-grid-pdf-ok-correlation",
            "source_endpoint": "/api/v1/financeiro/lancamentos-jornada.pdf",
        }
    ]


def test_period_extract_pdf_streams_closed_response_with_content_length(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_extract_pdf_authorized",
    )
    calls = []
    pdf_bytes = b"%PDF-extract\n%%EOF"

    def _report(**kwargs):
        calls.append(kwargs)
        return {
            "content": pdf_bytes,
            "filename": "extrato-periodo-2026-04-01-2026-04-30.pdf",
            "mimetype": "application/pdf",
        }

    monkeypatch.setattr(financeiro_routes, "exportar_extrato_periodo_pdf", _report)

    response = client.get(
        "/api/v1/financeiro/extrato-periodo.pdf?data_inicio=2026-04-01&data_fim=2026-04-30&tipo=ambos",
        headers={**_headers(request_id="period-extract-pdf-ok"), "Accept": "application/pdf"},
    )

    assert response.status_code == 200
    assert response.content_type.startswith("application/pdf")
    assert response.data == pdf_bytes
    assert response.headers["Content-Length"] == str(len(pdf_bytes))
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Document-Policy"] == "finance_period_extract_pdf"
    assert "extrato-periodo-2026-04-01-2026-04-30.pdf" in response.headers["Content-Disposition"]
    assert calls == [
        {
            "data_inicio": "2026-04-01",
            "data_fim": "2026-04-30",
            "tripulante_id": None,
            "funcao": None,
            "tipo": "ambos",
            "actor_user_id": 951,
            "request_id": "period-extract-pdf-ok",
            "correlation_id": "period-extract-pdf-ok-correlation",
        }
    ]


def test_individual_report_rejects_invalid_pdf_payload_without_disguised_download(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_individual_report_invalid_pdf",
    )

    def _report(**_kwargs):
        return {
            "content": b'{"success":false}',
            "filename": "relatorio-bonificacao-horaria-2026-04.pdf",
            "mimetype": "application/pdf",
        }

    monkeypatch.setattr(financeiro_routes, "gerar_relatorio_financeiro_individual_pdf", _report)

    response = client.get(
        "/api/v1/financeiro/relatorios/individual.pdf?tipo=horaria&competencia=2026-04&tripulante_id=135&funcao=comandante",
        headers={**_headers(request_id="individual-report-invalid-pdf"), "Accept": "application/pdf"},
    )

    payload = _assert_envelope(response, status=500, success=False)
    assert payload["code"] == "finance_individual_report_pdf_invalid_signature"
    assert response.content_type.startswith("application/json")


def test_individual_report_rejects_invalid_query_without_calling_service(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_individual_report_invalid",
    )
    calls = []
    monkeypatch.setattr(financeiro_routes, "gerar_relatorio_financeiro_individual_pdf", lambda **kwargs: calls.append(kwargs))

    invalid_type = client.get(
        "/api/v1/financeiro/relatorios/individual.pdf?tipo=consolidado&competencia=2026-04&tripulante_id=135",
        headers=_headers(request_id="individual-report-invalid-type"),
    )
    payload = _assert_envelope(invalid_type, status=400, success=False)
    assert payload["code"] == "finance_individual_report_invalid_type"

    invalid_competencia = client.get(
        "/api/v1/financeiro/relatorios/individual.pdf?tipo=produtividade&competencia=abril&tripulante_id=135",
        headers=_headers(request_id="individual-report-invalid-competencia"),
    )
    payload = _assert_envelope(invalid_competencia, status=400, success=False)
    assert payload["code"] == "finance_invalid_competence"

    missing_tripulante = client.get(
        "/api/v1/financeiro/relatorios/individual.pdf?tipo=produtividade&competencia=2026-04",
        headers=_headers(request_id="individual-report-missing-tripulante"),
    )
    payload = _assert_envelope(missing_tripulante, status=400, success=False)
    assert payload["code"] == "finance_individual_report_tripulante_required"
    assert calls == []
