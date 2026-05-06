from __future__ import annotations

import json

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.api.http.financeiro import routes as financeiro_routes
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


def _auth_user_row(*, permissions, login: str = "finance_holiday_http_user"):
    return {
        "id": 801,
        "nome": "Finance Holiday HTTP User",
        "login": login,
        "email": f"{login}@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": json.dumps(sorted(permissions)),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch, *, permissions, login: str = "finance_holiday_http_user") -> str:
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


def _headers(csrf_token: str | None = None, *, request_id: str = "finance-holiday-http") -> dict:
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


def _holiday_payload(**overrides):
    payload = {
        "data": "2026-04-21",
        "nome": "Tiradentes",
        "tipo": "nacional",
        "status": "ativo",
    }
    payload.update(overrides)
    return payload


def _holiday_response(**overrides):
    payload = {
        "id": 1,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "data": "2026-04-21",
        "nome": "Tiradentes",
        "tipo": "nacional",
        "localidade": None,
        "status": "ativo",
        "created_by": 801,
        "updated_by": 801,
        "links": {"self": "/api/v1/financeiro/feriados/1"},
    }
    payload.update(overrides)
    return payload


def test_holiday_endpoints_require_authentication_and_permission(monkeypatch):
    app = create_app()
    anonymous = app.test_client()

    response = anonymous.get("/api/v1/financeiro/feriados", headers=_headers())
    payload = _assert_envelope(response, status=401, success=False)
    assert payload["code"] == "auth_required"

    no_scope_client = app.test_client()
    csrf_token = _authenticate_client(
        no_scope_client,
        monkeypatch,
        permissions={"dashboard:view"},
        login="finance_holiday_no_scope",
    )
    response = no_scope_client.post(
        "/api/v1/financeiro/feriados",
        json=_holiday_payload(),
        headers=_headers(csrf_token, request_id="finance-holiday-forbidden"),
    )
    payload = _assert_envelope(response, status=403, success=False)
    assert payload["code"] == "forbidden"


def test_holiday_http_endpoints_delegate_to_use_cases_and_return_envelope(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_holiday_authorized",
    )
    calls = []

    def _list_holidays(**kwargs):
        calls.append(("list", kwargs))
        return {
            "items": [_holiday_response()],
            "pagination": {"page": kwargs["page"], "offset": kwargs["offset"], "total": 1},
        }

    def _create_holiday(payload, **kwargs):
        calls.append(("create", payload, kwargs))
        assert payload["tipo"] == "nacional"
        return _holiday_response(localidade=None)

    def _update_holiday(holiday_id, payload, **kwargs):
        calls.append(("update", holiday_id, payload, kwargs))
        assert holiday_id == 1
        return _holiday_response(nome=payload.get("nome"), localidade=None)

    monkeypatch.setattr(financeiro_routes, "listar_feriados_nacionais", _list_holidays)
    monkeypatch.setattr(financeiro_routes, "criar_feriado_nacional", _create_holiday)
    monkeypatch.setattr(financeiro_routes, "atualizar_feriado_nacional", _update_holiday)

    list_response = client.get(
        "/api/v1/financeiro/feriados?ano=2026",
        headers=_headers(request_id="finance-holiday-list"),
    )
    list_payload = _assert_envelope(list_response, status=200, success=True)
    assert list_payload["items"][0]["tipo"] == "nacional"

    create_response = client.post(
        "/api/v1/financeiro/feriados",
        json=_holiday_payload(localidade="SP"),
        headers=_headers(csrf_token, request_id="finance-holiday-create"),
    )
    create_payload = _assert_envelope(create_response, status=201, success=True)
    assert create_payload["holiday"]["localidade"] is None

    patch_response = client.patch(
        "/api/v1/financeiro/feriados/1",
        json={"nome": "Tiradentes Nacional", "localidade": "RJ"},
        headers=_headers(csrf_token, request_id="finance-holiday-patch"),
    )
    patch_payload = _assert_envelope(patch_response, status=200, success=True)
    assert patch_payload["holiday"]["nome"] == "Tiradentes Nacional"
    assert patch_payload["holiday"]["localidade"] is None

    assert [call[0] for call in calls] == ["list", "create", "update"]


def test_observability_finance_endpoints_are_available(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_holiday_stubs",
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

    endpoints = (
        ("GET", "/api/v1/financeiro/auditoria"),
        ("GET", "/api/v1/financeiro/divergencias"),
    )
    for method, path in endpoints:
        response = client.open(
            path,
            method=method,
            headers=_headers(csrf_token if method == "POST" else None, request_id=f"finance-holiday-stub-{method}"),
        )
        payload = _assert_envelope(response, status=200, success=True)
        assert payload["items"] == []
        assert payload["status"] != 501


def test_holiday_patch_rejects_empty_or_irrelevant_payload(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_holiday_patch_validation",
    )

    monkeypatch.setattr(
        financeiro_routes,
        "atualizar_feriado_nacional",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Route should block invalid PATCH payload before use case")),
    )

    empty_response = client.patch(
        "/api/v1/financeiro/feriados/1",
        json={},
        headers=_headers(csrf_token, request_id="finance-holiday-patch-empty"),
    )
    empty_payload = _assert_envelope(empty_response, status=400, success=False)
    assert empty_payload["code"] == "finance_holiday_patch_empty_or_invalid"

    irrelevant_response = client.patch(
        "/api/v1/financeiro/feriados/1",
        json={"foo": "bar"},
        headers=_headers(csrf_token, request_id="finance-holiday-patch-irrelevant"),
    )
    irrelevant_payload = _assert_envelope(irrelevant_response, status=400, success=False)
    assert irrelevant_payload["code"] == "finance_holiday_patch_empty_or_invalid"


def test_holiday_patch_keeps_rbac_forbidden_for_authenticated_user_without_permission(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions={"finance:parameters:read"},
        login="finance_holiday_patch_forbidden",
    )

    response = client.patch(
        "/api/v1/financeiro/feriados/1",
        json={"nome": "Teste"},
        headers=_headers(csrf_token, request_id="finance-holiday-patch-forbidden"),
    )
    payload = _assert_envelope(response, status=403, success=False)
    assert payload["code"] == "forbidden"
