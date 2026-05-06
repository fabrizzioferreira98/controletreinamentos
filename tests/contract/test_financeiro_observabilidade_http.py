from __future__ import annotations

import json

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.api.http.financeiro import routes as financeiro_routes
from backend.src.controle_treinamentos.auth import FINANCE_PERMISSION_KEYS
from backend.src.controle_treinamentos.core.domain_errors import DomainValidationError


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


def _auth_user_row(*, permissions, login: str = "finance_observability_http_user"):
    return {
        "id": 871,
        "nome": "Finance Observability HTTP User",
        "login": login,
        "email": f"{login}@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": json.dumps(sorted(permissions)),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch, *, permissions, login: str = "finance_observability_http_user") -> str:
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


def _headers(*, request_id: str, csrf_token: str | None = None) -> dict:
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
    assert payload["request_id"]
    assert payload["correlation_id"]
    return payload


def test_observability_endpoints_require_authentication_and_permission(monkeypatch):
    app = create_app()
    anonymous = app.test_client()

    anonymous_audit = anonymous.get(
        "/api/v1/financeiro/auditoria",
        headers=_headers(request_id="finance-observability-anonymous-audit"),
    )
    anonymous_audit_payload = _assert_envelope(anonymous_audit, status=401, success=False)
    assert anonymous_audit_payload["code"] == "auth_required"

    anonymous_divergences = anonymous.get(
        "/api/v1/financeiro/divergencias",
        headers=_headers(request_id="finance-observability-anonymous-divergences"),
    )
    anonymous_divergences_payload = _assert_envelope(anonymous_divergences, status=401, success=False)
    assert anonymous_divergences_payload["code"] == "auth_required"

    no_scope_client = app.test_client()
    csrf_token = _authenticate_client(
        no_scope_client,
        monkeypatch,
        permissions={"dashboard:view"},
        login="finance_observability_no_scope",
    )
    forbidden_audit = no_scope_client.get(
        "/api/v1/financeiro/auditoria",
        headers=_headers(request_id="finance-observability-forbidden-audit", csrf_token=csrf_token),
    )
    forbidden_audit_payload = _assert_envelope(forbidden_audit, status=403, success=False)
    assert forbidden_audit_payload["code"] == "forbidden"

    forbidden_divergences = no_scope_client.get(
        "/api/v1/financeiro/divergencias",
        headers=_headers(request_id="finance-observability-forbidden-divergences", csrf_token=csrf_token),
    )
    forbidden_divergences_payload = _assert_envelope(forbidden_divergences, status=403, success=False)
    assert forbidden_divergences_payload["code"] == "forbidden"


def test_observability_endpoints_delegate_filters_and_return_envelope(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_observability_authorized",
    )
    calls = []

    def _audit_list(**kwargs):
        calls.append(("audit", kwargs))
        return {
            "items": [{"id": 10, "event_name": "finance.mission.created"}],
            "pagination": {"page": 1, "offset": 0, "limit": 10, "total": 1},
        }

    def _divergences_list(**kwargs):
        calls.append(("divergences", kwargs))
        return {
            "items": [{"id": 20, "severity": "alta", "code": "parametro_ausente"}],
            "pagination": {"page": 1, "offset": 0, "limit": 10, "total": 1},
        }

    monkeypatch.setattr(financeiro_routes, "listar_eventos_auditoria_financeira", _audit_list)
    monkeypatch.setattr(financeiro_routes, "listar_divergencias_financeiras", _divergences_list)

    audit_response = client.get(
        "/api/v1/financeiro/auditoria?competencia=2026-04&entity_type=finance_mission&entity_id=101&event_name=finance.mission.created&limit=10&offset=0",
        headers=_headers(request_id="finance-observability-audit-ok", csrf_token=csrf_token),
    )
    audit_payload = _assert_envelope(audit_response, status=200, success=True)
    assert audit_payload["code"] == "finance_audit_list_ok"
    assert audit_payload["items"][0]["event_name"] == "finance.mission.created"
    assert audit_payload["filters"]["entity_id"] == 101
    assert audit_response.status_code != 501

    divergences_response = client.get(
        "/api/v1/financeiro/divergencias?competencia=2026-04&status=aberta&severidade=alta&codigo=parametro_ausente&limit=10&offset=0",
        headers=_headers(request_id="finance-observability-divergences-ok", csrf_token=csrf_token),
    )
    divergences_payload = _assert_envelope(divergences_response, status=200, success=True)
    assert divergences_payload["code"] == "finance_divergences_list_ok"
    assert divergences_payload["items"][0]["severity"] == "alta"
    assert divergences_response.status_code != 501

    assert calls[0][0] == "audit"
    assert calls[0][1]["competencia"] == "2026-04"
    assert calls[0][1]["entity_type"] == "finance_mission"
    assert calls[0][1]["entity_id"] == "101"
    assert calls[0][1]["event_name"] == "finance.mission.created"
    assert calls[0][1]["limit"] == "10"
    assert calls[0][1]["offset"] == "0"
    assert calls[1][0] == "divergences"
    assert calls[1][1]["status"] == "aberta"
    assert calls[1][1]["severidade"] == "alta"
    assert calls[1][1]["codigo"] == "parametro_ausente"


def test_observability_endpoints_return_empty_list_without_error(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_observability_empty",
    )

    monkeypatch.setattr(
        financeiro_routes,
        "listar_eventos_auditoria_financeira",
        lambda **_kwargs: {"items": [], "pagination": {"page": 1, "offset": 0, "limit": 50, "total": 0}},
    )
    monkeypatch.setattr(
        financeiro_routes,
        "listar_divergencias_financeiras",
        lambda **_kwargs: {"items": [], "pagination": {"page": 1, "offset": 0, "limit": 50, "total": 0}},
    )

    audit_response = client.get(
        "/api/v1/financeiro/auditoria",
        headers=_headers(request_id="finance-observability-empty-audit", csrf_token=csrf_token),
    )
    audit_payload = _assert_envelope(audit_response, status=200, success=True)
    assert audit_payload["items"] == []
    assert audit_payload["pagination"]["total"] == 0

    divergences_response = client.get(
        "/api/v1/financeiro/divergencias",
        headers=_headers(request_id="finance-observability-empty-divergences", csrf_token=csrf_token),
    )
    divergences_payload = _assert_envelope(divergences_response, status=200, success=True)
    assert divergences_payload["items"] == []
    assert divergences_payload["pagination"]["total"] == 0


def test_observability_endpoints_translate_validation_errors(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_observability_invalid",
    )

    monkeypatch.setattr(
        financeiro_routes,
        "listar_eventos_auditoria_financeira",
        lambda **_kwargs: (_ for _ in ()).throw(
            DomainValidationError(
                "Filtro limit invalido.",
                code="finance_observability_limit_invalid",
                status=400,
            )
        ),
    )
    invalid_audit = client.get(
        "/api/v1/financeiro/auditoria?limit=abc",
        headers=_headers(request_id="finance-observability-invalid-audit", csrf_token=csrf_token),
    )
    invalid_audit_payload = _assert_envelope(invalid_audit, status=400, success=False)
    assert invalid_audit_payload["code"] == "finance_observability_limit_invalid"

    monkeypatch.setattr(
        financeiro_routes,
        "listar_divergencias_financeiras",
        lambda **_kwargs: (_ for _ in ()).throw(
            DomainValidationError(
                "Filtro severidade invalido.",
                code="finance_divergence_severity_invalid",
                status=400,
            )
        ),
    )
    invalid_divergences = client.get(
        "/api/v1/financeiro/divergencias?severidade=critica",
        headers=_headers(request_id="finance-observability-invalid-divergences", csrf_token=csrf_token),
    )
    invalid_divergences_payload = _assert_envelope(invalid_divergences, status=400, success=False)
    assert invalid_divergences_payload["code"] == "finance_divergence_severity_invalid"
