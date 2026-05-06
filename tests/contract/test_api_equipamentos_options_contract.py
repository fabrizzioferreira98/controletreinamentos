from __future__ import annotations

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.api.http.cadastros import routes as cadastros_api
from backend.src.controle_treinamentos.contracts.equipamentos import (
    FINANCE_CATEGORIA_OPTIONS,
    validate_finance_categoria,
)


class _SingleCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _SingleUserDB:
    def __init__(self, row):
        self._row = row

    def execute(self, _query, _params):
        return _SingleCursor(self._row)


def _auth_user_row(*, permissions: list[str]):
    return {
        "id": 42,
        "nome": "Operador Cadastros",
        "login": "equip_api",
        "email": "equip.api@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": str(permissions).replace("'", '"'),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch, *, permissions: list[str]):
    row = _auth_user_row(permissions=permissions)
    fake_db = _SingleUserDB(row)
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)
    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "equip_api", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 200


def test_equipamentos_finance_category_contract_uses_lowercase_slugs():
    assert FINANCE_CATEGORIA_OPTIONS == ("a", "b", "turbohelice_palmas", "nao_aplicavel")
    assert validate_finance_categoria("A") == "a"
    assert validate_finance_categoria("") is None


def test_api_equipamentos_options_requires_authentication():
    app = create_app()
    client = app.test_client()

    response = client.get("/api/v1/equipamentos/options")

    assert response.status_code == 401
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["request_id"]
    assert payload["correlation_id"]


def test_api_equipamentos_options_requires_equipamentos_permission(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch, permissions=["treinamentos:view"])

    response = client.get("/api/v1/equipamentos/options")

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["code"] == "forbidden"


def test_api_equipamentos_options_returns_transversal_options_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch, permissions=["equipamentos:view"])

    captured = {}

    def fake_get_equipamentos_options_read_model(**kwargs):
        captured.update(kwargs)
        return [
            {
                "id": 3,
                "nome": "PR-ABC",
                "tipo": "AS350",
                "ativo": 1,
                "categoria_financeira": "b",
                "campo_interno": "nao_deve_vazar",
            }
        ]

    monkeypatch.setattr(
        cadastros_api,
        "get_equipamentos_options_read_model",
        fake_get_equipamentos_options_read_model,
    )

    response = client.get(
        "/api/v1/equipamentos/options?equipamento_id=3",
        headers={"X-Request-ID": "req-equip-options"},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert captured["selected_equipment_id"] == 3
    assert payload["success"] is True
    assert payload["status"] == 200
    assert payload["code"] == "equipamentos_options_ok"
    assert payload["message"]
    assert payload["request_id"] == "req-equip-options"
    assert payload["correlation_id"] == "req-equip-options"
    assert payload["options"] == [
        {
            "id": 3,
            "value": 3,
            "label": "PR-ABC / AS350",
            "nome": "PR-ABC",
            "tipo": "AS350",
            "status": "ativo",
            "ativo": True,
            "categoria_financeira": "b",
            "raw": {
                "id": 3,
                "nome": "PR-ABC",
                "tipo": "AS350",
                "ativo": True,
                "categoria_financeira": "b",
            },
        }
    ]
    assert "campo_interno" not in payload["options"][0]
    assert "campo_interno" not in payload["options"][0]["raw"]


def test_api_equipamentos_options_allows_null_finance_category(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch, permissions=["equipamentos:view"])

    def fake_get_equipamentos_options_read_model(**_kwargs):
        return [
            {
                "id": 4,
                "nome": "PR-SEM",
                "tipo": "C172",
                "ativo": 1,
                "categoria_financeira": None,
            }
        ]

    monkeypatch.setattr(
        cadastros_api,
        "get_equipamentos_options_read_model",
        fake_get_equipamentos_options_read_model,
    )

    response = client.get("/api/v1/equipamentos/options")

    assert response.status_code == 200
    option = response.get_json()["options"][0]
    assert option["categoria_financeira"] is None
    assert option["raw"]["categoria_financeira"] is None
