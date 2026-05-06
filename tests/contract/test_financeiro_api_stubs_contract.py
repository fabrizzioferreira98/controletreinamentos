from __future__ import annotations

import json

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import audit as audit_module
from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.auth import ENDPOINT_PERMISSION_MAP, FINANCE_PERMISSION_KEYS
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_API_ROUTE_PREFIX
from backend.src.controle_treinamentos.contracts.financeiro_http import (
    FINANCE_HTTP_CONTRACTS,
    FINANCE_STUB_HTTP_CONTRACTS,
)
from backend.src.controle_treinamentos.core import audit_utils as audit_utils_module

API_METHODS = {"GET", "POST", "PATCH"}
MUTATION_METHODS = {"POST", "PATCH"}


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


def _auth_user_row(*, permissions, login: str = "finance_stub_user"):
    return {
        "id": 501,
        "nome": "Finance Stub User",
        "login": login,
        "email": f"{login}@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": json.dumps(sorted(permissions)),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch, *, permissions, login: str = "finance_stub_user") -> str:
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


def _csrf_token(client) -> str:
    response = client.get("/api/v1/session")
    assert response.status_code == 200
    return response.get_json()["csrf_token"]


def _materialize_path(path: str) -> str:
    return (
        path.replace("{tripulante_id}", "77")
        .replace("{competencia}", "2026-04")
        .replace("{id}", "101")
    )


def _normalize_registered_finance_path(path: str) -> str:
    normalized = path.replace("<string:competencia>", "{competencia}")
    normalized = normalized.replace("<int:tripulante_id>", "{tripulante_id}")
    normalized = normalized.replace("<int:mission_id>", "{id}")
    normalized = normalized.replace("<int:linha_id>", "{id}")
    normalized = normalized.replace("<int:calculation_id>", "{id}")
    normalized = normalized.replace("<int:parameter_id>", "{id}")
    return normalized.replace("<int:holiday_id>", "{id}")


def _request_payload_for(contract: dict) -> dict | None:
    if contract["method"] not in MUTATION_METHODS:
        return None
    payload = {"motivo": "stub contract"}
    if "confirm" in contract["request_payload_minimal"]:
        payload["confirm"] = True
    if "changed_fields" in contract["request_payload_minimal"]:
        payload["changed_fields"] = {}
    return payload


def _call_contract(client, contract: dict, *, csrf_token: str | None = None):
    headers = {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-Request-ID": f"finance-request-{contract['name']}",
        "X-Correlation-ID": f"finance-correlation-{contract['name']}",
    }
    if csrf_token and contract["method"] in MUTATION_METHODS:
        headers["X-CSRFToken"] = csrf_token
    kwargs = {
        "method": contract["method"],
        "headers": headers,
        "follow_redirects": False,
    }
    payload = _request_payload_for(contract)
    if payload is not None:
        kwargs["json"] = payload
    return client.open(_materialize_path(contract["path"]), **kwargs)


def _assert_error_envelope(response, *, status: int):
    assert response.status_code == status
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == status
    assert payload["message"]
    assert payload["code"]
    assert payload["request_id"]
    assert payload["correlation_id"]
    return payload


def _registered_finance_routes_by_key(app) -> dict[tuple[str, str], str]:
    registered = {}
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith(FINANCE_API_ROUTE_PREFIX):
            continue
        normalized_path = _normalize_registered_finance_path(rule.rule)
        for method in set(rule.methods) & API_METHODS:
            registered[(method, normalized_path)] = rule.endpoint
    return registered


def test_finance_runtime_routes_are_registered_from_contract_matrix():
    app = create_app()
    expected = {
        (contract["method"], contract["path"]): contract["permission"]
        for contract in FINANCE_HTTP_CONTRACTS
    }
    registered = _registered_finance_routes_by_key(app)

    assert set(registered) == set(expected)
    for key, endpoint in registered.items():
        assert ENDPOINT_PERMISSION_MAP.get(endpoint) == expected[key]


def test_finance_runtime_routes_require_authentication():
    app = create_app()
    client = app.test_client()
    csrf_token = _csrf_token(client)

    for contract in FINANCE_HTTP_CONTRACTS:
        response = _call_contract(client, contract, csrf_token=csrf_token)
        payload = _assert_error_envelope(response, status=401)
        assert payload["code"] == "auth_required"


def test_finance_runtime_routes_deny_authenticated_user_without_finance_permission(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions={"dashboard:view"},
        login="finance_stub_no_scope",
    )

    for contract in FINANCE_HTTP_CONTRACTS:
        response = _call_contract(client, contract, csrf_token=csrf_token)
        payload = _assert_error_envelope(response, status=403)
        assert payload["code"] == "forbidden"


def test_finance_runtime_contract_matrix_has_no_pending_501_stub_for_authorized_user(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_stub_authorized",
    )
    registered = _registered_finance_routes_by_key(app)
    runtime_keys = {(contract["method"], contract["path"]) for contract in FINANCE_HTTP_CONTRACTS}
    stub_keys = {(contract["method"], contract["path"]) for contract in FINANCE_STUB_HTTP_CONTRACTS}

    assert runtime_keys == set(registered)
    assert stub_keys == set()


def test_finance_stub_mutations_if_any_do_not_dispatch_audit_events(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_stub_no_audit",
    )
    audit_calls = []

    def _capture_audit_call(*args, **kwargs):
        audit_calls.append((args, kwargs))

    monkeypatch.setattr(audit_module, "record_audit_event", _capture_audit_call)
    monkeypatch.setattr(audit_utils_module, "audit_event", _capture_audit_call)

    for contract in FINANCE_STUB_HTTP_CONTRACTS:
        if contract["method"] not in MUTATION_METHODS:
            continue
        response = _call_contract(client, contract, csrf_token=csrf_token)
        _assert_error_envelope(response, status=501)

    assert audit_calls == []
