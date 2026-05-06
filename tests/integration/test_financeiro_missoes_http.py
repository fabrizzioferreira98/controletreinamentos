from __future__ import annotations

import json
import os
import uuid

import pytest
from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.auth import FINANCE_PERMISSION_KEYS
from backend.src.controle_treinamentos.contracts.financeiro import FINANCE_ORG_SCOPE_DEFAULT

SKIP_REASON = "DATABASE_URL not set or not pointing to test DB"


def _has_test_db() -> bool:
    url = (os.getenv("DATABASE_URL", "") or "").strip()
    return bool(url) and "test" in url.lower()


pytestmark = pytest.mark.skipif(not _has_test_db(), reason=SKIP_REASON)


def _cpf() -> str:
    return str(uuid.uuid4().int % 100_000_000_000).zfill(11)


def _headers(csrf_token: str | None = None, *, request_id: str = "finance-http-test") -> dict:
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
    assert payload["request_id"]
    assert payload["correlation_id"]
    return payload


def _seed_user(db, *, permissions, login_prefix: str) -> dict:
    token = uuid.uuid4().hex[:10]
    login = f"{login_prefix}_{token}"
    user = db.execute(
        """
        INSERT INTO usuarios (nome, login, email, senha_hash, perfil, ativo, permissao_modulos_json)
        VALUES (%s, %s, %s, %s, 'operador', 1, %s)
        RETURNING id, login
        """,
        (
            f"Finance HTTP User {token}",
            login,
            f"{login}@local.test",
            generate_password_hash("secret", method="pbkdf2:sha256"),
            json.dumps(sorted(permissions)),
        ),
    ).fetchone()
    return {"id": user["id"], "login": user["login"], "password": "secret"}


def _seed_refs(db) -> dict:
    token = uuid.uuid4().hex[:10]
    comandante_id = db.execute(
        """
        INSERT INTO tripulantes (nome, cpf, licenca_anac, base, status)
        VALUES (%s, %s, %s, 'BSB', 'Ativo')
        RETURNING id
        """,
        (f"Comandante HTTP {token}", _cpf(), f"HA{token[:5]}"),
    ).fetchone()["id"]
    copiloto_id = db.execute(
        """
        INSERT INTO tripulantes (nome, cpf, licenca_anac, base, status)
        VALUES (%s, %s, %s, 'BSB', 'Ativo')
        RETURNING id
        """,
        (f"Copiloto HTTP {token}", _cpf(), f"HB{token[:5]}"),
    ).fetchone()["id"]
    aeronave_id = db.execute(
        """
        INSERT INTO equipamentos (nome, tipo, ativo)
        VALUES (%s, 'aeronave', 1)
        RETURNING id
        """,
        (f"Aeronave HTTP {token}",),
    ).fetchone()["id"]
    return {
        "comandante_id": comandante_id,
        "copiloto_id": copiloto_id,
        "aeronave_id": aeronave_id,
        "token": token,
    }


def _login(client, user: dict) -> str:
    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": user["login"], "senha": user["password"]},
        headers={"X-CSRFToken": csrf_token, "Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    return client.get("/api/v1/session").get_json()["csrf_token"]


@pytest.fixture()
def finance_http_context():
    from backend.src.controle_treinamentos.db import close_db, execute_schema_bootstrap, get_db

    app = create_app()
    with app.app_context():
        db = get_db()
        execute_schema_bootstrap(db)
        finance_user = _seed_user(db, permissions=set(FINANCE_PERMISSION_KEYS), login_prefix="finance_http")
        no_scope_user = _seed_user(db, permissions={"dashboard:view"}, login_prefix="finance_http_no_scope")
        refs = _seed_refs(db)
        db.commit()
        close_db()

    client = app.test_client()
    csrf_token = _login(client, finance_user)
    return {
        "app": app,
        "client": client,
        "csrf_token": csrf_token,
        "finance_user": finance_user,
        "no_scope_user": no_scope_user,
        "refs": refs,
    }


def _mission_payload(refs: dict, *, competencia: str = "2026-10") -> dict:
    token = uuid.uuid4().hex[:8]
    return {
        "competencia": competencia,
        "data_missao": f"{competencia}-10",
        "cavok_numero_voo": f"CAVOK-HTTP-{token}",
        "contratante": f"Cliente HTTP {token}",
        "chamado": f"HTTP-{token}",
        "aeronave_id": refs["aeronave_id"],
        "categoria_financeira_aeronave": "A",
        "comandante_tripulante_id": refs["comandante_id"],
        "copiloto_tripulante_id": refs["copiloto_id"],
        "horario_apresentacao": f"{competencia}-10 08:00:00",
        "horario_abandono": f"{competencia}-10 18:00:00",
        "trecho": "BSB-GRU",
        "houve_pernoite": False,
        "quantidade_pernoites": 0,
        "cobertura_base": False,
        "operacao_especial": "",
        "observacoes": "http integration",
    }


def _create_mission(context, *, competencia: str = "2026-10") -> dict:
    response = context["client"].post(
        "/api/v1/financeiro/missoes",
        json=_mission_payload(context["refs"], competencia=competencia),
        headers=_headers(context["csrf_token"], request_id=f"finance-create-{uuid.uuid4().hex[:6]}"),
    )
    payload = _assert_envelope(response, status=201, success=True)
    return payload["mission"]


def test_mission_endpoints_require_authentication_and_permission(finance_http_context):
    app = finance_http_context["app"]
    anonymous = app.test_client()

    response = anonymous.get("/api/v1/financeiro/missoes?competencia=2026-10", headers=_headers())
    payload = _assert_envelope(response, status=401, success=False)
    assert payload["code"] == "auth_required"

    no_scope_client = app.test_client()
    csrf_token = _login(no_scope_client, finance_http_context["no_scope_user"])
    response = no_scope_client.post(
        "/api/v1/financeiro/missoes",
        json=_mission_payload(finance_http_context["refs"]),
        headers=_headers(csrf_token, request_id="finance-forbidden"),
    )
    payload = _assert_envelope(response, status=403, success=False)
    assert payload["code"] == "forbidden"


def test_mission_http_crud_flow_and_audit_log(finance_http_context):
    client = finance_http_context["client"]
    csrf_token = finance_http_context["csrf_token"]
    mission = _create_mission(finance_http_context, competencia="2026-10")

    list_response = client.get(
        "/api/v1/financeiro/missoes?competencia=2026-10",
        headers=_headers(request_id="finance-list"),
    )
    list_payload = _assert_envelope(list_response, status=200, success=True)
    assert any(item["id"] == mission["id"] for item in list_payload["items"])

    detail_response = client.get(
        f"/api/v1/financeiro/missoes/{mission['id']}",
        headers=_headers(request_id="finance-detail"),
    )
    detail_payload = _assert_envelope(detail_response, status=200, success=True)
    assert detail_payload["mission"]["id"] == mission["id"]
    assert {item["funcao"] for item in detail_payload["participants"]} == {"comandante", "copiloto"}

    patch_response = client.patch(
        f"/api/v1/financeiro/missoes/{mission['id']}",
        json={"trecho": "BSB-CGH", "motivo": "ajuste http", "comandante_tripulante_id": 999999},
        headers=_headers(csrf_token, request_id="finance-patch"),
    )
    patch_payload = _assert_envelope(patch_response, status=200, success=True)
    assert patch_payload["mission"]["trecho"] == "BSB-CGH"
    assert patch_payload["mission"]["comandante_tripulante_id"] == finance_http_context["refs"]["comandante_id"]

    cancel_response = client.post(
        f"/api/v1/financeiro/missoes/{mission['id']}/cancelar",
        json={"motivo": "cancelamento http"},
        headers=_headers(csrf_token, request_id="finance-cancel"),
    )
    cancel_payload = _assert_envelope(cancel_response, status=200, success=True)
    assert cancel_payload["mission"]["status"] == "cancelada"

    with finance_http_context["app"].app_context():
        from backend.src.controle_treinamentos.db import close_db, get_db

        db = get_db()
        rows = db.execute(
            """
            SELECT acao
            FROM auditoria_eventos
            WHERE entidade = 'finance_mission'
              AND entidade_id = %s
            ORDER BY id
            """,
            (mission["id"],),
        ).fetchall()
        close_db()
    assert [row["acao"] for row in rows] == [
        "finance.mission.created",
        "finance.mission.updated",
        "finance.mission.cancel.requested",
        "finance.mission.cancelled",
    ]


def test_mission_delete_endpoint_soft_deletes_eligible_mission(finance_http_context):
    client = finance_http_context["client"]
    csrf_token = finance_http_context["csrf_token"]
    mission = _create_mission(finance_http_context, competencia="2026-09")

    delete_response = client.delete(
        f"/api/v1/financeiro/missoes/{mission['id']}",
        json={"motivo": "erro de lancamento"},
        headers=_headers(csrf_token, request_id="finance-delete"),
    )
    delete_payload = _assert_envelope(delete_response, status=200, success=True)
    assert delete_payload["action"] == "deleted"
    assert delete_payload["deleted"] is True
    assert delete_payload["mission"]["is_deleted"] is True

    list_response = client.get(
        "/api/v1/financeiro/missoes?competencia=2026-09",
        headers=_headers(request_id="finance-list-after-delete"),
    )
    list_payload = _assert_envelope(list_response, status=200, success=True)
    assert all(item["id"] != mission["id"] for item in list_payload["items"])

    detail_response = client.get(
        f"/api/v1/financeiro/missoes/{mission['id']}",
        headers=_headers(request_id="finance-detail-after-delete"),
    )
    _assert_envelope(detail_response, status=404, success=False)

    with finance_http_context["app"].app_context():
        from backend.src.controle_treinamentos.db import close_db, get_db

        db = get_db()
        rows = db.execute(
            """
            SELECT acao
            FROM auditoria_eventos
            WHERE entidade = 'finance_mission'
              AND entidade_id = %s
            ORDER BY id
            """,
            (mission["id"],),
        ).fetchall()
        close_db()
    assert [row["acao"] for row in rows] == [
        "finance.mission.created",
        "finance.mission.delete.requested",
        "finance.mission.deleted",
    ]


def test_duplicate_and_closed_period_errors_use_error_envelope(finance_http_context):
    client = finance_http_context["client"]
    csrf_token = finance_http_context["csrf_token"]
    payload = _mission_payload(finance_http_context["refs"], competencia="2026-11")

    first = client.post(
        "/api/v1/financeiro/missoes",
        json=payload,
        headers=_headers(csrf_token, request_id="finance-dup-first"),
    )
    _assert_envelope(first, status=201, success=True)

    duplicate = client.post(
        "/api/v1/financeiro/missoes",
        json=payload,
        headers=_headers(csrf_token, request_id="finance-dup-second"),
    )
    duplicate_payload = _assert_envelope(duplicate, status=409, success=False)
    assert duplicate_payload["code"] == "missao_operacional_duplicada"

    closed_competencia = "2026-12"
    with finance_http_context["app"].app_context():
        from backend.src.controle_treinamentos.db import close_db, get_db

        db = get_db()
        db.execute(
            """
            INSERT INTO financeiro_competencias (org_id, competencia, status)
            VALUES (%s, %s, 'fechada')
            ON CONFLICT (org_id, competencia) DO UPDATE SET status = EXCLUDED.status
            """,
            (FINANCE_ORG_SCOPE_DEFAULT, closed_competencia),
        )
        db.commit()
        close_db()

    blocked = client.post(
        "/api/v1/financeiro/missoes",
        json=_mission_payload(finance_http_context["refs"], competencia=closed_competencia),
        headers=_headers(csrf_token, request_id="finance-closed-create"),
    )
    blocked_payload = _assert_envelope(blocked, status=409, success=False)
    assert blocked_payload["code"] == "competencia_financeira_fechada"

    read_response = client.get(
        f"/api/v1/financeiro/missoes?competencia={closed_competencia}",
        headers=_headers(request_id="finance-closed-read"),
    )
    _assert_envelope(read_response, status=200, success=True)


def test_observability_endpoints_do_not_return_501(finance_http_context):
    client = finance_http_context["client"]
    _create_mission(finance_http_context, competencia="2026-10")

    endpoints = ("/api/v1/financeiro/auditoria", "/api/v1/financeiro/divergencias")
    for path in endpoints:
        response = client.open(
            path,
            method="GET",
            headers=_headers(request_id=f"finance-observability-{path.split('/')[-1]}"),
        )
        payload = _assert_envelope(response, status=200, success=True)
        assert isinstance(payload["items"], list)
