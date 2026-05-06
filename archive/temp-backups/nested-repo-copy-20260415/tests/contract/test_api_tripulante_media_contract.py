from __future__ import annotations

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.api.http.cadastros import routes as tripulante_media_api


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
        "id": 31,
        "nome": "Operador Midia",
        "login": "midia_api",
        "email": "midia.api@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": '["tripulantes:view","tripulantes:edit","tripulantes_file:view","tripulantes_file:create","tripulantes_file:delete"]',
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
        json={"login": "midia_api", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 200


def test_api_tripulante_photo_get_returns_binary(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        tripulante_media_api,
        "get_tripulante_photo",
        lambda tripulante_id: {"payload_bytes": b"img", "mime_type": "image/png", "has_photo": True},
    )

    response = client.get("/api/v1/tripulantes/7/photo")

    assert response.status_code == 200
    assert response.data == b"img"
    assert response.mimetype == "image/png"


def test_api_tripulante_photo_post_returns_state_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        tripulante_media_api,
        "save_tripulante_photo",
        lambda payload, tripulante_id: {"tripulante_id": tripulante_id, "has_photo": True},
    )

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/tripulantes/7/photo",
        json={"foto_base64": "data:image/png;base64,aGVsbG8="},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "tripulante_photo_saved"
    assert payload["photo"]["has_photo"] is True


def test_api_tripulante_files_list_returns_items(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        tripulante_media_api,
        "list_tripulante_files",
        lambda tripulante_id: [
            {
                "id": 91,
                "tripulante_id": tripulante_id,
                "tipo_documento": "geral",
                "nome_original": "doc.pdf",
                "nome_interno": "doc_interno.pdf",
                "mime_type": "application/pdf",
                "tamanho_bytes": 123,
                "storage_ref": "fs:tripulantes/7/documentos/doc.pdf",
                "arquivo_hash": "abc",
                "status": "ativo",
                "enviado_por": 31,
                "enviado_em": None,
                "substitui_arquivo_id": None,
                "removido_por": None,
                "removido_em": None,
                "motivo_status": "",
            }
        ],
    )

    response = client.get("/api/v1/tripulantes/7/files")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "tripulante_files_ok"
    assert payload["items"][0]["id"] == 91


def test_api_tripulante_files_upload_returns_created_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        tripulante_media_api,
        "upload_tripulante_file",
        lambda payload, tripulante_id, enviado_por: {
            "id": 92,
            "tripulante_id": tripulante_id,
            "tipo_documento": "geral",
            "nome_original": "novo.pdf",
            "nome_interno": "novo_interno.pdf",
            "mime_type": "application/pdf",
            "tamanho_bytes": 456,
            "storage_ref": "fs:tripulantes/7/documentos/novo.pdf",
            "arquivo_hash": "def",
            "status": "ativo",
            "enviado_por": enviado_por,
            "enviado_em": None,
            "substitui_arquivo_id": None,
            "removido_por": None,
            "removido_em": None,
            "motivo_status": "",
        },
    )

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/tripulantes/7/files",
        json={"filename": "novo.pdf", "arquivo_base64": "JVBERi0xLjQKZW5kb2JqCiUlRU9G", "tipo_documento": "geral"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "tripulante_file_created"
    assert payload["file"]["id"] == 92


def test_api_tripulante_file_get_returns_binary(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        tripulante_media_api,
        "get_tripulante_file",
        lambda tripulante_id, arquivo_id: {
            "nome_original": "arquivo.pdf",
            "mime_type": "application/pdf",
            "payload_bytes": b"%PDF-1.4\n%%EOF",
        },
    )

    response = client.get("/api/v1/tripulantes/7/files/99")

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")


def test_api_tripulante_file_delete_returns_updated_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        tripulante_media_api,
        "delete_tripulante_file",
        lambda tripulante_id, arquivo_id, removido_por: {
            "id": arquivo_id,
            "tripulante_id": tripulante_id,
            "tipo_documento": "geral",
            "nome_original": "arquivo.pdf",
            "nome_interno": "arquivo.pdf",
            "mime_type": "application/pdf",
            "tamanho_bytes": 456,
            "storage_ref": "fs:tripulantes/7/documentos/arquivo.pdf",
            "arquivo_hash": "ghi",
            "status": "removido",
            "enviado_por": 31,
            "enviado_em": None,
            "substitui_arquivo_id": None,
            "removido_por": removido_por,
            "removido_em": None,
            "motivo_status": "Removido manualmente via API.",
        },
    )

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.delete(
        "/api/v1/tripulantes/7/files/99",
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "tripulante_file_deleted"
    assert payload["file"]["status"] == "removido"
