from __future__ import annotations

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.blueprints.cadastros import api_routes as tripulantes_api
from backend.src.controle_treinamentos.contracts.tripulantes import serialize_tripulante_detail


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
        "base_operacional": "Sao Paulo",
        "base_operacional_id": 1,
        "base_operacional_owner": "pilotos.base_id",
        "base_snapshot_compat": "Sao Paulo",
        "base_snapshot_compat_source": "tripulantes.base",
        "piloto_base_id": 1,
        "piloto_base_nome": "Sao Paulo",
        "status": "Ativo",
        "status_operacional": "Ativo",
        "status_operacional_owner": "pilotos.status",
        "status_snapshot_compat": "Ativo",
        "status_snapshot_compat_source": "tripulantes.status",
        "piloto_status": "ativo",
        "observacoes": "Observacao de teste",
        "ativo": True,
        "funcao_operacional": "comandante",
        "categoria_operacional": "A",
        "sdea_ativo": True,
        "sdea_icao_validade": "2026-04-30",
        "instrutor_ativo": True,
        "instrutor_inicio": "2026-04-01",
        "instrutor_fim": "",
        "checador_ativo": True,
        "checador_inicio": "2026-04-01",
        "checador_fim": "",
        "checador_carta_designacao": "CHK-001",
        "elegivel_adicional_excepcional": True,
        "foto_storage_ref": "",
        "foto_mime_type": "",
        "foto_base64": "",
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

    captured = {}

    def fake_list_tripulantes_read_model(**kwargs):
        captured.update(kwargs)
        return {"items": [_sample_tripulante()], "page": 1, "per_page": 20, "total": 1}

    monkeypatch.setattr(
        tripulantes_api,
        "list_tripulantes_read_model",
        fake_list_tripulantes_read_model,
    )

    response = client.get("/api/v1/tripulantes?nome=Lucas")

    assert response.status_code == 200
    payload = response.get_json()
    assert captured["filters"]["nome"] == "Lucas"
    assert captured["page"] == 1
    assert captured["per_page"] == 20
    assert payload["success"] is True
    assert payload["code"] == "tripulantes_list_ok"
    assert payload["filters"]["nome"] == "Lucas"
    assert payload["pagination"]["total"] == 1
    assert payload["items"][0]["nome"] == "Lucas Silva"
    assert payload["items"][0]["base"] == "Sao Paulo"
    assert payload["items"][0]["base_operacional"] == "Sao Paulo"
    assert payload["items"][0]["base_operacional_owner"] == "pilotos.base_id"
    assert payload["items"][0]["base_snapshot_compat"] == "Sao Paulo"
    assert payload["items"][0]["base_snapshot_compat_source"] == "tripulantes.base"
    assert payload["items"][0]["status"] == "Ativo"
    assert payload["items"][0]["status_operacional"] == "Ativo"
    assert payload["items"][0]["status_operacional_owner"] == "pilotos.status"
    assert payload["items"][0]["status_snapshot_compat"] == "Ativo"
    assert payload["items"][0]["status_snapshot_compat_source"] == "tripulantes.status"
    assert payload["items"][0]["sdea_icao_validade"] == "2026-04-30"
    assert payload["items"][0]["instrutor_inicio"] == "2026-04-01"
    assert payload["items"][0]["checador_carta_designacao"] == "CHK-001"
    assert payload["items"][0]["photo_policy"]["legacy_write"] == "blocked_new_writes"
    assert payload["items"][0]["photo_policy"]["legacy_read"] == "isolated_fallback"
    assert payload["items"][0]["links"]["self"] == "/api/v1/tripulantes/7"
    assert payload["items"][0]["links"]["files"] == "/api/v1/tripulantes/7/files"
    assert payload["items"][0]["links"]["files_api"] == "/api/v1/tripulantes/7/files"
    assert payload["items"][0]["links"]["files_legacy"] == "/tripulantes/7/file"


def test_api_tripulantes_options_returns_form_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    captured = {}

    def fake_get_tripulantes_options_read_model(**kwargs):
        captured.update(kwargs)
        return {"bases": [{"nome": "Sao Paulo", "uf": "SP"}]}

    monkeypatch.setattr(
        tripulantes_api,
        "get_tripulantes_options_read_model",
        fake_get_tripulantes_options_read_model,
    )

    response = client.get("/api/v1/tripulantes/options")

    assert response.status_code == 200
    payload = response.get_json()
    assert captured["base"] is None
    assert payload["success"] is True
    assert payload["code"] == "tripulantes_options_ok"
    assert payload["options"]["bases"][0]["nome"] == "Sao Paulo"
    assert "Ativo" in payload["options"]["status"]


def test_api_tripulante_get_returns_404_for_missing_record(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    captured = {}

    def fake_get_tripulante_detail_read_model(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(tripulantes_api, "get_tripulante_detail_read_model", fake_get_tripulante_detail_read_model)

    response = client.get("/api/v1/tripulantes/999")

    assert response.status_code == 404
    payload = response.get_json()
    assert captured["tripulante_id"] == 999
    assert payload["success"] is False
    assert payload["code"] == "tripulante_not_found"


def test_api_tripulante_operational_periods_list_keeps_edit_form_compat(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    captured = {}

    def fake_get_tripulante_detail_read_model(**kwargs):
        captured.update(kwargs)
        return _sample_tripulante(tripulante_id=11)

    monkeypatch.setattr(tripulantes_api, "get_tripulante_detail_read_model", fake_get_tripulante_detail_read_model)

    response = client.get("/api/v1/tripulantes/11/periodos-operacionais")

    assert response.status_code == 200
    payload = response.get_json()
    assert captured["tripulante_id"] == 11
    assert payload["success"] is True
    assert payload["code"] == "tripulante_periodos_operacionais_ok"
    assert payload["items"] == []


def test_api_tripulante_operational_periods_list_preserves_missing_tripulante_404(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(tripulantes_api, "get_tripulante_detail_read_model", lambda **_kwargs: None)

    response = client.get("/api/v1/tripulantes/999/periodos-operacionais")

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


def test_tripulante_contract_only_exposes_photo_url_when_photo_is_servible(monkeypatch):
    app = create_app()
    monkeypatch.setattr(
        "backend.src.controle_treinamentos.application.tripulante_media.read_media_bytes",
        lambda _ref, fallback_bytes=None: None,
    )
    row = _sample_tripulante()
    row["foto_storage_ref"] = "fs:tripulantes/7/foto/quebrada.jpg"
    row["foto_mime_type"] = "image/jpeg"
    row["possui_foto"] = True

    with app.test_request_context():
        payload = serialize_tripulante_detail(row)

    assert payload["possui_foto"] is False
    assert payload["photo_compat_residual"] is False
    assert payload["photo_url"] is None
    assert payload["links"]["photo"] is None


def test_tripulante_contract_recognizes_legacy_base64_photo(monkeypatch):
    app = create_app()
    monkeypatch.setattr(
        "backend.src.controle_treinamentos.application.tripulante_media.read_media_bytes",
        lambda _ref, fallback_bytes=None: None,
    )
    row = _sample_tripulante()
    row["foto_base64"] = "data:image/png;base64,aW1n"

    with app.test_request_context():
        payload = serialize_tripulante_detail(row)

    assert payload["possui_foto"] is True
    assert payload["photo_source"] == "base64"
    assert payload["photo_compat_residual"] is True
    assert payload["photo_compat_source"] == "foto_base64"
    assert payload["photo_policy"]["canonical_owner"] == "tripulantes.foto_storage_ref"
    assert payload["photo_policy"]["compat_residual"] is True
    assert payload["photo_url"] == "/api/v1/tripulantes/7/photo"
    assert payload["links"]["photo"] == "/api/v1/tripulantes/7/photo"


def test_tripulante_contract_prefers_linked_pilot_status_and_keeps_snapshot_compat(monkeypatch):
    app = create_app()
    monkeypatch.setattr(
        "backend.src.controle_treinamentos.application.tripulante_media.read_media_bytes",
        lambda _ref, fallback_bytes=None: None,
    )
    row = _sample_tripulante()
    row["status"] = "Ativo"
    row["status_snapshot_compat"] = "Ativo"
    row["piloto_status"] = "folga"

    with app.test_request_context():
        payload = serialize_tripulante_detail(row)

    assert payload["status"] == "Folga"
    assert payload["status_operacional"] == "Folga"
    assert payload["status_operacional_owner"] == "pilotos.status"
    assert payload["status_snapshot_compat"] == "Ativo"
    assert payload["status_snapshot_compat_source"] == "tripulantes.status"


def test_tripulante_contract_prefers_linked_pilot_base_and_keeps_snapshot_compat(monkeypatch):
    app = create_app()
    monkeypatch.setattr(
        "backend.src.controle_treinamentos.application.tripulante_media.read_media_bytes",
        lambda _ref, fallback_bytes=None: None,
    )
    row = _sample_tripulante()
    row["base"] = "Belem"
    row["base_snapshot_compat"] = "Belem"
    row["piloto_base_id"] = 12
    row["piloto_base_nome"] = "Manaus"

    with app.test_request_context():
        payload = serialize_tripulante_detail(row)

    assert payload["base"] == "Manaus"
    assert payload["base_operacional"] == "Manaus"
    assert payload["base_operacional_id"] == 12
    assert payload["base_operacional_owner"] == "pilotos.base_id"
    assert payload["base_snapshot_compat"] == "Belem"
    assert payload["base_snapshot_compat_source"] == "tripulantes.base"


def test_tripulante_contract_keeps_snapshot_residual_out_of_operational_owner(monkeypatch):
    app = create_app()
    monkeypatch.setattr(
        "backend.src.controle_treinamentos.application.tripulante_media.read_media_bytes",
        lambda _ref, fallback_bytes=None: None,
    )
    row = _sample_tripulante()
    row["base"] = "Belem"
    row["base_snapshot_compat"] = "Belem"
    row["piloto_base_id"] = None
    row["piloto_base_nome"] = None
    row["status"] = "Ativo"
    row["status_snapshot_compat"] = "Ativo"
    row["piloto_status"] = None

    with app.test_request_context():
        payload = serialize_tripulante_detail(row)

    assert payload["base"] == ""
    assert payload["base_operacional"] == ""
    assert payload["base_operacional_owner"] == "pilotos.base_id"
    assert payload["base_snapshot_compat"] == "Belem"
    assert payload["base_snapshot_compat_source"] == "tripulantes.base"
    assert payload["status"] == ""
    assert payload["status_operacional"] == ""
    assert payload["status_operacional_owner"] == "pilotos.status"
    assert payload["status_snapshot_compat"] == "Ativo"
    assert payload["status_snapshot_compat_source"] == "tripulantes.status"
