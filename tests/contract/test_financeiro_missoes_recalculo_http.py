from __future__ import annotations

import json

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.api.http.financeiro import routes as financeiro_routes
from backend.src.controle_treinamentos.auth import FINANCE_PERMISSION_KEYS
from backend.src.controle_treinamentos.core.domain_errors import DomainConflictError


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


def _auth_user_row(*, permissions, login: str = "finance_recalc_http_user"):
    return {
        "id": 901,
        "nome": "Finance Recalc HTTP User",
        "login": login,
        "email": f"{login}@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": json.dumps(sorted(permissions)),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch, *, permissions, login: str = "finance_recalc_http_user") -> str:
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


def _headers(csrf_token: str | None = None, *, request_id: str = "finance-recalc-http") -> dict:
    headers = {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-Request-ID": request_id,
        "X-Correlation-ID": f"{request_id}-correlation",
    }
    if csrf_token:
        headers["X-CSRFToken"] = csrf_token
    return headers


def _assert_envelope(response, *, status: int, success: bool):
    assert response.status_code == status
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["success"] is success
    assert payload["status"] == status
    assert payload["code"]
    assert payload["message"]
    assert "request_id" in payload
    assert "correlation_id" in payload
    if status != 401:
        assert payload["request_id"]
        assert payload["correlation_id"]
    return payload


def _recalc_result():
    return {
        "mission": {
            "id": 10,
            "org_id": "default_single_tenant",
            "competencia": "2026-04",
            "status": "ativa",
        },
        "calculations": [
            {
                "id": 900,
                "mission_id": 10,
                "tripulante_id": 101,
                "funcao": "comandante",
                "jornada_total_minutos": 105,
                "minutos_diurnos": 0,
                "minutos_noturnos": 105,
                "minutos_noturnos_reais": 105,
                "horas_noturnas_convertidas": "2.0000",
                "valor_adicional_noturno": "200.00",
                "total": "200.00",
                "memoria_calculo": {"steps": [{"rule_key": "conversao_hora_noturna"}]},
                "parametros_usados": [{"tipo": "duracao_hora_noturna_minutos", "valor": "52.5"}],
                "calculation_version": "finance-hourly-v1",
            },
            {
                "id": 901,
                "mission_id": 10,
                "tripulante_id": 202,
                "funcao": "copiloto",
                "jornada_total_minutos": 105,
                "minutos_diurnos": 0,
                "minutos_noturnos": 105,
                "minutos_noturnos_reais": 105,
                "horas_noturnas_convertidas": "2.0000",
                "valor_adicional_noturno": "160.00",
                "total": "160.00",
                "memoria_calculo": {"steps": [{"rule_key": "conversao_hora_noturna"}]},
                "parametros_usados": [{"tipo": "duracao_hora_noturna_minutos", "valor": "52.5"}],
                "calculation_version": "finance-hourly-v1",
            },
        ],
        "mission_id": 10,
        "competence": "2026-04",
        "calculation_status": "calculado",
        "recalculated_at": "2026-05-04T14:30:00+00:00",
        "affected_calculations": [
            {"id": 900, "mission_id": 10, "tripulante_id": 101, "funcao": "comandante", "status": "calculado", "action": "updated"},
            {"id": 901, "mission_id": 10, "tripulante_id": 202, "funcao": "copiloto", "status": "calculado", "action": "updated"},
        ],
        "warnings": [],
        "errors": [],
        "current_result": {"total": "360.00", "calculations": []},
        "audit_event_id": None,
    }


def _cancel_result():
    return {
        "mission": {
            "id": 10,
            "org_id": "default_single_tenant",
            "competencia": "2026-04",
            "status": "cancelada",
        },
        "mission_id": 10,
        "competence": "2026-04",
        "calculation_status": "cancelada",
        "cancelled_at": "2026-05-04T15:00:00+00:00",
        "affected_calculations": [
            {"id": 900, "mission_id": 10, "tripulante_id": 101, "funcao": "comandante", "status": "obsoleto", "action": "invalidated"},
        ],
        "warnings": [
            {
                "code": "finance_calculation_invalidated_by_mission_cancel",
                "message": "1 calculo horario vigente foi marcado como obsoleto.",
            }
        ],
        "errors": [],
        "current_result": {"status": "cancelada", "calculations": []},
        "audit_event_id": None,
        "action": "cancelled",
    }


def test_cancel_endpoint_requires_authentication_and_permission(monkeypatch):
    app = create_app()
    anonymous = app.test_client()

    response = anonymous.post("/api/v1/financeiro/missoes/10/cancelar", headers=_headers(request_id="finance-cancel-auth"))
    payload = _assert_envelope(response, status=401, success=False)
    assert payload["code"] == "auth_required"

    no_scope_client = app.test_client()
    csrf_token = _authenticate_client(
        no_scope_client,
        monkeypatch,
        permissions={"finance:missions:read"},
        login="finance_cancel_no_scope",
    )
    response = no_scope_client.post(
        "/api/v1/financeiro/missoes/10/cancelar",
        json={"motivo": "sem permissao"},
        headers=_headers(csrf_token, request_id="finance-cancel-forbidden"),
    )
    payload = _assert_envelope(response, status=403, success=False)
    assert payload["code"] == "forbidden"


def test_cancel_endpoint_delegates_to_use_case_and_returns_typed_envelope(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_cancel_authorized",
    )
    calls = []

    def _cancel(mission_id, **kwargs):
        calls.append((mission_id, kwargs))
        return _cancel_result()

    monkeypatch.setattr(financeiro_routes, "cancelar_missao_operacional", _cancel)

    response = client.post(
        "/api/v1/financeiro/missoes/10/cancelar",
        json={"motivo": "cancelamento seguro"},
        headers=_headers(csrf_token, request_id="finance-cancel-ok"),
    )
    payload = _assert_envelope(response, status=200, success=True)

    assert payload["code"] == "finance_mission_cancelled"
    assert payload["mission"]["status"] == "cancelada"
    assert payload["mission_id"] == 10
    assert payload["competence"] == "2026-04"
    assert payload["calculation_status"] == "cancelada"
    assert payload["affected_calculations"][0]["action"] == "invalidated"
    assert payload["current_result"]["status"] == "cancelada"
    assert payload["warnings"][0]["code"] == "finance_calculation_invalidated_by_mission_cancel"
    assert payload["errors"] == []
    assert calls == [(10, {"actor_user_id": 901, "motivo": "cancelamento seguro"})]


def test_cancel_endpoint_translates_domain_errors(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_cancel_conflict",
    )

    def _cancel(_mission_id, **_kwargs):
        raise DomainConflictError("Competencia fechada.", code="competencia_financeira_fechada", status=409)

    monkeypatch.setattr(financeiro_routes, "cancelar_missao_operacional", _cancel)

    response = client.post(
        "/api/v1/financeiro/missoes/10/cancelar",
        json={"motivo": "competencia fechada"},
        headers=_headers(csrf_token, request_id="finance-cancel-conflict"),
    )
    payload = _assert_envelope(response, status=409, success=False)
    assert payload["code"] == "competencia_financeira_fechada"


def test_recalculate_endpoint_requires_authentication_and_permission(monkeypatch):
    app = create_app()
    anonymous = app.test_client()

    response = anonymous.post("/api/v1/financeiro/missoes/10/recalcular", headers=_headers())
    payload = _assert_envelope(response, status=401, success=False)
    assert payload["code"] == "auth_required"

    no_scope_client = app.test_client()
    csrf_token = _authenticate_client(
        no_scope_client,
        monkeypatch,
        permissions={"finance:missions:read"},
        login="finance_recalc_no_scope",
    )
    response = no_scope_client.post(
        "/api/v1/financeiro/missoes/10/recalcular",
        headers=_headers(csrf_token, request_id="finance-recalc-forbidden"),
    )
    payload = _assert_envelope(response, status=403, success=False)
    assert payload["code"] == "forbidden"


def test_recalculate_endpoint_delegates_to_use_case_and_returns_calculation_memory(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_recalc_authorized",
    )
    calls = []

    def _recalculate(mission_id, **kwargs):
        calls.append((mission_id, kwargs))
        return _recalc_result()

    monkeypatch.setattr(financeiro_routes, "recalcular_missao_operacional", _recalculate)

    response = client.post(
        "/api/v1/financeiro/missoes/10/recalcular",
        headers=_headers(csrf_token, request_id="finance-recalc-ok"),
    )
    payload = _assert_envelope(response, status=200, success=True)

    assert payload["code"] == "finance_mission_recalculated"
    assert payload["mission"]["id"] == 10
    assert {item["funcao"] for item in payload["calculations"]} == {"comandante", "copiloto"}
    assert payload["calculations"][0]["memoria_calculo"]["steps"][0]["rule_key"] == "conversao_hora_noturna"
    assert payload["calculations"][0]["parametros_usados"][0]["valor"] == "52.5"
    assert payload["mission_id"] == 10
    assert payload["competence"] == "2026-04"
    assert payload["calculation_status"] == "calculado"
    assert payload["affected_calculations"][0]["action"] == "updated"
    assert payload["current_result"]["total"] == "360.00"
    assert payload["warnings"] == []
    assert payload["errors"] == []
    assert calls == [(10, {"actor_user_id": 901})]


def test_recalculate_endpoint_translates_domain_errors(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_recalc_conflict",
    )

    def _recalculate(_mission_id, **_kwargs):
        raise DomainConflictError("Competencia fechada.", code="competencia_financeira_fechada", status=409)

    monkeypatch.setattr(financeiro_routes, "recalcular_missao_operacional", _recalculate)

    response = client.post(
        "/api/v1/financeiro/missoes/10/recalcular",
        headers=_headers(csrf_token, request_id="finance-recalc-conflict"),
    )
    payload = _assert_envelope(response, status=409, success=False)
    assert payload["code"] == "competencia_financeira_fechada"
