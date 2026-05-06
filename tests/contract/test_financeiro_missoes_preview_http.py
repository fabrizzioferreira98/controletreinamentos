from __future__ import annotations

import json

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.api.http.financeiro import routes as financeiro_routes
from backend.src.controle_treinamentos.application import financeiro_missoes as financeiro_missoes_app
from backend.src.controle_treinamentos.auth import FINANCE_PERMISSION_KEYS
from backend.src.controle_treinamentos.core.domain_errors import DomainValidationError


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


class _PreviewDB:
    def __init__(self):
        self.commits = []
        self.conn = self

    def commit(self):
        self.commits.append("commit")

    def rollback(self):
        raise AssertionError("preview_missao_operacional nao deve executar rollback em fluxo feliz")


def _auth_user_row(*, permissions, login: str = "finance_preview_http_user"):
    return {
        "id": 902,
        "nome": "Finance Preview HTTP User",
        "login": login,
        "email": f"{login}@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": json.dumps(sorted(permissions)),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch, *, permissions, login: str = "finance_preview_http_user") -> str:
    fake_db = _SingleUserDB(_auth_user_row(permissions=permissions, login=login))
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": login, "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert response.status_code == 200
    return client.get("/api/v1/session").get_json()["csrf_token"]


def _headers(csrf_token: str | None = None, *, request_id: str = "finance-preview-http") -> dict:
    headers = {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-Request-ID": request_id,
        "X-Correlation-ID": f"{request_id}-correlation",
    }
    if csrf_token:
        headers["X-CSRFToken"] = csrf_token
    return headers


def _assert_envelope(response, *, status: int, success: bool):
    assert response.status_code == status
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["success"] is success
    assert payload["status"] == status
    assert payload["code"]
    assert payload["message"]
    assert "request_id" in payload
    assert "correlation_id" in payload
    if status != 401:
        assert payload["request_id"]
        assert payload["correlation_id"]
    return payload


def _valid_preview_payload():
    return {
        "competencia": "2026-04",
        "data_missao": "2026-04-30",
        "cavok_numero_voo": "CAVOK-100",
        "aeronave_id": 77,
        "categoria_financeira_aeronave": "categoria a",
        "comandante_tripulante_id": 101,
        "copiloto_tripulante_id": 202,
        "horario_apresentacao": "2026-04-30T20:00",
        "horario_abandono": "2026-04-30T22:00",
        "status": "ativa",
    }


def _sample_preview(status: str = "disponivel"):
    return {
        "status": status,
        "estado_calculo": "estimado",
        "base_calculo": "Bonificacao horaria operacional",
        "campos_faltantes": [],
        "pendencias": [],
        "inconsistencias": [],
        "horas_consideradas": {"jornada_total_minutos": 120},
        "tripulantes_considerados": [
            {"tripulante_id": 101, "funcao": "comandante"},
            {"tripulante_id": 202, "funcao": "copiloto"},
        ],
        "valor_estimado": "360.00",
        "calculations": [],
        "observacoes": ["Estimativa operacional calculada sem persistencia."],
        "generated_at": "2026-05-04T14:00:00+00:00",
    }


def test_preview_endpoint_requires_authentication_and_permission(monkeypatch):
    app = create_app()
    anonymous = app.test_client()

    response = anonymous.post("/api/v1/financeiro/missoes/preview", json={}, headers=_headers())
    payload = _assert_envelope(response, status=401, success=False)
    assert payload["code"] == "auth_required"

    no_scope_client = app.test_client()
    csrf_token = _authenticate_client(
        no_scope_client,
        monkeypatch,
        permissions={"dashboard:view"},
        login="finance_preview_no_scope",
    )
    response = no_scope_client.post(
        "/api/v1/financeiro/missoes/preview",
        json={},
        headers=_headers(csrf_token, request_id="finance-preview-forbidden"),
    )
    payload = _assert_envelope(response, status=403, success=False)
    assert payload["code"] == "forbidden"


def test_preview_endpoint_delegates_to_non_persistent_use_case(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_preview_authorized",
    )
    calls = []

    def _preview(payload, **kwargs):
        calls.append((payload, kwargs))
        return _sample_preview()

    monkeypatch.setattr(financeiro_routes, "preview_missao_operacional", _preview)

    response = client.post(
        "/api/v1/financeiro/missoes/preview",
        json=_valid_preview_payload(),
        headers=_headers(csrf_token, request_id="finance-preview-ok"),
    )
    payload = _assert_envelope(response, status=200, success=True)

    assert payload["code"] == "finance_mission_preview_ok"
    assert payload["preview"]["status"] == "disponivel"
    assert payload["preview"]["valor_estimado"] == "360.00"
    assert calls == [(_valid_preview_payload(), {})]


def test_preview_endpoint_returns_pending_fields_without_recalculate(monkeypatch):
    app = create_app()
    client = app.test_client()
    csrf_token = _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_preview_pending",
    )
    mutation_calls = []

    monkeypatch.setattr(financeiro_routes, "recalcular_missao_operacional", lambda *args, **kwargs: mutation_calls.append("recalcular"))
    monkeypatch.setattr(financeiro_routes, "criar_missao_operacional", lambda *args, **kwargs: mutation_calls.append("criar"))

    response = client.post(
        "/api/v1/financeiro/missoes/preview",
        json={"competencia": "2026-04"},
        headers=_headers(csrf_token, request_id="finance-preview-pending"),
    )
    payload = _assert_envelope(response, status=200, success=True)

    assert payload["preview"]["status"] == "pendente_dados"
    assert {item["field"] for item in payload["preview"]["campos_faltantes"]} >= {
        "data_missao",
        "aeronave_id",
        "categoria_financeira_aeronave",
    }
    assert mutation_calls == []


def test_preview_use_case_does_not_persist_or_call_recalculation_repositories(monkeypatch):
    db = _PreviewDB()
    write_calls = []

    monkeypatch.setattr(financeiro_missoes_app, "create_missao_operacional_with_tripulantes", lambda *args, **kwargs: write_calls.append("create"))
    monkeypatch.setattr(financeiro_missoes_app, "substituir_calculos_da_missao", lambda *args, **kwargs: write_calls.append("substituir"))
    monkeypatch.setattr(financeiro_missoes_app, "salvar_calculo_horario", lambda *args, **kwargs: write_calls.append("salvar"))
    monkeypatch.setattr(financeiro_missoes_app, "record_audit_event", lambda *args, **kwargs: write_calls.append("audit"))
    monkeypatch.setattr(financeiro_missoes_app, "_is_feriado_nacional", lambda *args, **kwargs: False)
    monkeypatch.setattr(financeiro_missoes_app, "_buscar_parametros_vigentes", lambda *args, **kwargs: [{"id": 1}])
    monkeypatch.setattr(
        financeiro_missoes_app,
        "calcular_bonificacao_horaria",
        lambda **kwargs: {
            "tripulante_id": kwargs["participante"]["tripulante_id"],
            "funcao": kwargs["participante"]["funcao"],
            "jornada_total_minutos": 120,
            "minutos_diurnos": 60,
            "minutos_noturnos_reais": 60,
            "total": "180.00",
            "memoria_calculo": {"steps": []},
            "parametros_usados": [],
            "calculation_version": "finance-hourly-v1",
        },
    )

    preview = financeiro_missoes_app.preview_missao_operacional(_valid_preview_payload(), db=db)

    assert preview["status"] == "disponivel"
    assert preview["valor_estimado"] == "360.00"
    assert write_calls == []
    assert db.commits == []


def test_preview_use_case_returns_blocked_state_for_backend_inconsistency(monkeypatch):
    db = _PreviewDB()

    monkeypatch.setattr(financeiro_missoes_app, "_is_feriado_nacional", lambda *args, **kwargs: False)
    monkeypatch.setattr(financeiro_missoes_app, "_buscar_parametros_vigentes", lambda *args, **kwargs: [])

    def _blocked_calculation(**_kwargs):
        raise DomainValidationError(
            "Parametro financeiro obrigatorio ausente.",
            code="bonificacao_horaria_parametro_ausente",
        )

    monkeypatch.setattr(financeiro_missoes_app, "calcular_bonificacao_horaria", _blocked_calculation)

    preview = financeiro_missoes_app.preview_missao_operacional(_valid_preview_payload(), db=db)

    assert preview["status"] == "bloqueada"
    assert preview["estado_calculo"] == "bloqueado"
    assert preview["inconsistencias"][0]["code"] == "bonificacao_horaria_parametro_ausente"
    assert db.commits == []
