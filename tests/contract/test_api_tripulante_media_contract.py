from __future__ import annotations

import base64
from datetime import datetime
from io import BytesIO

import pytest
from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.application import tripulante_media as tripulante_media_app
from backend.src.controle_treinamentos.application.tripulante_media import (
    get_tripulante_photo,
    resolve_tripulante_photo_state,
)
from backend.src.controle_treinamentos.api.http.cadastros import routes as tripulante_media_api
from backend.src.controle_treinamentos.core.domain_errors import DomainUnavailableError
from backend.src.controle_treinamentos.infra.media_storage import storage_ref_to_path

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
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


class _PhotoCursor:
    def __init__(self, row=None, *, rowcount=1):
        self._row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self._row


class _MutableTripulantePhotoDB:
    def __init__(self):
        self.conn = self
        self.row = {
            "id": 7,
            "nome": "Lucas Silva",
            "foto_base64": "",
            "foto_storage_ref": "",
            "foto_mime_type": "",
            "possui_foto": False,
        }
        self.committed = False
        self.rolled_back = False
        self.last_update_query = ""
        self.audit_events = []

    def execute(self, query, params=()):
        compact = " ".join(query.split())
        if compact.startswith("SAVEPOINT") or compact.startswith("RELEASE SAVEPOINT") or compact.startswith("ROLLBACK TO SAVEPOINT"):
            return _PhotoCursor(rowcount=0)
        if compact.startswith("SELECT") and "FROM tripulantes" in compact and ("WHERE id = %s" in compact or "WHERE t.id = %s" in compact):
            return _PhotoCursor(dict(self.row))
        if compact.startswith("UPDATE tripulantes") and "foto_storage_ref = %s" in compact:
            self.last_update_query = compact
            self.row.update(
                {
                    "foto_base64": None,
                    "foto_storage_ref": params[0],
                    "foto_mime_type": params[1],
                    "possui_foto": params[2],
                }
            )
            return _PhotoCursor(rowcount=1)
        if compact.startswith("INSERT INTO auditoria_eventos"):
            self.audit_events.append(params)
            return _PhotoCursor(rowcount=1)
        raise AssertionError(f"Unexpected query: {query}")

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def _auth_user_row():
    return {
        "id": 31,
        "nome": "Operador Midia",
        "login": "midia_api",
        "email": "midia.api@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": '["tripulantes:view","tripulantes:edit","tripulantes_file:view","tripulantes_file:create","tripulantes_file:delete","tripulantes_file:replace"]',
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
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-File-Access-Action"] == "preview"
    assert response.headers["X-File-Link-Policy"] == "authenticated-session"
    assert response.headers["X-File-Link-Expires"] == "session"


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


def test_api_tripulante_photo_post_reports_storage_unavailable(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    def _raise_storage_unavailable(payload, tripulante_id):
        raise DomainUnavailableError(
            "Nao foi possivel confirmar a persistencia fisica da foto.",
            code="tripulante_photo_blob_unavailable",
        )

    monkeypatch.setattr(tripulante_media_api, "save_tripulante_photo", _raise_storage_unavailable)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/tripulantes/7/photo",
        json={"foto_base64": "data:image/png;base64,aGVsbG8="},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["code"] == "tripulante_photo_blob_unavailable"


def test_api_tripulante_photo_upload_persists_blob_and_get_returns_binary(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)
    db = _MutableTripulantePhotoDB()
    monkeypatch.setattr(tripulante_media_app, "get_db", lambda: db)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/tripulantes/7/photo",
        json={"foto_base64": "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode("ascii")},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert db.committed is True
    assert len(db.audit_events) == 1
    assert db.audit_events[0][0] == "tripulante_photo"
    assert db.audit_events[0][2] == "update"
    assert db.audit_events[0][5] == 31
    assert db.row["foto_base64"] is None
    assert db.row["foto_mime_type"] == "image/png"
    assert db.row["possui_foto"] is True
    assert "foto_base64 = NULL" in db.last_update_query
    assert "foto_base64 = %s" not in db.last_update_query
    assert db.row["foto_storage_ref"].startswith("fs:tripulantes/tripulante-7/fotos/foto-")
    target = storage_ref_to_path(db.row["foto_storage_ref"])
    assert target is not None
    assert target.exists()
    assert target.read_bytes() == PNG_BYTES

    photo_response = client.get("/api/v1/tripulantes/7/photo")

    assert photo_response.status_code == 200
    assert photo_response.data == PNG_BYTES
    assert photo_response.mimetype == "image/png"


def test_save_tripulante_photo_rejects_invalid_image_content_before_write(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    db = _MutableTripulantePhotoDB()
    monkeypatch.setattr(tripulante_media_app, "get_db", lambda: db)

    def fail_write(*_args, **_kwargs):
        raise AssertionError("invalid photo content reached storage")

    monkeypatch.setattr(tripulante_media_app, "write_tripulante_photo", fail_write)

    with pytest.raises(tripulante_media_app.TripulanteValidationError):
        tripulante_media_app.save_tripulante_photo(
            {"foto_base64": "data:image/png;base64," + base64.b64encode(b"not-a-real-image").decode("ascii")},
            tripulante_id=7,
        )

    assert db.committed is False


def test_save_tripulante_photo_rejects_unsupported_photo_type(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    db = _MutableTripulantePhotoDB()
    monkeypatch.setattr(tripulante_media_app, "get_db", lambda: db)

    with pytest.raises(tripulante_media_app.TripulanteValidationError):
        tripulante_media_app.save_tripulante_photo(
            {"foto_base64": "data:image/gif;base64," + base64.b64encode(b"GIF89a").decode("ascii")},
            tripulante_id=7,
        )

    assert db.committed is False


def test_save_tripulante_photo_refuses_metadata_when_blob_is_not_readable(monkeypatch, tmp_path):
    monkeypatch.setenv("MEDIA_STORAGE_ROOT", str(tmp_path))
    db = _MutableTripulantePhotoDB()
    monkeypatch.setattr(tripulante_media_app, "get_db", lambda: db)
    monkeypatch.setattr(
        tripulante_media_app,
        "write_tripulante_photo",
        lambda *_args, **_kwargs: "fs:tripulantes/tripulante-7/fotos/missing.png",
    )
    monkeypatch.setattr(tripulante_media_app, "read_media_bytes", lambda *_args, **_kwargs: None)

    with pytest.raises(DomainUnavailableError):
        tripulante_media_app.save_tripulante_photo(
            {"foto_base64": "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode("ascii")},
            tripulante_id=7,
        )

    assert db.committed is False
    assert db.rolled_back is True
    assert db.row["foto_storage_ref"] == ""
    assert db.row["possui_foto"] is False


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
    assert isinstance(payload["items"][0]["id"], int)
    assert payload["items"][0]["enviado_em"] is None
    assert payload["items"][0]["substitui_arquivo_id"] is None
    assert payload["items"][0]["removido_por"] is None
    assert payload["items"][0]["removido_em"] is None
    assert payload["items"][0]["document_policy"]["kind"] == "pdf_evidence"
    assert payload["items"][0]["document_policy"]["versioning"] == "replace_marks_previous_as_substituido"


def test_api_tripulante_files_list_normalizes_ids_dates_and_compat_boundary(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        tripulante_media_api,
        "list_tripulante_files",
        lambda tripulante_id: [
            {
                "id": "91",
                "tripulante_id": str(tripulante_id),
                "tipo_documento": "cma",
                "nome_original": "doc.pdf",
                "nome_interno": "doc_interno.pdf",
                "mime_type": "",
                "tamanho_bytes": "123",
                "storage_ref": "legacy:database",
                "blob_storage": "database",
                "blob_available": 1,
                "blob_status": "legacy_database",
                "compat_residual": 1,
                "compat_source": "arquivo_pdf_blob",
                "arquivo_hash": "abc",
                "status": "substituido",
                "enviado_por": "31",
                "enviado_em": datetime(2026, 4, 2, 10, 30),
                "substitui_arquivo_id": "90",
                "removido_por": "32",
                "removido_em": datetime(2026, 4, 3, 11, 45),
                "motivo_status": None,
                "payload_bytes": b"%PDF",
                "screen_badge": "transient",
            }
        ],
    )

    response = client.get("/api/v1/tripulantes/7/files")

    assert response.status_code == 200
    item = response.get_json()["items"][0]
    assert set(item) == {
        "id",
        "tripulante_id",
        "tipo_documento",
        "nome_original",
        "nome_interno",
        "mime_type",
        "tamanho_bytes",
        "storage_ref",
        "blob_storage",
        "blob_available",
        "blob_status",
        "compat_residual",
        "compat_source",
        "blob_policy",
        "arquivo_hash",
        "status",
        "status_label",
        "enviado_por",
        "enviado_em",
        "substitui_arquivo_id",
        "removido_por",
        "removido_em",
        "motivo_status",
        "links",
        "access_policy",
        "document_policy",
    }
    assert item["id"] == 91
    assert item["tripulante_id"] == 7
    assert item["mime_type"] == "application/pdf"
    assert item["tamanho_bytes"] == 123
    assert item["blob_available"] is True
    assert item["compat_residual"] is True
    assert item["compat_source"] == "arquivo_pdf_blob"
    assert item["blob_policy"]["legacy_write"] == "blocked_new_writes"
    assert item["blob_policy"]["legacy_read"] == "isolated_fallback"
    assert item["blob_policy"]["compat_residual"] is True
    assert item["enviado_por"] == 31
    assert item["enviado_em"] == "2026-04-02T10:30:00"
    assert item["substitui_arquivo_id"] == 90
    assert item["removido_por"] == 32
    assert item["removido_em"] == "2026-04-03T11:45:00"
    assert item["motivo_status"] == ""
    assert item["links"]["download"] == "/api/v1/tripulantes/7/files/91?download=1"
    assert item["access_policy"]["preview_permission"] == "tripulantes_file:view"
    assert item["document_policy"]["versioning"] == "replace_marks_previous_as_substituido"


def test_api_tripulante_files_upload_returns_created_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)
    captured_payload = {}

    def fake_upload(payload, tripulante_id, enviado_por):
        captured_payload.update(payload)
        return {
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
        }

    monkeypatch.setattr(tripulante_media_api, "upload_tripulante_file", fake_upload)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/tripulantes/7/files",
        json={"filename": "novo.pdf", "content_base64": "JVBERi0xLjQKZW5kb2JqCiUlRU9G", "tipo_documento": "geral"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "tripulante_file_created"
    assert payload["upload"] == {
        "source": "json",
        "filename": "novo.pdf",
        "original_filename": "novo.pdf",
        "filename_source": "upload",
        "filename_was_fallback": False,
        "content_type": "application/pdf",
        "content_type_source": "fallback",
        "encoding": "base64",
    }
    assert payload["file"]["id"] == 92
    assert payload["file"]["document_policy"]["kind"] == "pdf_evidence"
    assert payload["file"]["blob_policy"]["canonical_owner"] == "tripulante_arquivos_pdf.storage_ref"
    assert captured_payload["content_base64"] == "JVBERi0xLjQKZW5kb2JqCiUlRU9G"
    assert captured_payload["arquivo_base64"] == "JVBERi0xLjQKZW5kb2JqCiUlRU9G"


def test_api_tripulante_files_upload_marks_json_filename_fallback(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    def fake_upload(payload, tripulante_id, enviado_por):
        return {
            "id": 95,
            "tripulante_id": tripulante_id,
            "tipo_documento": "geral",
            "nome_original": payload["filename_fallback"],
            "nome_interno": "documento-interno.pdf",
            "mime_type": "application/pdf",
            "tamanho_bytes": 456,
            "storage_ref": "fs:tripulantes/7/documentos/documento-interno.pdf",
            "arquivo_hash": "fallback",
            "status": "ativo",
            "enviado_por": enviado_por,
            "enviado_em": None,
            "substitui_arquivo_id": None,
            "removido_por": None,
            "removido_em": None,
            "motivo_status": "",
        }

    monkeypatch.setattr(tripulante_media_api, "upload_tripulante_file", fake_upload)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/tripulantes/7/files",
        json={"content_base64": "JVBERi0xLjQKZW5kb2JqCiUlRU9G", "tipo_documento": "geral"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["upload"]["filename"] == "documento_tripulante.pdf"
    assert payload["upload"]["original_filename"] == ""
    assert payload["upload"]["filename_source"] == "fallback"
    assert payload["upload"]["filename_was_fallback"] is True


def test_api_tripulante_files_upload_accepts_multipart_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)
    captured_payload = {}

    def fake_upload(payload, tripulante_id, enviado_por):
        captured_payload.update(payload)
        return {
            "id": 94,
            "tripulante_id": tripulante_id,
            "tipo_documento": "geral",
            "nome_original": "multipart.pdf",
            "nome_interno": "multipart_interno.pdf",
            "mime_type": "application/pdf",
            "tamanho_bytes": 17,
            "storage_ref": "fs:tripulantes/7/documentos/multipart.pdf",
            "arquivo_hash": "multipart",
            "status": "ativo",
            "enviado_por": enviado_por,
            "enviado_em": None,
            "substitui_arquivo_id": None,
            "removido_por": None,
            "removido_em": None,
            "motivo_status": "",
        }

    monkeypatch.setattr(tripulante_media_api, "upload_tripulante_file", fake_upload)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/tripulantes/7/files",
        data={
            "arquivo_pdf": (BytesIO(b"%PDF-1.4\n%%EOF"), "multipart.pdf"),
            "tipo_documento": "geral",
        },
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["code"] == "tripulante_file_created"
    assert payload["upload"] == {
        "source": "multipart",
        "filename": "multipart.pdf",
        "original_filename": "multipart.pdf",
        "filename_source": "upload",
        "filename_was_fallback": False,
        "content_type": "application/pdf",
        "content_type_source": "upload",
        "encoding": "binary",
    }
    assert payload["file"]["id"] == 94
    assert captured_payload["arquivo_bytes"].startswith(b"%PDF")


def test_api_tripulante_files_upload_preserves_multipart_mime(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)
    captured_payload = {}

    def fake_upload(payload, tripulante_id, enviado_por):
        captured_payload.update(payload)
        return {
            "id": 96,
            "tripulante_id": tripulante_id,
            "tipo_documento": "geral",
            "nome_original": "mime.pdf",
            "nome_interno": "mime_interno.pdf",
            "mime_type": "application/pdf",
            "tamanho_bytes": 17,
            "storage_ref": "fs:tripulantes/7/documentos/mime.pdf",
            "arquivo_hash": "mime",
            "status": "ativo",
            "enviado_por": enviado_por,
            "enviado_em": None,
            "substitui_arquivo_id": None,
            "removido_por": None,
            "removido_em": None,
            "motivo_status": "",
        }

    monkeypatch.setattr(tripulante_media_api, "upload_tripulante_file", fake_upload)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/tripulantes/7/files",
        data={
            "arquivo_pdf": (BytesIO(b"%PDF-1.4\n%%EOF"), "mime.pdf", "application/octet-stream"),
            "tipo_documento": "geral",
        },
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 201
    assert captured_payload["content_type"] == "application/octet-stream"
    assert response.get_json()["upload"]["content_type"] == "application/octet-stream"


def test_api_tripulante_files_upload_accepts_replace_target_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)
    captured_payload = {}

    def fake_upload(payload, tripulante_id, enviado_por):
        captured_payload.update(payload)
        return {
            "id": 93,
            "tripulante_id": tripulante_id,
            "tipo_documento": "cma",
            "nome_original": "novo.pdf",
            "nome_interno": "novo_interno.pdf",
            "mime_type": "application/pdf",
            "tamanho_bytes": 456,
            "storage_ref": "fs:tripulantes/7/documentos/novo.pdf",
            "arquivo_hash": "def",
            "status": "ativo",
            "enviado_por": enviado_por,
            "enviado_em": None,
            "substitui_arquivo_id": 91,
            "removido_por": None,
            "removido_em": None,
            "motivo_status": "",
        }

    monkeypatch.setattr(tripulante_media_api, "upload_tripulante_file", fake_upload)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/tripulantes/7/files",
        json={
            "filename": "novo.pdf",
            "arquivo_base64": "JVBERi0xLjQKZW5kb2JqCiUlRU9G",
            "tipo_documento": "cma",
            "substitui_arquivo_id": 91,
        },
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["code"] == "tripulante_file_created"
    assert payload["file"]["substitui_arquivo_id"] == 91
    assert captured_payload["substitui_arquivo_id"] == 91


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
    assert response.headers["Content-Disposition"] == "inline; filename=arquivo.pdf"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-File-Access-Action"] == "preview"
    assert response.headers["X-File-Link-Policy"] == "authenticated-session"
    assert response.headers["X-File-Link-Expires"] == "session"
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in response.headers["Content-Security-Policy"]

    download_response = client.get("/api/v1/tripulantes/7/files/99?download=1")

    assert download_response.status_code == 200
    assert download_response.headers["Content-Disposition"] == "attachment; filename=arquivo.pdf"
    assert download_response.headers["X-File-Access-Action"] == "download"
    assert download_response.headers["X-Frame-Options"] == "SAMEORIGIN"


def test_api_tripulante_file_get_missing_returns_json_error_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    def _raise_missing(tripulante_id, arquivo_id):
        raise tripulante_media_api.TripulanteFileNotFoundError("Documento nao encontrado.")

    monkeypatch.setattr(tripulante_media_api, "get_tripulante_file", _raise_missing)

    response = client.get("/api/v1/tripulantes/7/files/99")

    assert response.status_code == 404
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == 404
    assert payload["code"] == "tripulante_file_not_found"
    assert "request_id" in payload


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


def test_tripulante_photo_state_uses_servible_storage_not_metadata(monkeypatch):
    monkeypatch.setattr(
        "backend.src.controle_treinamentos.application.tripulante_media.read_media_bytes",
        lambda _ref, fallback_bytes=None: None,
    )

    state = resolve_tripulante_photo_state(
        {
            "foto_storage_ref": "fs:tripulantes/7/foto/quebrada.jpg",
            "foto_mime_type": "image/jpeg",
            "foto_base64": "",
            "possui_foto": True,
        }
    )

    assert state["has_photo"] is False
    assert state["source"] == "broken_reference"
    assert state["broken_reference"] is True
    assert state["compat_residual"] is False


def test_tripulante_photo_endpoint_can_serve_legacy_base64(monkeypatch):
    monkeypatch.setattr(
        "backend.src.controle_treinamentos.application.tripulante_media.fetch_tripulante_for_write",
        lambda _db, tripulante_id: {
            "id": tripulante_id,
            "nome": "Lucas Silva",
            "foto_storage_ref": "",
            "foto_mime_type": "",
            "foto_base64": "data:image/png;base64,aW1n",
            "possui_foto": True,
        },
    )
    monkeypatch.setattr("backend.src.controle_treinamentos.application.tripulante_media.get_db", lambda: object())

    payload = get_tripulante_photo(tripulante_id=7)

    assert payload["has_photo"] is True
    assert payload["mime_type"] == "image/png"
    assert payload["payload_bytes"] == b"img"
    assert payload["compat_residual"] is True
    assert payload["compat_source"] == "foto_base64"
