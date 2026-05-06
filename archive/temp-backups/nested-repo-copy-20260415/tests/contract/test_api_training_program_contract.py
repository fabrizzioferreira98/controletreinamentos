from __future__ import annotations

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


def _auth_user_row():
    return {
        "id": 41,
        "nome": "Operador Treinamentos",
        "login": "training_program_api",
        "email": "training.program@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": (
            '["tipos_treinamento:view","tipos_treinamento:create","tipos_treinamento:edit","tipos_treinamento:delete",'
            '"treinamentos:view","treinamentos:create","treinamentos:edit","treinamentos:delete"]'
        ),
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
        "data_realizacao": "2026-04-01",
        "data_vencimento": "2027-04-01",
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


def test_training_master_options_returns_contract(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(training_program_api, "get_db", lambda: object())
    monkeypatch.setattr(training_program_api, "fetch_training_master_types", lambda _db: [_sample_type()])
    monkeypatch.setattr(
        training_program_api,
        "fetch_training_program_aircraft_models",
        lambda _db: [{"aeronave_modelo": "King Air B200/200/C90A/C90GT", "total_registros": 3}],
    )

    response = client.get("/api/v1/treinamento-raiz/options")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["options"]["tipos_treinamento"][0]["codigo"] == "T4"
    assert payload["options"]["modelos_aeronave"][0]["aeronave_modelo"] == "King Air B200/200/C90A/C90GT"


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
    assert len(payload["template"]["segmentos"]) == 2
    assert "Gerais" in payload["template"]["segmentos_por_modelo"]


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


def test_training_program_record_detail_returns_attachments(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(client, monkeypatch)

    monkeypatch.setattr(training_program_api, "get_db", lambda: object())
    monkeypatch.setattr(training_program_api, "fetch_training_program_record_detail", lambda _db, treinamento_id: _sample_record(treinamento_id))
    monkeypatch.setattr(
        training_program_api,
        "fetch_treinamento_attachments",
        lambda _db, treinamento_id: [
            {
                "id": 5,
                "treinamento_id": treinamento_id,
                "nome_original": "anexo.pdf",
                "nome_interno": "anexo.pdf",
                "mime_type": "application/pdf",
                "tamanho_bytes": 123,
                "storage_ref": "fs:tripulantes/7/treinamentos/88/anexo.pdf",
                "arquivo_hash": "abc",
                "status": "ativo",
                "enviado_por": 41,
                "enviado_em": None,
                "enviado_por_nome": "Operador Treinamentos",
            }
        ],
    )

    response = client.get("/api/v1/treinamentos-tripulantes/88")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["item"]["id"] == 88
    assert payload["item"]["attachments"][0]["id"] == 5
