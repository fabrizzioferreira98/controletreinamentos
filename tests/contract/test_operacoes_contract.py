from __future__ import annotations

import json

import pytest
from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.api.http.operacoes import routes as operacoes_api
from backend.src.controle_treinamentos.contracts.operacoes import (
    OPERACOES_API_ROUTE_PREFIX,
    OPERACOES_FUTURE_API_CONTRACT,
    OPERACOES_READ_API_ENDPOINTS,
    OPERACOES_SSR_CURRENT_ENDPOINTS,
    current_read_api_endpoints,
    future_api_paths,
)


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


def _auth_user_row(*, permissions=None):
    permission_keys = ["pernoites:view"] if permissions is None else permissions
    return {
        "id": 77,
        "nome": "Operador Pernoites",
        "login": "pernoites_api",
        "email": "pernoites.api@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": json.dumps(permission_keys),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch, *, permissions=None):
    fake_db = _SingleUserDB(_auth_user_row(permissions=permissions))
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)
    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "pernoites_api", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/pernoites?tipo=cobertura_base"])
def test_operacoes_ssr_html_route_without_session_redirects_to_login(path):
    app = create_app()
    client = app.test_client()

    response = client.get(
        path,
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )

    assert response.status_code in {302, 303}
    assert "/login" in response.headers["Location"]


@pytest.mark.parametrize("path", ["/pernoites?tipo=cobertura_base"])
def test_operacoes_ssr_programmatic_access_without_session_returns_json_auth_required(path):
    app = create_app()
    client = app.test_client()

    response = client.get(
        path,
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )

    assert response.status_code == 401
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == 401
    assert payload["code"] == "auth_required"


@pytest.mark.parametrize(
    "path",
    [
        "/pernoites/novo",
        "/pernoites/1/editar",
        "/pernoites/1/excluir",
    ],
)
def test_operacoes_ssr_mutation_without_session_prefers_auth_required_over_csrf(path):
    app = create_app()
    client = app.test_client()

    response = client.post(
        path,
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )

    assert response.status_code == 401
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == 401
    assert payload["code"] == "auth_required"


def test_operacoes_current_boundary_is_formally_current_ssr_canonical_against_registered_routes():
    app = create_app()
    rules_by_endpoint = {rule.endpoint: rule for rule in app.url_map.iter_rules()}

    assert {item["classification"] for item in OPERACOES_SSR_CURRENT_ENDPOINTS} == {"ssr_canonical_current_direct"}
    for contract in OPERACOES_SSR_CURRENT_ENDPOINTS:
        rule = rules_by_endpoint[contract["endpoint"]]
        assert rule.rule == contract["route"]
        assert set(contract["methods"]).issubset(rule.methods)


def test_operacoes_read_api_contract_is_registered_without_write_api_cutover():
    app = create_app()
    registered_operacoes_api_rules = {
        rule.endpoint: rule
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith(OPERACOES_API_ROUTE_PREFIX)
    }

    assert current_read_api_endpoints() == OPERACOES_READ_API_ENDPOINTS
    assert {item["classification"] for item in OPERACOES_READ_API_ENDPOINTS} == {"api_read_canonical_registered"}
    for contract in OPERACOES_READ_API_ENDPOINTS:
        rule = registered_operacoes_api_rules[contract["endpoint"]]
        assert rule.rule == contract["route"]
        assert set(contract["methods"]).issubset(rule.methods)

    write_methods = {"POST", "PUT", "PATCH", "DELETE"}
    write_api_routes = [
        rule.rule
        for rule in registered_operacoes_api_rules.values()
        if write_methods.intersection(rule.methods)
    ]
    assert write_api_routes == []
    assert OPERACOES_FUTURE_API_CONTRACT["status"] == "read_api_registered_write_ssr_canonical_current"
    assert OPERACOES_FUTURE_API_CONTRACT["canonical_current"] == "ssr_ui_and_write_current_with_api_read_model"
    assert "write API" in OPERACOES_FUTURE_API_CONTRACT["registration_policy"]
    assert set(future_api_paths()) == {
        "/api/v1/operacoes/pernoites",
        "/api/v1/operacoes/pernoites/<id>",
    }
    assert OPERACOES_FUTURE_API_CONTRACT["error"]["source"] == "DomainError"
    assert "missoes" not in OPERACOES_FUTURE_API_CONTRACT["resources"]
    assert "missao_id" not in OPERACOES_FUTURE_API_CONTRACT["resources"]["pernoites"]["request"]


def test_operacoes_read_api_list_returns_real_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    captured = {}

    def _list_read_model(**kwargs):
        captured.update(kwargs)
        return {
            "items": [
                {
                    "id": 8,
                    "tripulante_id": 3,
                    "tripulante_nome": "Ana Piloto",
                    "data_pernoite": "2026-05-02",
                    "tipo_pernoite": "cobertura_base",
                    "tipo_label": "Cobertura de base",
                    "quantidade": 1,
                    "observacoes": None,
                }
            ],
            "filters": {"tipo": "cobertura_base", "tripulante": "3"},
            "options": {"tipo_pernoite": [{"value": "cobertura_base", "label": "Cobertura de base"}]},
            "pagination": {"page": 2, "per_page": 10, "total": 11, "total_pages": 2, "has_next": False, "has_prev": True},
        }

    monkeypatch.setattr(operacoes_api, "list_pernoites_read_model", _list_read_model)

    response = client.get("/api/v1/operacoes/pernoites?tipo=cobertura_base&tripulante=3&page=2&per_page=10")

    assert response.status_code == 200
    payload = response.get_json()
    assert captured == {"tipo": "cobertura_base", "tripulante": "3", "page": "2", "per_page": "10"}
    assert payload["code"] == "operacoes_pernoites_list_ok"
    assert payload["pernoites"]["items"][0]["tripulante_nome"] == "Ana Piloto"
    assert "template" not in payload["pernoites"]["items"][0]


def test_operacoes_read_api_detail_returns_real_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        operacoes_api,
        "get_pernoite_read_model",
        lambda *, pernoite_id: {
            "item": {
                "id": pernoite_id,
                "tripulante_id": 3,
                "tripulante_nome": "Ana Piloto",
                "data_pernoite": "2026-05-02",
                "tipo_pernoite": "operacional_comum",
                "tipo_label": "Operacional comum",
                "quantidade": 2,
                "observacoes": "Jornada operacional",
            }
        },
    )

    response = client.get("/api/v1/operacoes/pernoites/8")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == "operacoes_pernoite_ok"
    assert payload["pernoite"]["id"] == 8
    assert payload["pernoite"]["tipo_pernoite"] == "operacional_comum"


def test_operacoes_read_api_detail_returns_domain_not_found(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    from backend.src.controle_treinamentos.core.domain_errors import DomainNotFoundError

    def _missing(*, pernoite_id):
        raise DomainNotFoundError("Pernoite nao encontrado.", code="operacoes_pernoite_not_found")

    monkeypatch.setattr(operacoes_api, "get_pernoite_read_model", _missing)

    response = client.get("/api/v1/operacoes/pernoites/404")

    assert response.status_code == 404
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["code"] == "operacoes_pernoite_not_found"
