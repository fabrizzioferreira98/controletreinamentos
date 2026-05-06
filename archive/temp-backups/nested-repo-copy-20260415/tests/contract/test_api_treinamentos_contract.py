from __future__ import annotations

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.api.http.cadastros import routes as treinamentos_api


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
        "id": 41,
        "nome": "Operador Treinamentos",
        "login": "trein_api",
        "email": "trein.api@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": '["treinamentos:view","treinamentos:create","treinamentos:edit","treinamentos:delete","treinamentos_anexos:view","treinamentos_anexos:create","treinamentos_anexos:delete"]',
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch):
    row = _auth_user_row()
    fake_db = _SingleUserDB(row)
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)
    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "trein_api", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 200


def _sample_treinamento(*, treinamento_id: int = 55):
    return {
        "id": treinamento_id,
        "tripulante_id": 7,
        "equipamento_id": 3,
        "tipo_treinamento_id": 2,
        "tripulante_nome": "Lucas Silva",
        "equipamento_nome": "AS350",
        "tipo_treinamento_nome": "CQ IFR",
        "data_realizacao": "2026-04-01",
        "data_vencimento": "2026-10-01",
        "observacao": "Observacao",
        "status_calculado": "regular",
    }


def _sample_attachment(*, treinamento_id: int = 55, attachment_id: int = 77):
    return {
        "id": attachment_id,
        "treinamento_id": treinamento_id,
        "nome_original": "anexo.pdf",
        "nome_interno": "anexo.pdf",
        "mime_type": "application/pdf",
        "tamanho_bytes": 123,
        "storage_ref": "fs:tripulantes/7/treinamentos/55/anexo.pdf",
        "arquivo_hash": "abc",
        "status": "ativo",
        "enviado_por": 41,
        "enviado_em": None,
        "enviado_por_nome": "Operador Treinamentos",
    }


def test_api_treinamentos_list_returns_collection_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(treinamentos_api, "get_db", lambda: object())
    monkeypatch.setattr(
        treinamentos_api,
        "count_treinamentos",
        lambda _db, **_filters: {"total": 1, "vencido": 0, "a_vencer": 0, "regular": 1, "sem_informacao": 0},
    )
    monkeypatch.setattr(treinamentos_api, "build_training_filters", lambda **_filters: ("", ()))
    monkeypatch.setattr(treinamentos_api, "fetch_training_page", lambda _db, *_args, **_kwargs: [_sample_treinamento()])

    response = client.get("/api/v1/treinamentos?status=regular")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "treinamentos_list_ok"
    assert payload["items"][0]["id"] == 55
    assert payload["summary"]["regular"] == 1


def test_api_treinamentos_options_returns_form_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        treinamentos_api,
        "fetch_training_options",
        lambda _db, **_kwargs: {
            "tripulantes": [{"id": 7, "nome": "Lucas Silva"}],
            "equipamentos": [{"id": 3, "nome": "AS350"}],
            "tipos": [{"id": 2, "nome": "CQ IFR", "periodicidade_meses": 6, "exige_equipamento": True}],
            "attachments": [],
        },
    )
    monkeypatch.setattr(treinamentos_api, "get_db", lambda: object())

    response = client.get("/api/v1/treinamentos/options")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "treinamentos_options_ok"
    assert payload["options"]["tripulantes"][0]["id"] == 7


def test_api_treinamento_create_returns_created_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        treinamentos_api,
        "save_treinamento",
        lambda payload, treinamento_id=None: {
            "operation": "created",
            "treinamento": _sample_treinamento(),
            "attachments": [],
        },
    )

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/treinamentos",
        json={
            "tripulante_id": 7,
            "equipamento_id": 3,
            "tipo_treinamento_id": 2,
            "data_realizacao": "2026-04-01",
            "data_vencimento": "2026-10-01",
        },
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "treinamento_created"
    assert payload["treinamento"]["id"] == 55


def test_api_treinamento_get_returns_detail_with_attachments(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(treinamentos_api, "get_db", lambda: object())
    monkeypatch.setattr(treinamentos_api, "fetch_treinamento_detail", lambda _db, **_kwargs: _sample_treinamento())
    monkeypatch.setattr(treinamentos_api, "list_treinamento_attachments", lambda **_kwargs: [_sample_attachment()])

    response = client.get("/api/v1/treinamentos/55")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["treinamento"]["attachments"][0]["id"] == 77


def test_api_treinamento_attachments_upload_returns_created_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        treinamentos_api,
        "upload_treinamento_attachment",
        lambda payload, treinamento_id, enviado_por: _sample_attachment(treinamento_id=treinamento_id, attachment_id=88),
    )

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/treinamentos/55/attachments",
        json={"filename": "anexo.pdf", "arquivo_base64": "JVBERi0xLjQKZW5kb2JqCiUlRU9G"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "treinamento_attachment_created"
    assert payload["attachment"]["id"] == 88


def test_api_treinamento_attachment_get_returns_binary(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        treinamentos_api,
        "get_treinamento_attachment",
        lambda treinamento_id, anexo_id: {
            "nome_original": "anexo.pdf",
            "mime_type": "application/pdf",
            "payload_bytes": b"%PDF-1.4\n%%EOF",
        },
    )

    response = client.get("/api/v1/treinamentos/55/attachments/77")

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")


def test_api_treinamento_attachment_delete_returns_deleted_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        treinamentos_api,
        "delete_treinamento_attachment",
        lambda treinamento_id, anexo_id: _sample_attachment(treinamento_id=treinamento_id, attachment_id=anexo_id),
    )

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.delete(
        "/api/v1/treinamentos/55/attachments/77",
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "treinamento_attachment_deleted"
    assert payload["attachment"]["id"] == 77
