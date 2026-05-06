from __future__ import annotations

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.api.http.cadastros import routes as tripulantes_api


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


def _auth_user_row():
    return {
        "id": 21,
        "nome": "Operador Tripulantes",
        "login": "trip_api",
        "email": "trip.api@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": '["tripulantes:view","tripulantes:create","tripulantes:edit","tripulantes:delete"]',
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _sample_tripulante(*, tripulante_id: int = 7):
    return {
        "id": tripulante_id,
        "nome": "Lucas Silva",
        "cpf": "123.456.789-01",
        "licenca_anac": "123456",
        "email": "lucas@local.test",
        "telefone": "11999999999",
        "base": "Sao Paulo",
        "status": "Ativo",
        "observacoes": "Observacao de teste",
        "ativo": True,
        "funcao_operacional": "comandante",
        "categoria_operacional": "A",
        "sdea_ativo": True,
        "instrutor_ativo": False,
        "checador_ativo": False,
        "elegivel_adicional_excepcional": True,
        "foto_storage_ref": "",
        "foto_mime_type": "",
        "possui_foto": False,
    }


def _authenticate_client(client, monkeypatch):
    row = _auth_user_row()
    fake_db = _SingleUserDB(row)
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "trip_api", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 200


def test_api_tripulantes_list_returns_formal_collection(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(tripulantes_api, "get_db", lambda: object())
    monkeypatch.setattr(tripulantes_api, "count_tripulantes", lambda _db, **_filters: 1)
    monkeypatch.setattr(
        tripulantes_api,
        "fetch_tripulante_list_page",
        lambda _db, **_kwargs: [_sample_tripulante()],
    )

    response = client.get("/api/v1/tripulantes?nome=Lucas")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "tripulantes_list_ok"
    assert payload["filters"]["nome"] == "Lucas"
    assert payload["pagination"]["total"] == 1
    assert payload["items"][0]["nome"] == "Lucas Silva"
    assert payload["items"][0]["links"]["self"] == "/api/v1/tripulantes/7"


def test_api_tripulantes_options_returns_form_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(tripulantes_api, "get_db", lambda: object())
    monkeypatch.setattr(
        tripulantes_api,
        "fetch_base_options",
        lambda _db, _selected_base=None: [{"nome": "Sao Paulo", "uf": "SP"}],
    )

    response = client.get("/api/v1/tripulantes/options")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "tripulantes_options_ok"
    assert payload["options"]["bases"][0]["nome"] == "Sao Paulo"
    assert "Ativo" in payload["options"]["status"]


def test_api_tripulante_get_returns_404_for_missing_record(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(tripulantes_api, "get_db", lambda: object())
    monkeypatch.setattr(tripulantes_api, "fetch_tripulante_detail", lambda _db, **_kwargs: None)

    response = client.get("/api/v1/tripulantes/999")

    assert response.status_code == 404
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["code"] == "tripulante_not_found"


def test_api_tripulante_create_returns_created_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        tripulantes_api,
        "save_tripulante",
        lambda payload, tripulante_id=None: {"operation": "created", "tripulante": _sample_tripulante()},
    )

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/tripulantes",
        json={
            "nome": "Lucas Silva",
            "cpf": "123.456.789-01",
            "licenca_anac": "123456",
            "base": "Sao Paulo",
            "status": "Ativo",
            "funcao_operacional": "comandante",
            "categoria_operacional": "A",
        },
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "tripulante_created"
    assert payload["operation"] == "created"
    assert payload["tripulante"]["id"] == 7


def test_api_tripulante_update_propagates_not_found_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    def _raise_not_found(_payload, tripulante_id=None):
        raise tripulantes_api.TripulanteNotFoundError("Tripulante não encontrado.")

    monkeypatch.setattr(tripulantes_api, "save_tripulante", _raise_not_found)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.put(
        "/api/v1/tripulantes/77",
        json={"nome": "Nao existe"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 404
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["code"] == "tripulante_not_found"


def test_api_tripulante_delete_can_return_inactivated_operation(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        tripulantes_api,
        "delete_tripulante",
        lambda tripulante_id: {
            "operation": "inactivated",
            "message": "Tripulante inativado porque existem vínculos históricos.",
            "tripulante": _sample_tripulante(tripulante_id=tripulante_id),
        },
    )

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.delete(
        "/api/v1/tripulantes/7",
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "tripulante_inactivated"
    assert payload["operation"] == "inactivated"
    assert payload["tripulante"]["id"] == 7
