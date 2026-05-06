from __future__ import annotations

import json

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.api.http.financeiro import routes as financeiro_routes
from backend.src.controle_treinamentos.auth import FINANCE_PERMISSION_KEYS
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT
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


def _auth_user_row(*, permissions, login: str = "finance_param_http_user"):
    return {
        "id": 701,
        "nome": "Finance Param HTTP User",
        "login": login,
        "email": f"{login}@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": json.dumps(sorted(permissions)),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch, *, permissions, login: str = "finance_param_http_user") -> str:
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


def _headers(csrf_token: str | None = None, *, request_id: str = "finance-param-http") -> dict:
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


def _parameter_payload(**overrides):
    payload = {
        "tipo": "duracao_hora_noturna_minutos",
        "valor": "52.5",
        "unidade": "minutos",
        "vigencia_inicio": "2026-04-01",
        "motivo": "contrato http",
    }
    payload.update(overrides)
    return payload


def _parameter_response(**overrides):
    payload = {
        "id": 1,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "tipo": "duracao_hora_noturna_minutos",
        "funcao": None,
        "categoria": None,
        "valor": "52.5",
        "unidade": "minutos",
        "vigencia_inicio": "2026-04-01",
        "vigencia_fim": None,
        "status": "ativo",
        "motivo": "contrato http",
        "created_by": 701,
        "updated_by": 701,
        "links": {"self": "/api/v1/financeiro/parametros/1"},
    }
    payload.update(overrides)
    return payload


def test_parameter_endpoints_require_authentication_and_permission(monkeypatch):
    app = create_app()
    anonymous = app.test_client()

    response = anonymous.get("/api/v1/financeiro/parametros", headers=_headers())
    payload = _assert_envelope(response, status=401, success=False)
    assert payload["code"] == "auth_required"

    no_scope_client = app.test_client()
    csrf_token = _authenticate_client(
        no_scope_client,
        monkeypatch,
        permissions={"dashboard:view"},
        login="finance_param_no_scope",
    )
    response = no_scope_client.post(
        "/api/v1/financeiro/parametros",
        json=_parameter_payload(),
        headers=_headers(csrf_token, request_id="finance-param-forbidden"),
    )
    payload = _assert_envelope(response, status=403, success=False)
    assert payload["code"] == "forbidden"


def test_parameter_http_endpoints_delegate_to_use_cases_and_return_envelope(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_param_authorized",
    )
    calls = []

    def _list_parameters(**kwargs):
        calls.append(("list", kwargs))
        return {
            "items": [_parameter_response()],
            "pagination": {"page": kwargs["page"], "offset": kwargs["offset"], "total": 1},
        }

    def _create_parameter(payload, **kwargs):
        calls.append(("create", payload, kwargs))
        assert payload["valor"] == "52.5"
        assert payload["unidade"] == "minutos"
        return _parameter_response()

    def _update_parameter(parameter_id, payload, **kwargs):
        calls.append(("update", parameter_id, payload, kwargs))
        assert parameter_id == 1
        return _parameter_response(valor="60", motivo=payload.get("motivo"))

    monkeypatch.setattr(financeiro_routes, "listar_parametros_financeiros", _list_parameters)
    monkeypatch.setattr(financeiro_routes, "criar_parametro_financeiro", _create_parameter)
    monkeypatch.setattr(financeiro_routes, "atualizar_parametro_financeiro", _update_parameter)

    list_response = client.get(
        "/api/v1/financeiro/parametros?tipo=duracao_hora_noturna_minutos",
        headers=_headers(request_id="finance-param-list"),
    )
    list_payload = _assert_envelope(list_response, status=200, success=True)
    assert list_payload["items"][0]["tipo"] == "duracao_hora_noturna_minutos"

    create_response = client.post(
        "/api/v1/financeiro/parametros",
        json=_parameter_payload(),
        headers=_headers(csrf_token, request_id="finance-param-create"),
    )
    create_payload = _assert_envelope(create_response, status=201, success=True)
    assert create_payload["parameter"]["valor"] == "52.5"
    assert create_payload["parameter"]["unidade"] == "minutos"

    patch_response = client.patch(
        "/api/v1/financeiro/parametros/1",
        json={"valor": "60", "motivo": "ajuste"},
        headers=_headers(csrf_token, request_id="finance-param-patch"),
    )
    patch_payload = _assert_envelope(patch_response, status=200, success=True)
    assert patch_payload["parameter"]["valor"] == "60"

    assert [call[0] for call in calls] == ["list", "create", "update"]


def test_parameter_http_accepts_day_period_minutes_of_day(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_param_period_authorized",
    )
    calls = []

    def _create_parameter(payload, **_kwargs):
        calls.append(payload)
        return _parameter_response(
            tipo=payload["tipo"],
            valor=str(payload["valor"]),
            unidade=payload["unidade"],
            motivo=payload.get("motivo"),
        )

    monkeypatch.setattr(financeiro_routes, "criar_parametro_financeiro", _create_parameter)

    inicio_response = client.post(
        "/api/v1/financeiro/parametros",
        json=_parameter_payload(
            tipo="periodo_diurno_inicio",
            valor="360",
            unidade="minutos_do_dia",
            motivo="periodo inicio",
        ),
        headers=_headers(csrf_token, request_id="finance-param-period-start"),
    )
    fim_response = client.post(
        "/api/v1/financeiro/parametros",
        json=_parameter_payload(
            tipo="periodo_diurno_fim",
            valor="1080",
            unidade="minutos_do_dia",
            motivo="periodo fim",
        ),
        headers=_headers(csrf_token, request_id="finance-param-period-end"),
    )

    inicio_payload = _assert_envelope(inicio_response, status=201, success=True)
    fim_payload = _assert_envelope(fim_response, status=201, success=True)
    assert inicio_payload["parameter"]["tipo"] == "periodo_diurno_inicio"
    assert inicio_payload["parameter"]["valor"] == "360"
    assert inicio_payload["parameter"]["unidade"] == "minutos_do_dia"
    assert fim_payload["parameter"]["tipo"] == "periodo_diurno_fim"
    assert fim_payload["parameter"]["valor"] == "1080"
    assert fim_payload["parameter"]["unidade"] == "minutos_do_dia"
    assert [call["valor"] for call in calls] == ["360", "1080"]


def test_parameter_http_translates_day_period_validation_error(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_param_period_invalid",
    )

    def _create_parameter(_payload, **_kwargs):
        raise DomainValidationError("Valor invalido.", code="parametro_financeiro_campo_invalido", status=400)

    monkeypatch.setattr(financeiro_routes, "criar_parametro_financeiro", _create_parameter)

    response = client.post(
        "/api/v1/financeiro/parametros",
        json=_parameter_payload(
            tipo="periodo_diurno_inicio",
            valor="06:00",
            unidade="minutos_do_dia",
        ),
        headers=_headers(csrf_token, request_id="finance-param-period-invalid"),
    )
    payload = _assert_envelope(response, status=400, success=False)
    assert payload["code"] == "parametro_financeiro_campo_invalido"


def test_observability_finance_endpoints_are_available(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_param_stubs",
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
            json={"motivo": "still stub"} if method == "POST" else None,
            headers=_headers(csrf_token if method == "POST" else None, request_id=f"finance-param-stub-{method}"),
        )
        payload = _assert_envelope(response, status=200, success=True)
        assert payload["items"] == []
        assert payload["status"] != 501


def test_parameter_patch_rejects_empty_or_irrelevant_payload(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_param_patch_validation",
    )

    monkeypatch.setattr(
        financeiro_routes,
        "atualizar_parametro_financeiro",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("Route should block invalid PATCH payload before use case")),
    )

    empty_response = client.patch(
        "/api/v1/financeiro/parametros/1",
        json={},
        headers=_headers(csrf_token, request_id="finance-param-patch-empty"),
    )
    empty_payload = _assert_envelope(empty_response, status=400, success=False)
    assert empty_payload["code"] == "finance_parameter_patch_empty_or_invalid"

    irrelevant_response = client.patch(
        "/api/v1/financeiro/parametros/1",
        json={"foo": "bar"},
        headers=_headers(csrf_token, request_id="finance-param-patch-irrelevant"),
    )
    irrelevant_payload = _assert_envelope(irrelevant_response, status=400, success=False)
    assert irrelevant_payload["code"] == "finance_parameter_patch_empty_or_invalid"


def test_parameter_patch_keeps_rbac_forbidden_for_authenticated_user_without_permission(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions={"finance:parameters:read"},
        login="finance_param_patch_forbidden",
    )

    response = client.patch(
        "/api/v1/financeiro/parametros/1",
        json={"motivo": "teste"},
        headers=_headers(csrf_token, request_id="finance-param-patch-forbidden"),
    )
    payload = _assert_envelope(response, status=403, success=False)
    assert payload["code"] == "forbidden"

