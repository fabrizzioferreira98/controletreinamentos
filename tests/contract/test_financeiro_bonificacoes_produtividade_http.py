from __future__ import annotations

import json

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.api.http.financeiro import routes as financeiro_routes
from backend.src.controle_treinamentos.application.financeiro_bonificacoes import (
    BonificacaoProdutividadeNaoEncontradaErro,
)
from backend.src.controle_treinamentos.auth import FINANCE_PERMISSION_KEYS
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT


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


def _auth_user_row(*, permissions, login: str = "finance_productivity_http_user"):
    return {
        "id": 901,
        "nome": "Finance Productivity HTTP User",
        "login": login,
        "email": f"{login}@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": json.dumps(sorted(permissions)),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch, *, permissions, login: str = "finance_productivity_http_user") -> str:
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


def _headers(*, request_id: str = "finance-productivity-http") -> dict:
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


def _calculation_response(**overrides):
    payload = {
        "id": 10,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "competencia": "2026-04",
        "tripulante_id": 101,
        "tripulante": {"id": 101, "nome": "Comandante Um"},
        "funcao": "comandante",
        "categoria_aplicavel": "categoria a",
        "valor_icao": "0.00",
        "valor_instrutor": "0.00",
        "valor_checador": "0.00",
        "valor_missoes_categoria_a": "120.00",
        "valor_missoes_categoria_b": "0.00",
        "valor_cobertura_base": "0.00",
        "valor_pernoite_comum": "0.00",
        "valor_excecao_palmas": "0.00",
        "produtividade_calculada": "120.00",
        "garantia_minima": "100.00",
        "total_devido": "120.00",
        "status": "calculado",
        "memoria_calculo": {"steps": [{"rule_key": "produtividade_calculada"}]},
        "parametros_usados": [{"tipo": "missao_categoria_a", "valor": "120.00", "unidade": "valor"}],
    }
    payload.update(overrides)
    return payload


def test_productivity_bonus_endpoints_require_authentication_and_permission(monkeypatch):
    app = create_app()
    anonymous = app.test_client()

    response = anonymous.get("/api/v1/financeiro/bonificacoes/produtividade", headers=_headers())
    payload = _assert_envelope(response, status=401, success=False)
    assert payload["code"] == "auth_required"

    no_scope_client = app.test_client()
    _authenticate_client(
        no_scope_client,
        monkeypatch,
        permissions={"dashboard:view"},
        login="finance_productivity_no_scope",
    )
    response = no_scope_client.get(
        "/api/v1/financeiro/bonificacoes/produtividade/101",
        headers=_headers(request_id="finance-productivity-forbidden"),
    )
    payload = _assert_envelope(response, status=403, success=False)
    assert payload["code"] == "forbidden"


def test_productivity_bonus_http_endpoints_delegate_to_use_cases_and_return_envelope(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_productivity_authorized",
    )
    calls = []

    def _list_productivity(**kwargs):
        calls.append(("list", kwargs))
        return {
            "items": [_calculation_response()],
            "pagination": {"page": kwargs["page"], "offset": kwargs["offset"], "total": 1},
        }

    def _detail_productivity(tripulante_id, **kwargs):
        calls.append(("detail", tripulante_id, kwargs))
        return _calculation_response(tripulante_id=tripulante_id)

    monkeypatch.setattr(financeiro_routes, "listar_bonificacoes_produtividade", _list_productivity)
    monkeypatch.setattr(financeiro_routes, "detalhar_bonificacao_produtividade_por_tripulante", _detail_productivity)

    list_response = client.get(
        "/api/v1/financeiro/bonificacoes/produtividade?competencia=2026-04&tripulante_id=101&funcao=comandante&status=calculado",
        headers=_headers(request_id="finance-productivity-list"),
    )
    list_payload = _assert_envelope(list_response, status=200, success=True)
    assert list_payload["items"][0]["produtividade_calculada"] == "120.00"
    assert list_payload["items"][0]["total_devido"] == "120.00"

    detail_response = client.get(
        "/api/v1/financeiro/bonificacoes/produtividade/101?competencia=2026-04&funcao=comandante",
        headers=_headers(request_id="finance-productivity-detail"),
    )
    detail_payload = _assert_envelope(detail_response, status=200, success=True)
    assert detail_payload["calculation"]["memoria_calculo"]["steps"][0]["rule_key"] == "produtividade_calculada"

    assert calls[0][0] == "list"
    assert calls[0][1]["competencia"] == "2026-04"
    assert calls[0][1]["tripulante_id"] == 101
    assert calls[0][1]["funcao"] == "comandante"
    assert calls[1] == (
        "detail",
        101,
        {"competencia": "2026-04", "funcao": "comandante"},
    )


def test_productivity_bonus_detail_translates_not_found(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_productivity_not_found",
    )

    def _not_found(_tripulante_id, **_kwargs):
        raise BonificacaoProdutividadeNaoEncontradaErro()

    monkeypatch.setattr(financeiro_routes, "detalhar_bonificacao_produtividade_por_tripulante", _not_found)

    response = client.get(
        "/api/v1/financeiro/bonificacoes/produtividade/404",
        headers=_headers(request_id="finance-productivity-not-found"),
    )
    payload = _assert_envelope(response, status=404, success=False)
    assert payload["code"] == "bonificacao_produtividade_nao_encontrada"


def test_productivity_general_report_json_and_pdf_endpoints_delegate_and_validate_pdf(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_productivity_general_report",
    )
    calls = []

    report_payload = {
        "competencia": "2026-04",
        "funcao": "comandante",
        "titulo": "RELATÓRIO GERAL DE PRODUTIVIDADE - COMANDANTES",
        "totais": {
            "tripulantes": 1,
            "total_produtividade": "280.00",
            "possui_pendencias": False,
        },
        "items": [
            {
                "tripulante_id": 101,
                "nome": "Comandante Um",
                "funcao": "comandante",
                "total_produtividade": "280.00",
            }
        ],
        "pendencias": [],
        "contexto": {
            "competencia": "2026-04",
            "funcao": "comandante",
            "org_id": FINANCE_ORG_SCOPE_DEFAULT,
            "usa_preview": False,
        },
        "filters": {
            "competencia": "2026-04",
            "funcao": "comandante",
            "org_id": FINANCE_ORG_SCOPE_DEFAULT,
            "incluir_zerados": True,
        },
    }

    def _general_report(**kwargs):
        calls.append(("json", kwargs))
        return report_payload

    def _general_report_pdf(**kwargs):
        calls.append(("pdf", kwargs))
        return {
            "content": b"%PDF-1.4\n% productivity general report\n%%EOF\n",
            "filename": "relatorio-geral-produtividade-comandantes-2026-04.pdf",
            "mimetype": "application/pdf",
        }

    monkeypatch.setattr(financeiro_routes, "consolidar_relatorio_geral_produtividade", _general_report)
    monkeypatch.setattr(financeiro_routes, "exportar_relatorio_geral_produtividade_pdf", _general_report_pdf)

    json_response = client.get(
        "/api/v1/financeiro/produtividade/relatorio-geral?competencia=2026-04&funcao=comandante",
        headers=_headers(request_id="finance-productivity-general-json"),
    )
    json_payload = _assert_envelope(json_response, status=200, success=True)
    assert json_payload["titulo"] == "RELATÓRIO GERAL DE PRODUTIVIDADE - COMANDANTES"
    assert json_payload["items"][0]["total_produtividade"] == "280.00"

    pdf_response = client.get(
        "/api/v1/financeiro/produtividade/relatorio-geral.pdf?competencia=2026-04&funcao=comandante",
        headers=_headers(request_id="finance-productivity-general-pdf"),
    )
    assert pdf_response.status_code == 200
    assert pdf_response.content_type == "application/pdf"
    assert pdf_response.data.startswith(b"%PDF")
    assert b"%%EOF" in pdf_response.data[-4096:]
    assert (
        pdf_response.headers["Content-Disposition"]
        == 'attachment; filename="relatorio-geral-produtividade-comandantes-2026-04.pdf"'
    )
    assert pdf_response.headers["X-Document-Policy"] == "finance_productivity_general_report_pdf"

    assert calls[0] == (
        "json",
        {
            "competencia": "2026-04",
            "funcao": "comandante",
            "org_id": None,
            "incluir_zerados": True,
            "categoria": None,
        },
    )
    assert calls[1][0] == "pdf"
    assert calls[1][1]["competencia"] == "2026-04"
    assert calls[1][1]["funcao"] == "comandante"
    assert calls[1][1]["source_endpoint"] == "/api/v1/financeiro/produtividade/relatorio-geral.pdf"


