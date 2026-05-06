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


def _auth_user_row(*, permissions, login: str) -> dict:
    return {
        "id": 997,
        "nome": "Finance Preflight User",
        "login": login,
        "email": f"{login}@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": json.dumps(sorted(permissions)),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch, *, permissions, login: str) -> str:
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


def _headers(*, csrf_token: str | None = None, request_id: str = "finance-preflight-http") -> dict:
    headers = {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-Request-ID": request_id,
        "X-Correlation-ID": f"{request_id}-correlation",
    }
    if csrf_token:
        headers["X-CSRFToken"] = csrf_token
    return headers


def _assert_envelope(response, *, status: int, success: bool) -> dict:
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


def _sample_preflight(*, calculavel: bool, fechavel: bool = False) -> dict:
    return {
        "calculavel": calculavel,
        "fechavel": fechavel,
        "competencia_status": "em_conferencia",
        "missao_status": "ativa",
        "bloqueios": [] if calculavel else [{"code": "blocked", "next_action": "corrigir"}],
        "avisos": [],
        "parametros_faltantes": [],
        "parametros_invalidos": [],
        "parametros_nao_elegiveis": [],
        "parametros_ambiguos": [],
        "dados_qa_detectados": [],
        "divergencias": [],
        "next_action": "ok" if calculavel else "corrigir",
        "can_execute_actions": {
            "recalcular_missao": calculavel,
            "recalcular_competencia": calculavel,
            "fechar_competencia": fechavel,
            "gerar_pdf_previa": True,
            "gerar_pdf_fechamento": fechavel,
        },
    }


def test_preflight_endpoints_require_authentication_and_permission(monkeypatch):
    app = create_app()
    anonymous = app.test_client()

    mission_response = anonymous.get("/api/v1/financeiro/missoes/10/preflight-calculo", headers=_headers())
    mission_payload = _assert_envelope(mission_response, status=401, success=False)
    assert mission_payload["code"] == "auth_required"

    period_response = anonymous.get("/api/v1/financeiro/competencias/2026-04/preflight-calculo", headers=_headers())
    period_payload = _assert_envelope(period_response, status=401, success=False)
    assert period_payload["code"] == "auth_required"

    no_scope_client = app.test_client()
    csrf_token = _authenticate_client(
        no_scope_client,
        monkeypatch,
        permissions={"dashboard:view"},
        login="finance_preflight_no_scope",
    )
    forbidden_mission = no_scope_client.get(
        "/api/v1/financeiro/missoes/10/preflight-calculo",
        headers=_headers(csrf_token=csrf_token, request_id="preflight-mission-forbidden"),
    )
    forbidden_mission_payload = _assert_envelope(forbidden_mission, status=403, success=False)
    assert forbidden_mission_payload["code"] == "forbidden"

    forbidden_period = no_scope_client.get(
        "/api/v1/financeiro/competencias/2026-04/preflight-calculo",
        headers=_headers(csrf_token=csrf_token, request_id="preflight-period-forbidden"),
    )
    forbidden_period_payload = _assert_envelope(forbidden_period, status=403, success=False)
    assert forbidden_period_payload["code"] == "forbidden"


def test_preflight_endpoints_return_operational_data_envelope(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_preflight_authorized",
    )
    calls = []

    def _mission_preflight(mission_id, **kwargs):
        calls.append(("mission", mission_id, kwargs))
        return _sample_preflight(calculavel=True, fechavel=False)

    def _period_preflight(competencia, **kwargs):
        calls.append(("period", competencia, kwargs))
        return _sample_preflight(calculavel=True, fechavel=True)

    monkeypatch.setattr(financeiro_routes, "preflight_calculo_missao", _mission_preflight)
    monkeypatch.setattr(financeiro_routes, "preflight_calculo_competencia", _period_preflight)

    mission = client.get(
        "/api/v1/financeiro/missoes/10/preflight-calculo",
        headers=_headers(csrf_token=csrf_token, request_id="preflight-mission-ok"),
    )
    mission_payload = _assert_envelope(mission, status=200, success=True)
    assert mission_payload["code"] == "finance_mission_preflight_ok"
    assert mission_payload["data"]["calculavel"] is True
    assert mission_payload["data"]["next_action"] == "ok"

    period = client.get(
        "/api/v1/financeiro/competencias/2026-04/preflight-calculo",
        headers=_headers(csrf_token=csrf_token, request_id="preflight-period-ok"),
    )
    period_payload = _assert_envelope(period, status=200, success=True)
    assert period_payload["code"] == "finance_period_preflight_ok"
    assert period_payload["data"]["fechavel"] is True
    assert period_payload["data"]["can_execute_actions"]["fechar_competencia"] is True

    assert calls == [
        ("mission", 10, {}),
        ("period", "2026-04", {}),
    ]


def test_preflight_routes_do_not_call_mutation_use_cases(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_preflight_no_mutation",
    )
    mutation_calls = []

    monkeypatch.setattr(financeiro_routes, "preflight_calculo_missao", lambda *args, **kwargs: _sample_preflight(calculavel=False))
    monkeypatch.setattr(financeiro_routes, "preflight_calculo_competencia", lambda *args, **kwargs: _sample_preflight(calculavel=False))

    monkeypatch.setattr(
        financeiro_routes,
        "recalcular_missao_operacional",
        lambda *args, **kwargs: mutation_calls.append("recalcular_missao"),
    )
    monkeypatch.setattr(
        financeiro_routes,
        "recalcular_competencia_financeira",
        lambda *args, **kwargs: mutation_calls.append("recalcular_competencia"),
    )
    monkeypatch.setattr(
        financeiro_routes,
        "fechar_competencia_financeira",
        lambda *args, **kwargs: mutation_calls.append("fechar_competencia"),
    )

    response_mission = client.get(
        "/api/v1/financeiro/missoes/10/preflight-calculo",
        headers=_headers(csrf_token=csrf_token, request_id="preflight-no-mutation-mission"),
    )
    _assert_envelope(response_mission, status=200, success=True)

    response_period = client.get(
        "/api/v1/financeiro/competencias/2026-04/preflight-calculo",
        headers=_headers(csrf_token=csrf_token, request_id="preflight-no-mutation-period"),
    )
    _assert_envelope(response_period, status=200, success=True)

    assert mutation_calls == []
