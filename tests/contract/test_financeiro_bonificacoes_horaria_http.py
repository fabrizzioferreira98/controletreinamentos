from __future__ import annotations

import json

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.api.http.financeiro import routes as financeiro_routes
from backend.src.controle_treinamentos.application.financeiro_bonificacoes import BonificacaoHorariaNaoEncontradaErro
from backend.src.controle_treinamentos.auth import FINANCE_PERMISSION_KEYS
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT


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


def _auth_user_row(*, permissions, login: str = "finance_bonus_http_user"):
    return {
        "id": 801,
        "nome": "Finance Bonus HTTP User",
        "login": login,
        "email": f"{login}@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": json.dumps(sorted(permissions)),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _authenticate_client(client, monkeypatch, *, permissions, login: str = "finance_bonus_http_user") -> str:
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


def _headers(*, request_id: str = "finance-hourly-http") -> dict:
    return {
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "X-Request-ID": request_id,
        "X-Correlation-ID": f"{request_id}-correlation",
    }


def _assert_envelope(response, *, status: int, success: bool):
    assert response.status_code == status
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["success"] is success
    assert payload["status"] == status
    assert payload["code"]
    assert payload["message"]
    assert payload["request_id"]
    assert payload["correlation_id"]
    return payload


def _calculation_response(**overrides):
    payload = {
        "id": 10,
        "org_id": FINANCE_ORG_SCOPE_DEFAULT,
        "competencia": "2026-04",
        "mission_id": 22,
        "missao": {"id": 22, "cavok_numero_voo": "CAVOK-100", "contratante": "Cliente"},
        "tripulante_id": 101,
        "tripulante": {"id": 101, "nome": "Comandante Um"},
        "funcao": "comandante",
        "jornada_total_minutos": 300,
        "minutos_noturnos_reais": 105,
        "horas_noturnas_convertidas": "2.0000",
        "domingo_feriado": False,
        "total": "120.00",
        "status": "calculado",
        "memoria_calculo": {
            "steps": [
                {
                    "rule_key": "conversao_hora_noturna",
                    "formula_conceitual": "minutos_noturnos_reais / duracao_hora_noturna_minutos",
                }
            ]
        },
        "parametros_usados": [{"tipo": "duracao_hora_noturna_minutos", "valor": "52.5", "unidade": "minutos"}],
    }
    payload.update(overrides)
    return payload


def test_hourly_bonus_endpoints_require_authentication_and_permission(monkeypatch):
    app = create_app()
    anonymous = app.test_client()

    response = anonymous.get("/api/v1/financeiro/bonificacoes/horaria", headers=_headers())
    payload = _assert_envelope(response, status=401, success=False)
    assert payload["code"] == "auth_required"

    no_scope_client = app.test_client()
    _authenticate_client(
        no_scope_client,
        monkeypatch,
        permissions={"dashboard:view"},
        login="finance_bonus_no_scope",
    )
    response = no_scope_client.get(
        "/api/v1/financeiro/bonificacoes/horaria/10",
        headers=_headers(request_id="finance-hourly-forbidden"),
    )
    payload = _assert_envelope(response, status=403, success=False)
    assert payload["code"] == "forbidden"


def test_hourly_bonus_http_endpoints_delegate_to_use_cases_and_return_envelope(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_bonus_authorized",
    )
    calls = []

    def _list_hourly(**kwargs):
        calls.append(("list", kwargs))
        return {
            "items": [_calculation_response()],
            "pagination": {"page": kwargs["page"], "offset": kwargs["offset"], "total": 1},
        }

    def _detail_hourly(calculation_id, **kwargs):
        calls.append(("detail", calculation_id, kwargs))
        return _calculation_response(id=calculation_id)

    monkeypatch.setattr(financeiro_routes, "listar_bonificacoes_horarias", _list_hourly)
    monkeypatch.setattr(financeiro_routes, "detalhar_bonificacao_horaria", _detail_hourly)

    list_response = client.get(
        "/api/v1/financeiro/bonificacoes/horaria?competencia=2026-04&tripulante_id=101&funcao=comandante&status=calculado",
        headers=_headers(request_id="finance-hourly-list"),
    )
    list_payload = _assert_envelope(list_response, status=200, success=True)
    assert list_payload["items"][0]["minutos_noturnos_reais"] == 105
    assert list_payload["items"][0]["horas_noturnas_convertidas"] == "2.0000"
    assert list_payload["items"][0]["total"] == "120.00"

    detail_response = client.get(
        "/api/v1/financeiro/bonificacoes/horaria/10",
        headers=_headers(request_id="finance-hourly-detail"),
    )
    detail_payload = _assert_envelope(detail_response, status=200, success=True)
    assert detail_payload["calculation"]["memoria_calculo"]["steps"][0]["rule_key"] == "conversao_hora_noturna"
    assert detail_payload["calculation"]["parametros_usados"][0]["valor"] == "52.5"

    assert calls[0][0] == "list"
    assert calls[0][1]["competencia"] == "2026-04"
    assert calls[0][1]["tripulante_id"] == 101
    assert calls[0][1]["funcao"] == "comandante"
    assert calls[1][0] == "detail"
    assert calls[1][1] == 10


def test_hourly_bonus_detail_translates_not_found(monkeypatch):
    app = create_app()
    client = app.test_client()
    _authenticate_client(
        client,
        monkeypatch,
        permissions=set(FINANCE_PERMISSION_KEYS),
        login="finance_bonus_not_found",
    )

    def _not_found(_calculation_id):
        raise BonificacaoHorariaNaoEncontradaErro()

    monkeypatch.setattr(financeiro_routes, "detalhar_bonificacao_horaria", _not_found)

    response = client.get(
        "/api/v1/financeiro/bonificacoes/horaria/404",
        headers=_headers(request_id="finance-hourly-not-found"),
    )
    payload = _assert_envelope(response, status=404, success=False)
    assert payload["code"] == "bonificacao_horaria_nao_encontrada"
