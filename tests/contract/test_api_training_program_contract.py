from __future__ import annotations

import json
from datetime import date

import pytest
from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.api.http.cadastros import routes_training_program as training_program_api


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


def _auth_user_row(extra_permissions=()):
    permissions = [
        "tipos_treinamento:view",
        "tipos_treinamento:create",
        "tipos_treinamento:edit",
        "tipos_treinamento:delete",
        "treinamentos:view",
        "treinamentos:create",
        "treinamentos:edit",
        "treinamentos:delete",
        *extra_permissions,
    ]
    return {
        "id": 41,
        "nome": "Operador Treinamentos",
        "login": "training_program_api",
        "email": "training.program@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": json.dumps(permissions),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch, *, extra_permissions=()):
    row = _auth_user_row(extra_permissions=extra_permissions)
    fake_db = _SingleUserDB(row)
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)
    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "training_program_api", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 200


def _sample_type():
    return {
        "id": 4,
        "nome": "Treinamento Periodico",
        "codigo": "T4",
        "descricao": "",
        "periodicidade_meses": 24,
        "exige_equipamento": 1,
        "ativo": 1,
        "total_segmentos": 17,
        "total_horas_voo": 5,
    }


def _sample_template():
    return {
        "tipo": _sample_type(),
        "aeronave_modelo": "King Air B200/200/C90A/C90GT",
        "ctac_required": False,
        "horas_voo": {
            "id": 6,
            "aeronave_modelo": "King Air B200/200/C90A/C90GT",
            "solo_horas": 8.0,
            "voo_pic_sic_horas": 3.0,
            "voo_crew_horas": 0.0,
            "observacao": "",
        },
        "segmentos": [
            {
                "id": 26,
                "tipo_treinamento_id": 4,
                "modelo_segmento": "Gerais",
                "nome_segmento": "Operacoes Autorizadas",
                "carga_horaria": 0.5,
                "carga_teorica": 0.5,
                "carga_pratica": 0.0,
                "periodicidade_meses": 12,
                "observacao": "",
            },
            {
                "id": 29,
                "tipo_treinamento_id": 4,
                "modelo_segmento": "Especificos",
                "nome_segmento": "Artigos Perigosos",
                "carga_horaria": 4.0,
                "carga_teorica": 4.0,
                "carga_pratica": 0.0,
                "periodicidade_meses": 24,
                "observacao": "",
            },
        ],
    }


def _sample_segment():
    return {
        "id": 26,
        "tipo_treinamento_id": 4,
        "tipo_treinamento_nome": "Treinamento Periodico",
        "tipo_treinamento_codigo": "T4",
        "referencia_original_id": None,
        "modelo_segmento": "Gerais",
        "nome_segmento": "Operacoes Autorizadas",
        "carga_horaria": 0.5,
        "carga_teorica": 0.5,
        "carga_pratica": 0.0,
        "periodicidade_meses": 12,
        "observacao": "",
        "ativo": 1,
    }


def _sample_hour():
    return {
        "id": 6,
        "tipo_treinamento_id": 4,
        "tipo_treinamento_nome": "Treinamento Periodico",
        "tipo_treinamento_codigo": "T4",
        "referencia_original_id": None,
        "aeronave_modelo": "King Air B200/200/C90A/C90GT",
        "solo_horas": 8.0,
        "voo_pic_sic_horas": 3.0,
        "voo_crew_horas": 0.0,
        "observacao": "Conforme CTAC",
        "ativo": 1,
    }


def _sample_record(record_id: int = 88):
    return {
        "id": record_id,
        "tripulante_id": 7,
        "tripulante_nome": "Lucas Silva",
        "tripulante_matricula": "123456",
        "tipo_treinamento_id": 4,
        "tipo_treinamento_nome": "Treinamento Periodico",
        "tipo_treinamento_codigo": "T4",
        "segmento_teorico_id": 26,
        "nome_segmento": "Operacoes Autorizadas",
        "modelo_segmento": "Gerais",
        "aeronave_modelo": "King Air B200/200/C90A/C90GT",
        "data_realizacao": date(2026, 4, 1),
        "data_vencimento": date(2027, 4, 1),
        "observacao": "",
        "periodicidade_meses": 12,
        "status_calculado": "regular",
        "ctac_required": False,
        "total_anexos": 1,
        "carga_horaria": 0.5,
        "carga_teorica": 0.5,
        "carga_pratica": 0.0,
        "solo_horas_referencia": 8.0,
        "voo_pic_sic_horas_referencia": 3.0,
        "voo_crew_horas_referencia": 0.0,
        "horas_voo_observacao": "",
    }


def _sample_attachment(*, treinamento_id: int = 88, attachment_id: int = 5):
    return {
        "id": attachment_id,
        "treinamento_id": treinamento_id,
        "nome_original": "anexo.pdf",
        "nome_interno": "anexo.pdf",
        "mime_type": "application/pdf",
        "tamanho_bytes": 123,
        "storage_ref": f"fs:tripulantes/7/treinamentos/{treinamento_id}/anexo.pdf",
        "arquivo_hash": "abc",
        "status": "ativo",
        "enviado_por": 41,
        "enviado_em": None,
        "enviado_por_nome": "Operador Treinamentos",
    }


def test_training_master_options_returns_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        training_program_api,
        "get_training_master_options_read_model",
        lambda: {
            "tipos": [_sample_type()],
            "modelos_aeronave": [{"aeronave_modelo": "King Air B200/200/C90A/C90GT", "total_registros": 3}],
        },
    )

    response = client.get("/api/v1/treinamento-raiz/options")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["options"]["tipos_treinamento"][0]["codigo"] == "T4"
    assert payload["options"]["modelos_aeronave"][0]["aeronave_modelo"] == "King Air B200/200/C90A/C90GT"


@pytest.mark.parametrize(
    ("path", "entity", "sample", "code", "field", "value"),
    [
        ("/api/v1/treinamento-raiz/tipos", "types", _sample_type(), "training_master_types_ok", "codigo", "T4"),
        (
            "/api/v1/treinamento-raiz/segmentos?tipo_treinamento_id=4",
            "segments",
            _sample_segment(),
            "training_master_segments_ok",
            "nome_segmento",
            "Operacoes Autorizadas",
        ),
        (
            "/api/v1/treinamento-raiz/horas-voo?tipo_treinamento_id=4",
            "hours",
            _sample_hour(),
            "training_master_hours_ok",
            "aeronave_modelo",
            "King Air B200/200/C90A/C90GT",
        ),
    ],
)
def test_training_master_entities_list_returns_contract(
    monkeypatch,
    path,
    entity,
    sample,
    code,
    field,
    value,
):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)
    captured = {}

    def fake_list_entities(**kwargs):
        captured.update(kwargs)
        return [sample]

    monkeypatch.setattr(training_program_api, "list_training_master_entities_read_model", fake_list_entities)

    response = client.get(path)

    assert response.status_code == 200
    payload = response.get_json()
    assert captured["entity"] == entity
    if entity != "types":
        assert captured["tipo_treinamento_id"] == 4
    assert payload["code"] == code
    assert payload["items"][0][field] == value


@pytest.mark.parametrize(
    ("path", "entity", "entity_id", "sample", "code"),
    [
        (
            "/api/v1/treinamento-raiz/tipos/4",
            "types",
            4,
            _sample_type(),
            "training_master_type_detail_ok",
        ),
        (
            "/api/v1/treinamento-raiz/segmentos/26",
            "segments",
            26,
            _sample_segment(),
            "training_master_segment_detail_ok",
        ),
        (
            "/api/v1/treinamento-raiz/horas-voo/6",
            "hours",
            6,
            _sample_hour(),
            "training_master_hour_detail_ok",
        ),
    ],
)
def test_training_master_entity_detail_returns_contract(monkeypatch, path, entity, entity_id, sample, code):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)
    captured = {}

    def fake_entity_detail(**kwargs):
        captured.update(kwargs)
        return sample

    monkeypatch.setattr(training_program_api, "get_training_master_entity_detail_read_model", fake_entity_detail)

    response = client.get(path)

    assert response.status_code == 200
    payload = response.get_json()
    assert captured == {"entity": entity, "entity_id": entity_id}
    assert payload["code"] == code
    assert payload["item"]["id"] == entity_id


def test_training_master_type_create_returns_created_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        training_program_api,
        "save_training_master_type",
        lambda payload, tipo_treinamento_id=None: {"operation": "created", "tipo": _sample_type()},
    )

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/treinamento-raiz/tipos",
        json={"nome": "Treinamento Periodico", "codigo": "T4", "status": "Ativo", "exige_aeronave": "Sim"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["code"] == "training_master_type_created"
    assert payload["item"]["id"] == 4


def test_training_program_template_returns_grouped_segments(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(training_program_api, "build_training_program_template", lambda **_kwargs: _sample_template())

    response = client.get(
        "/api/v1/treinamentos-tripulantes/template?tipo_treinamento_id=4&aeronave_modelo=King%20Air%20B200/200/C90A/C90GT"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["template"]["tipo"]["id"] == 4
    assert payload["template"]["modo_estrutura"] == "programa_segmentado"
    assert payload["template"]["aeronave_modelo_referencia"] == "King Air B200/200/C90A/C90GT"
    assert payload["template"]["aeronave_modelo_role"] == "referencia_programa"
    assert len(payload["template"]["segmentos"]) == 2
    assert "Gerais" in payload["template"]["segmentos_por_modelo"]


def test_training_program_template_accepts_explicit_reference_query_name(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)
    captured = {}

    def fake_template(**kwargs):
        captured.update(kwargs)
        return _sample_template()

    monkeypatch.setattr(training_program_api, "build_training_program_template", fake_template)

    response = client.get(
        "/api/v1/treinamentos-tripulantes/template?tipo_treinamento_id=4"
        "&aeronave_modelo_referencia=King%20Air%20B200/200/C90A/C90GT"
    )

    assert response.status_code == 200
    assert captured["aeronave_modelo_referencia"] == "King Air B200/200/C90A/C90GT"


def test_training_program_options_accepts_optional_base_filter(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)
    captured = {}

    def fake_options(*, base=None):
        captured["base"] = base
        return {
            "tripulantes": [{"id": 7, "nome": "Lucas Silva", "matricula": "123456"}],
            "tipos": [_sample_type()],
            "modelos_aeronave": [{"aeronave_modelo": "King Air B200/200/C90A/C90GT", "total_registros": 3}],
        }

    monkeypatch.setattr(training_program_api, "get_tripulante_program_options_read_model", fake_options)

    response = client.get("/api/v1/treinamentos-tripulantes/options?base=SSA")

    assert response.status_code == 200
    payload = response.get_json()
    assert captured["base"] == "SSA"
    assert payload["code"] == "training_program_tripulantes_options_ok"
    assert payload["options"]["tripulantes"][0]["id"] == 7
    assert payload["options"]["tipos_treinamento"][0]["id"] == 4


def test_training_program_records_list_accepts_explicit_snapshot_query_name(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)
    captured = {}

    def fake_list_records(**kwargs):
        captured.update(kwargs)
        return [_sample_record()]

    monkeypatch.setattr(training_program_api, "list_tripulante_program_records_read_model", fake_list_records)

    response = client.get(
        "/api/v1/treinamentos-tripulantes"
        "?tipo_treinamento_id=4"
        "&aeronave_modelo_snapshot=King%20Air%20B200/200/C90A/C90GT"
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert captured["aeronave_modelo_snapshot"] == "King Air B200/200/C90A/C90GT"
    assert payload["items"][0]["modo_estrutura"] == "programa_segmentado"
    assert payload["items"][0]["aeronave_modelo_snapshot"] == "King Air B200/200/C90A/C90GT"
    assert payload["items"][0]["aeronave_modelo_role"] == "snapshot_realizado"


def test_training_program_records_list_accepts_optional_base_filter(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)
    captured = {}

    def fake_list_records(**kwargs):
        captured.update(kwargs)
        return [_sample_record()]

    monkeypatch.setattr(training_program_api, "list_tripulante_program_records_read_model", fake_list_records)

    response = client.get("/api/v1/treinamentos-tripulantes?base=SSA&tipo_treinamento_id=4")

    assert response.status_code == 200
    payload = response.get_json()
    assert captured["base"] == "SSA"
    assert captured["tipo_treinamento_id"] == 4
    assert payload["code"] == "training_program_records_ok"
    assert payload["items"][0]["tripulante_id"] == 7


def test_training_program_batch_create_returns_created_records(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(
        training_program_api,
        "create_tripulante_training_batch",
        lambda payload, criado_por: {
            "created_ids": [88, 89],
            "items": [_sample_record(88), {**_sample_record(89), "segmento_teorico_id": 29, "nome_segmento": "Artigos Perigosos"}],
            "template": _sample_template(),
        },
    )

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/treinamentos-tripulantes/batch",
        json={
            "tripulante_id": 7,
            "tipo_treinamento_id": 4,
            "aeronave_modelo": "King Air B200/200/C90A/C90GT",
            "segmentos": [
                {"segmento_id": 26, "data_realizacao": "2026-04-01"},
                {"segmento_id": 29, "data_realizacao": "2026-04-01"},
            ],
        },
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["code"] == "training_program_batch_created"
    assert payload["created_ids"] == [88, 89]
    assert payload["items"][0]["tripulante_id"] == 7
    assert payload["items"][0]["modo_estrutura"] == "programa_segmentado"
    assert payload["items"][0]["aeronave_modelo_snapshot"] == "King Air B200/200/C90A/C90GT"
    assert payload["items"][0]["aeronave_modelo_role"] == "snapshot_realizado"
    assert payload["template"]["modo_estrutura"] == "programa_segmentado"
    assert payload["template"]["aeronave_modelo_referencia"] == "King Air B200/200/C90A/C90GT"


def test_training_program_batch_with_evidence_requires_attachment_permission(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    def fail_batch(*_args, **_kwargs):
        raise AssertionError("batch service should not run without evidence upload permission")

    monkeypatch.setattr(training_program_api, "create_tripulante_training_batch", fail_batch)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/treinamentos-tripulantes/batch",
        json={
            "tripulante_id": 7,
            "tipo_treinamento_id": 4,
            "segmentos": [
                {
                    "segmento_id": 26,
                    "data_realizacao": "2026-04-01",
                    "arquivo_base64": "JVBERi0xLjQKZW5kb2JqCiUlRU9G",
                    "filename": "evidencia.pdf",
                }
            ],
        },
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 403
    payload = response.get_json()
    assert payload["code"] == "training_program_evidence_upload_forbidden"


def test_training_program_batch_with_evidence_allows_attachment_permission(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch, extra_permissions=("treinamentos_anexos:create",))
    captured_payload = {}

    def fake_batch(payload, criado_por):
        captured_payload.update(payload)
        return {
            "created_ids": [88],
            "items": [_sample_record(88)],
            "template": _sample_template(),
        }

    monkeypatch.setattr(training_program_api, "create_tripulante_training_batch", fake_batch)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/treinamentos-tripulantes/batch",
        json={
            "tripulante_id": 7,
            "tipo_treinamento_id": 4,
            "segmentos": [
                {
                    "segmento_id": 26,
                    "data_realizacao": "2026-04-01",
                    "arquivo_base64": "JVBERi0xLjQKZW5kb2JqCiUlRU9G",
                    "filename": "evidencia.pdf",
                }
            ],
        },
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 201
    assert captured_payload["segmentos"][0]["arquivo_base64"] == "JVBERi0xLjQKZW5kb2JqCiUlRU9G"
    assert response.get_json()["code"] == "training_program_batch_created"


def test_training_program_record_detail_returns_attachments(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    captured = {}

    def fake_detail(*, treinamento_id):
        captured["treinamento_id"] = treinamento_id
        return {
            "item": _sample_record(treinamento_id),
            "attachments": [_sample_attachment(treinamento_id=treinamento_id)],
        }

    monkeypatch.setattr(training_program_api, "get_tripulante_program_record_detail_read_model", fake_detail)

    response = client.get("/api/v1/treinamentos-tripulantes/88")

    assert response.status_code == 200
    payload = response.get_json()
    assert captured["treinamento_id"] == 88
    assert payload["item"]["id"] == 88
    assert payload["item"]["modo_estrutura"] == "programa_segmentado"
    assert payload["item"]["aeronave_modelo_snapshot"] == "King Air B200/200/C90A/C90GT"
    assert payload["item"]["aeronave_modelo_role"] == "snapshot_realizado"
    assert payload["item"]["links"]["attachments"] == "/api/v1/treinamentos-tripulantes/88/attachments"
    assert payload["item"]["attachments"][0]["id"] == 5
    assert payload["item"]["attachments"][0]["links"]["download"] == (
        "/api/v1/treinamentos-tripulantes/88/attachments/5?download=1"
    )


def test_training_program_attachment_list_uses_canonical_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch, extra_permissions=("treinamentos_anexos:view",))

    captured = {}

    def fake_list_attachments(**kwargs):
        captured.update(kwargs)
        return [_sample_attachment(treinamento_id=88)]

    monkeypatch.setattr(training_program_api, "list_treinamento_attachments", fake_list_attachments)

    response = client.get("/api/v1/treinamentos-tripulantes/88/attachments")

    assert response.status_code == 200
    payload = response.get_json()
    assert captured["treinamento_id"] == 88
    assert payload["code"] == "training_program_record_attachments_ok"
    assert payload["items"][0]["links"]["self"] == "/api/v1/treinamentos-tripulantes/88/attachments/5"


def test_training_program_attachment_upload_uses_canonical_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch, extra_permissions=("treinamentos_anexos:create",))
    captured_payload = {}

    def fake_upload(payload, treinamento_id, enviado_por):
        captured_payload.update(payload)
        assert treinamento_id == 88
        assert enviado_por == 41
        return _sample_attachment(treinamento_id=88, attachment_id=9)

    monkeypatch.setattr(training_program_api, "upload_treinamento_attachment", fake_upload)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/treinamentos-tripulantes/88/attachments",
        json={"filename": "evidencia.pdf", "content_base64": "JVBERi0xLjQKZW5kb2JqCiUlRU9G"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 201
    payload = response.get_json()
    assert payload["code"] == "training_program_record_attachment_created"
    assert payload["attachment"]["links"]["download"] == "/api/v1/treinamentos-tripulantes/88/attachments/9?download=1"
    assert captured_payload["content_base64"] == "JVBERi0xLjQKZW5kb2JqCiUlRU9G"
    assert captured_payload["arquivo_base64"] == "JVBERi0xLjQKZW5kb2JqCiUlRU9G"


def test_training_program_attachment_get_returns_binary_from_canonical_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch, extra_permissions=("treinamentos_anexos:view",))

    monkeypatch.setattr(
        training_program_api,
        "get_treinamento_attachment",
        lambda treinamento_id, anexo_id: {
            "nome_original": "anexo.pdf",
            "mime_type": "application/pdf",
            "payload_bytes": b"%PDF-1.4\n%%EOF",
        },
    )

    response = client.get("/api/v1/treinamentos-tripulantes/88/attachments/5")

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")
    assert response.headers["Content-Disposition"] == "inline; filename=anexo.pdf"
    assert response.headers["X-File-Access-Action"] == "preview"


def test_training_program_attachment_delete_uses_canonical_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch, extra_permissions=("treinamentos_anexos:delete",))

    monkeypatch.setattr(
        training_program_api,
        "delete_treinamento_attachment",
        lambda treinamento_id, anexo_id: _sample_attachment(treinamento_id=treinamento_id, attachment_id=anexo_id),
    )

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.delete(
        "/api/v1/treinamentos-tripulantes/88/attachments/5",
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["code"] == "training_program_record_attachment_deleted"
    assert payload["attachment"]["links"]["self"] == "/api/v1/treinamentos-tripulantes/88/attachments/5"
