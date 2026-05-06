from __future__ import annotations

from datetime import date, datetime

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


def _sample_program_treinamento(*, treinamento_id: int = 55):
    return {
        **_sample_treinamento(treinamento_id=treinamento_id),
        "segmento_teorico_id": 26,
        "aeronave_modelo": "King Air B200/200/C90A/C90GT",
        "ctac_solo_horas": None,
        "ctac_voo_pic_sic_horas": None,
        "ctac_voo_crew_horas": None,
    }


def test_api_treinamentos_list_returns_collection_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    captured = {}

    def fake_list_treinamentos_read_model(**kwargs):
        captured.update(kwargs)
        return {
            "items": [_sample_treinamento()],
            "page": 1,
            "per_page": 20,
            "total": 1,
            "resumo": {"total": 1, "vencido": 0, "a_vencer": 0, "regular": 1, "sem_informacao": 0},
        }

    monkeypatch.setattr(
        treinamentos_api,
        "list_treinamentos_read_model",
        fake_list_treinamentos_read_model,
    )

    response = client.get("/api/v1/treinamentos?status=regular")

    assert response.status_code == 200
    payload = response.get_json()
    assert captured["filters"]["status"] == "regular"
    assert captured["page"] == 1
    assert captured["per_page"] == 20
    assert payload["success"] is True
    assert payload["code"] == "treinamentos_list_ok"
    assert payload["items"][0]["id"] == 55
    assert payload["items"][0]["origem_registro"] == "treinamento_geral"
    assert payload["items"][0]["modo_estrutura"] == "simples"
    assert isinstance(payload["items"][0]["id"], int)
    assert payload["items"][0]["data_realizacao"] == "2026-04-01"
    assert payload["items"][0]["data_vencimento"] == "2026-10-01"
    assert payload["summary"]["regular"] == 1


def test_api_treinamentos_options_returns_form_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    captured = {}

    def fake_get_treinamentos_options_read_model(**kwargs):
        captured.update(kwargs)
        return {
            "tripulantes": [{"id": 7, "nome": "Lucas Silva"}],
            "equipamentos": [{"id": 3, "nome": "AS350"}],
            "tipos": [{"id": 2, "nome": "CQ IFR", "periodicidade_meses": 6, "exige_equipamento": True}],
            "attachments": [],
        }

    monkeypatch.setattr(
        treinamentos_api,
        "get_treinamentos_options_read_model",
        fake_get_treinamentos_options_read_model,
    )

    response = client.get("/api/v1/treinamentos/options")

    assert response.status_code == 200
    payload = response.get_json()
    assert captured["treinamento_id"] is None
    assert captured["selected_equipment_id"] is None
    assert captured["selected_tipo_id"] is None
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

    captured = {}

    def fake_get_treinamento_detail_read_model(**kwargs):
        captured.update(kwargs)
        return _sample_treinamento(), [_sample_attachment()]

    monkeypatch.setattr(
        treinamentos_api,
        "get_treinamento_detail_read_model",
        fake_get_treinamento_detail_read_model,
    )

    response = client.get("/api/v1/treinamentos/55")

    assert response.status_code == 200
    payload = response.get_json()
    assert captured["treinamento_id"] == 55
    assert payload["success"] is True
    assert payload["treinamento"]["origem_registro"] == "treinamento_geral"
    assert payload["treinamento"]["modo_estrutura"] == "simples"
    assert payload["treinamento"]["attachments"][0]["id"] == 77
    assert isinstance(payload["treinamento"]["attachments"][0]["id"], int)
    assert payload["treinamento"]["attachments"][0]["enviado_em"] is None
    assert payload["treinamento"]["attachments"][0]["document_policy"]["kind"] == "pdf_evidence"
    assert payload["treinamento"]["attachments"][0]["document_policy"]["versioning"] == "append_only_with_soft_delete"


def test_api_treinamento_get_normalizes_dates_ids_and_attachment_boundary(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        treinamentos_api,
        "get_treinamento_detail_read_model",
        lambda **_kwargs: (
            {
                **_sample_treinamento(treinamento_id=55),
                "id": "55",
                "tripulante_id": "7",
                "tipo_treinamento_id": "2",
                "data_realizacao": date(2026, 4, 1),
                "data_vencimento": date(2026, 10, 1),
            },
            [
                {
                    "id": "77",
                    "treinamento_id": "55",
                    "nome_original": "anexo.pdf",
                    "nome_interno": "anexo-interno.pdf",
                    "mime_type": "",
                    "tamanho_bytes": "123",
                    "storage_ref": "legacy:database",
                    "blob_storage": "database",
                    "blob_available": 1,
                    "blob_status": "legacy_database",
                    "compat_residual": 1,
                    "compat_source": "arquivo_pdf_blob",
                    "arquivo_hash": "abc",
                    "status": "ativo",
                    "enviado_por": "41",
                    "enviado_em": datetime(2026, 4, 2, 10, 30),
                    "removido_por": "",
                    "removido_em": None,
                    "motivo_status": None,
                    "enviado_por_nome": "Operador Treinamentos",
                    "payload_bytes": b"%PDF",
                    "screen_badge": "transient",
                }
            ],
        ),
    )

    response = client.get("/api/v1/treinamentos/55")

    assert response.status_code == 200
    payload = response.get_json()
    treinamento = payload["treinamento"]
    assert treinamento["id"] == 55
    assert treinamento["tripulante_id"] == 7
    assert treinamento["tipo_treinamento_id"] == 2
    assert treinamento["data_realizacao"] == "2026-04-01"
    assert treinamento["data_vencimento"] == "2026-10-01"
    attachment = treinamento["attachments"][0]
    assert set(attachment) == {
        "id",
        "treinamento_id",
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
        "enviado_por",
        "enviado_em",
        "removido_por",
        "removido_em",
        "motivo_status",
        "enviado_por_nome",
        "links",
        "access_policy",
        "document_policy",
    }
    assert attachment["id"] == 77
    assert attachment["treinamento_id"] == 55
    assert attachment["mime_type"] == "application/pdf"
    assert attachment["tamanho_bytes"] == 123
    assert attachment["blob_available"] is True
    assert attachment["compat_residual"] is True
    assert attachment["compat_source"] == "arquivo_pdf_blob"
    assert attachment["blob_policy"]["canonical_owner"] == "treinamento_anexos_pdf.storage_ref"
    assert attachment["blob_policy"]["legacy_write"] == "blocked_new_writes"
    assert attachment["blob_policy"]["legacy_read"] == "isolated_fallback"
    assert attachment["enviado_por"] == 41
    assert attachment["enviado_em"] == "2026-04-02T10:30:00"
    assert attachment["removido_por"] is None
    assert attachment["removido_em"] is None
    assert attachment["links"]["download"] == "/api/v1/treinamentos/55/attachments/77?download=1"
    assert attachment["access_policy"]["preview_permission"] == "treinamentos_anexos:view"
    assert attachment["document_policy"]["versioning"] == "append_only_with_soft_delete"


def test_api_treinamento_get_exposes_program_snapshot_when_record_comes_from_program(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        treinamentos_api,
        "get_treinamento_detail_read_model",
        lambda **_kwargs: (_sample_program_treinamento(), []),
    )

    response = client.get("/api/v1/treinamentos/55")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["treinamento"]["origem_registro"] == "programa_tripulante"
    assert payload["treinamento"]["modo_estrutura"] == "programa_segmentado"
    assert payload["treinamento"]["segmento_teorico_id"] == 26
    assert payload["treinamento"]["aeronave_modelo_snapshot"] == "King Air B200/200/C90A/C90GT"
    assert payload["treinamento"]["aeronave_modelo_role"] == "snapshot_realizado"


def test_api_treinamento_attachments_upload_returns_created_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)
    captured_payload = {}

    def fake_upload(payload, treinamento_id, enviado_por):
        captured_payload.update(payload)
        return _sample_attachment(treinamento_id=treinamento_id, attachment_id=88)

    monkeypatch.setattr(treinamentos_api, "upload_treinamento_attachment", fake_upload)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/treinamentos/55/attachments",
        json={"filename": "anexo.pdf", "content_base64": "JVBERi0xLjQKZW5kb2JqCiUlRU9G"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "treinamento_attachment_created"
    assert payload["upload"] == {
        "source": "json",
        "filename": "anexo.pdf",
        "original_filename": "anexo.pdf",
        "filename_source": "upload",
        "filename_was_fallback": False,
        "content_type": "application/pdf",
        "content_type_source": "fallback",
        "encoding": "base64",
    }
    assert payload["attachment"]["id"] == 88
    assert payload["attachment"]["document_policy"]["kind"] == "pdf_evidence"
    assert captured_payload["content_base64"] == "JVBERi0xLjQKZW5kb2JqCiUlRU9G"
    assert captured_payload["arquivo_base64"] == "JVBERi0xLjQKZW5kb2JqCiUlRU9G"


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
    assert response.headers["Content-Disposition"] == "inline; filename=anexo.pdf"
    assert response.headers["Cache-Control"] == "private, no-store"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-File-Access-Action"] == "preview"
    assert response.headers["X-File-Link-Policy"] == "authenticated-session"
    assert response.headers["X-File-Link-Expires"] == "session"

    download_response = client.get("/api/v1/treinamentos/55/attachments/77?download=1")

    assert download_response.status_code == 200
    assert download_response.headers["Content-Disposition"] == "attachment; filename=anexo.pdf"
    assert download_response.headers["X-File-Access-Action"] == "download"


def test_api_treinamento_attachment_get_missing_returns_json_error_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    def _raise_missing(treinamento_id, anexo_id):
        raise treinamentos_api.TreinamentoAttachmentNotFoundError("Anexo nao encontrado.")

    monkeypatch.setattr(treinamentos_api, "get_treinamento_attachment", _raise_missing)

    response = client.get("/api/v1/treinamentos/55/attachments/77")

    assert response.status_code == 404
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == 404
    assert payload["code"] == "treinamento_attachment_not_found"
    assert "request_id" in payload


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
