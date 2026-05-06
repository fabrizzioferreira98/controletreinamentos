from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import psycopg2
from dotenv import dotenv_values
from werkzeug.security import generate_password_hash


CSRF_RE = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = Path(r"C:\srv\controle-treinamentos\env\hml.env")


def _ensure_repo_on_path() -> None:
    root_str = str(ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def _extract_csrf(html: str) -> str:
    match = CSRF_RE.search(html)
    if not match:
        raise AssertionError("CSRF token not found in HTML response.")
    return match.group(1)


def _digits(size: int) -> str:
    digits = "".join(ch for ch in uuid.uuid4().hex if ch.isdigit())
    return digits[:size].ljust(size, "7")


def _unique_suffix() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class SmokeState:
    user_logins: list[str] = field(default_factory=list)
    tripulante_ids: list[int] = field(default_factory=list)
    pilot_ids: list[int] = field(default_factory=list)
    missao_ids: list[int] = field(default_factory=list)
    pernoite_ids: list[int] = field(default_factory=list)
    training_ids: list[int] = field(default_factory=list)
    segment_ids: list[int] = field(default_factory=list)
    hour_ids: list[int] = field(default_factory=list)
    type_ids: list[int] = field(default_factory=list)
    notificacao_ids: list[int] = field(default_factory=list)
    background_job_ids: list[int] = field(default_factory=list)


def _load_hml_env() -> dict[str, str]:
    values = {
        key: str(value)
        for key, value in dotenv_values(ENV_PATH).items()
        if value is not None
    }
    if "DATABASE_URL" not in values:
        raise RuntimeError(f"DATABASE_URL missing in {ENV_PATH}")
    return values


def _configure_env() -> dict[str, str]:
    values = _load_hml_env()
    os.environ.update(values)
    os.environ["DATABASE_URL"] = values["DATABASE_URL"]
    os.environ["APP_ENV"] = "testing"
    secret_key = "hml-runtime-polish-smoke"
    os.environ["SECRET_KEY"] = secret_key
    os.environ["SECRET_KEY_FINGERPRINT"] = hashlib.sha256(secret_key.encode("utf-8")).hexdigest()[:12]
    os.environ["FRONTEND_PUBLIC_ORIGIN"] = ""
    os.environ["FRONTEND_LOCAL_ORIGIN"] = ""
    os.environ["FRONTEND_COMPAT_REDIRECTS"] = "0"
    os.environ["ALLOW_LOCAL_DATABASE_IN_SECURE_ENV"] = "1"
    os.environ["ALLOW_INSECURE_HTTP_IN_SECURE_ENV"] = "1"
    return values


def _connect(db_url: str):
    return psycopg2.connect(db_url)


def _insert_temp_user(conn, *, login: str, password: str, perfil: str, permissions: list[str] | None) -> None:
    email = f"{login}@example.com"
    password_hash = generate_password_hash(password, method="pbkdf2:sha256")
    permissions_json = json.dumps(permissions or [], ensure_ascii=True)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO usuarios (nome, login, email, senha_hash, perfil, ativo, permissao_modulos_json)
            VALUES (%s, %s, %s, %s, %s, 1, %s)
            ON CONFLICT (login) DO UPDATE
            SET
                nome = EXCLUDED.nome,
                email = EXCLUDED.email,
                senha_hash = EXCLUDED.senha_hash,
                perfil = EXCLUDED.perfil,
                ativo = 1,
                permissao_modulos_json = EXCLUDED.permissao_modulos_json
            """,
            (login, login, email, password_hash, perfil, permissions_json),
        )
    conn.commit()


def _query_value(conn, sql: str, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    return None if row is None else row[0]


def _query_row(conn, sql: str, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return None
        columns = [desc[0] for desc in cur.description]
    return dict(zip(columns, row))


def _cleanup_temp_users(cur, user_logins: list[str]) -> None:
    cur.execute(
        """
        DELETE FROM usuarios u
        WHERE u.login = ANY(%s)
          AND u.login LIKE 'qa\\_runtime\\_smoke\\_%%' ESCAPE '\\'
          AND NOT EXISTS (SELECT 1 FROM historico_status_piloto h WHERE h.alterado_por = u.id)
          AND NOT EXISTS (SELECT 1 FROM auditoria_eventos a WHERE a.realizado_por = u.id)
          AND NOT EXISTS (SELECT 1 FROM treinamento_anexos_pdf ta WHERE ta.enviado_por = u.id)
          AND NOT EXISTS (SELECT 1 FROM tripulante_arquivos_pdf tp WHERE tp.enviado_por = u.id OR tp.removido_por = u.id)
          AND NOT EXISTS (SELECT 1 FROM background_jobs bj WHERE bj.requested_by = u.id)
        """,
        (user_logins,),
    )
    cur.execute(
        """
        UPDATE usuarios
        SET ativo = 0
        WHERE login = ANY(%s)
          AND login LIKE 'qa\\_runtime\\_smoke\\_%%' ESCAPE '\\'
        """,
        (user_logins,),
    )


def _cleanup(conn, state: SmokeState) -> None:
    with conn.cursor() as cur:
        if state.background_job_ids:
            cur.execute("DELETE FROM background_jobs WHERE id = ANY(%s)", (state.background_job_ids,))
        if state.notificacao_ids:
            cur.execute("DELETE FROM notificacoes_email WHERE id = ANY(%s)", (state.notificacao_ids,))
        if state.training_ids:
            cur.execute("DELETE FROM treinamento_anexos_pdf WHERE treinamento_id = ANY(%s)", (state.training_ids,))
            cur.execute("DELETE FROM notificacoes_treinamento WHERE treinamento_id = ANY(%s)", (state.training_ids,))
            cur.execute("DELETE FROM treinamentos WHERE id = ANY(%s)", (state.training_ids,))
        if state.pernoite_ids:
            cur.execute("DELETE FROM pernoites_operacionais WHERE id = ANY(%s)", (state.pernoite_ids,))
        if state.missao_ids:
            cur.execute("DELETE FROM missao_tripulantes WHERE missao_id = ANY(%s)", (state.missao_ids,))
            cur.execute("DELETE FROM missoes_operacionais WHERE id = ANY(%s)", (state.missao_ids,))
        if state.pilot_ids:
            cur.execute("DELETE FROM historico_status_piloto WHERE piloto_id = ANY(%s)", (state.pilot_ids,))
            cur.execute("DELETE FROM pilotos WHERE id = ANY(%s)", (state.pilot_ids,))
        if state.hour_ids:
            cur.execute("DELETE FROM horas_voo_aeronave WHERE id = ANY(%s)", (state.hour_ids,))
        if state.segment_ids:
            cur.execute("DELETE FROM segmentos_teoricos WHERE id = ANY(%s)", (state.segment_ids,))
        if state.type_ids:
            cur.execute("DELETE FROM tipos_treinamento WHERE id = ANY(%s)", (state.type_ids,))
        if state.tripulante_ids:
            cur.execute("DELETE FROM historico_status_piloto WHERE piloto_id IN (SELECT id FROM pilotos WHERE tripulante_id = ANY(%s))", (state.tripulante_ids,))
            cur.execute("DELETE FROM pilotos WHERE tripulante_id = ANY(%s)", (state.tripulante_ids,))
            cur.execute("DELETE FROM tripulante_arquivos_pdf WHERE tripulante_id = ANY(%s)", (state.tripulante_ids,))
            cur.execute("DELETE FROM tripulantes WHERE id = ANY(%s)", (state.tripulante_ids,))
        if state.user_logins:
            _cleanup_temp_users(cur, state.user_logins)
    conn.commit()


def _login_html(client, *, login: str, senha: str) -> None:
    login_page = client.get("/login")
    assert login_page.status_code == 200, login_page.status_code
    csrf_token = _extract_csrf(login_page.get_data(as_text=True))
    response = client.post(
        "/login",
        data={"csrf_token": csrf_token, "login": login, "senha": senha},
        follow_redirects=False,
    )
    assert response.status_code in {302, 303}, response.status_code


def _api_csrf(client) -> str:
    response = client.get("/api/v1/session")
    assert response.status_code == 200, response.status_code
    payload = response.get_json()
    assert payload and payload.get("csrf_token"), payload
    return str(payload["csrf_token"])


def _post_form(client, path: str, *, csrf_token: str, data: dict, follow_redirects: bool = False):
    return client.post(
        path,
        data={"csrf_token": csrf_token, **data},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=follow_redirects,
    )


def main() -> int:
    env = _configure_env()
    _ensure_repo_on_path()

    from backend.src.controle_treinamentos import create_app
    from backend.src.controle_treinamentos.infra.mailer import validate_notification_dispatch_readiness

    db_url = env["DATABASE_URL"]
    state = SmokeState()
    suffix = _unique_suffix()
    gestora_login = "qa_runtime_smoke_gestora"
    operador_login = "qa_runtime_smoke_operador"
    password = "QaSmoke#2026"
    state.user_logins.extend([gestora_login, operador_login])

    try:
        with _connect(db_url) as conn:
            _insert_temp_user(conn, login=gestora_login, password=password, perfil="gestora", permissions=[])
            _insert_temp_user(conn, login=operador_login, password=password, perfil="operador", permissions=["dashboard:view"])

            app = create_app()
            client = app.test_client()
            _login_html(client, login=gestora_login, senha=password)
            api_csrf = _api_csrf(client)

            with conn.cursor() as cur:
                cur.execute("SELECT id, nome FROM bases WHERE ativa = TRUE ORDER BY nome")
                base_rows = cur.fetchall()
            assert base_rows, "No active bases available in HML."
            base_a_id, base_a_nome = int(base_rows[0][0]), str(base_rows[0][1])
            base_b_id = int(base_rows[1][0]) if len(base_rows) > 1 else base_a_id

            trip_payload = {
                "nome": f"QA Smoke Trip {suffix}",
                "cpf": _digits(11),
                "licenca_anac": _digits(6),
                "email": f"trip.{suffix}@example.com",
                "telefone": "11999999999",
                "base": base_a_nome,
                "status": "Ativo",
                "funcao_operacional": "copiloto",
                "categoria_operacional": "A",
                "observacoes": "qa runtime smoke",
                "ativo": True,
                "sdea_ativo": False,
                "instrutor_ativo": False,
                "checador_ativo": False,
                "elegivel_adicional_excepcional": False,
            }
            trip_resp = client.post("/api/v1/tripulantes", json=trip_payload, headers={"X-CSRFToken": api_csrf})
            assert trip_resp.status_code == 201, trip_resp.get_data(as_text=True)
            tripulante_id = int(trip_resp.get_json()["tripulante"]["id"])
            state.tripulante_ids.append(tripulante_id)

            trip_update = client.put(
                f"/api/v1/tripulantes/{tripulante_id}",
                json={**trip_payload, "observacoes": "qa runtime smoke updated"},
                headers={"X-CSRFToken": api_csrf},
            )
            assert trip_update.status_code == 200, trip_update.get_data(as_text=True)

            type_resp = client.post(
                "/api/v1/treinamento-raiz/tipos",
                json={
                    "nome": f"QA Tipo {suffix}",
                    "codigo": f"QA-{suffix[:6].upper()}",
                    "descricao": "qa runtime smoke type",
                    "status": "Ativo",
                    "exige_aeronave": "Sim",
                },
                headers={"X-CSRFToken": api_csrf},
            )
            assert type_resp.status_code == 201, type_resp.get_data(as_text=True)
            tipo_id = int(type_resp.get_json()["item"]["id"])
            state.type_ids.append(tipo_id)

            segment_resp = client.post(
                "/api/v1/treinamento-raiz/segmentos",
                json={
                    "tipo_treinamento_id": tipo_id,
                    "modelo_segmento": "Gerais",
                    "nome_segmento": f"Segmento QA {suffix}",
                    "carga_horaria": 1,
                    "carga_teorica": 1,
                    "carga_pratica": 0,
                    "periodicidade_meses": 12,
                    "observacao": "",
                    "ativo": 1,
                },
                headers={"X-CSRFToken": api_csrf},
            )
            assert segment_resp.status_code == 201, segment_resp.get_data(as_text=True)
            segment_id = int(segment_resp.get_json()["item"]["id"])
            state.segment_ids.append(segment_id)

            aircraft_model = f"QA-AIR-{suffix[:4].upper()}"
            hour_resp = client.post(
                "/api/v1/treinamento-raiz/horas-voo",
                json={
                    "tipo_treinamento_id": tipo_id,
                    "aeronave_modelo": aircraft_model,
                    "solo_horas": 1,
                    "voo_pic_sic_horas": 2,
                    "voo_crew_horas": 0,
                    "observacao": "",
                    "ativo": 1,
                },
                headers={"X-CSRFToken": api_csrf},
            )
            assert hour_resp.status_code == 201, hour_resp.get_data(as_text=True)
            hour_id = int(hour_resp.get_json()["item"]["id"])
            state.hour_ids.append(hour_id)

            template_resp = client.get(
                f"/api/v1/treinamentos-tripulantes/template?tipo_treinamento_id={tipo_id}&aeronave_modelo={aircraft_model}"
            )
            assert template_resp.status_code == 200, template_resp.get_data(as_text=True)
            assert template_resp.get_json()["template"]["segmentos"]

            batch_resp = client.post(
                "/api/v1/treinamentos-tripulantes/batch",
                json={
                    "tripulante_id": tripulante_id,
                    "tipo_treinamento_id": tipo_id,
                    "aeronave_modelo": aircraft_model,
                    "segmentos": [{
                        "segmento_id": segment_id,
                        "data_realizacao": str(date.today()),
                        "observacao": "batch qa smoke",
                    }],
                },
                headers={"X-CSRFToken": api_csrf},
            )
            assert batch_resp.status_code == 201, batch_resp.get_data(as_text=True)
            training_id = int(batch_resp.get_json()["created_ids"][0])
            state.training_ids.append(training_id)

            update_resp = client.put(
                f"/api/v1/treinamentos-tripulantes/{training_id}",
                json={
                    "tripulante_id": tripulante_id,
                    "tipo_treinamento_id": tipo_id,
                    "segmento_id": segment_id,
                    "aeronave_modelo": aircraft_model,
                    "data_realizacao": str(date.today()),
                    "observacao": "batch qa smoke updated",
                },
                headers={"X-CSRFToken": api_csrf},
            )
            assert update_resp.status_code == 200, update_resp.get_data(as_text=True)

            for pdf_url in (
                "/auditoria/export.pdf",
                "/treinamentos/consolidado/export.pdf",
            ):
                pdf_resp = client.get(pdf_url)
                assert pdf_resp.status_code == 200, (pdf_url, pdf_resp.status_code)
                assert pdf_resp.mimetype == "application/pdf", (pdf_url, pdf_resp.mimetype)

            dashboard_page = client.get("/dashboard")
            assert dashboard_page.status_code == 200, dashboard_page.status_code
            html_csrf = _extract_csrf(dashboard_page.get_data(as_text=True))

            pilot_resp = _post_form(
                client,
                "/bases/pilotos/adicionar",
                csrf_token=html_csrf,
                data={
                    "nome": f"QA Piloto {suffix}",
                    "matricula": f"QA{suffix[:6].upper()}",
                    "status": "ativo",
                    "base_id": str(base_a_id),
                    "observacao": "qa runtime smoke",
                },
            )
            assert pilot_resp.status_code == 201, pilot_resp.get_data(as_text=True)
            pilot_id = int(pilot_resp.get_json()["pilot_id"])
            state.pilot_ids.append(pilot_id)

            status_resp = _post_form(
                client,
                f"/bases/pilotos/{pilot_id}/status",
                csrf_token=html_csrf,
                data={"status_novo": "folga", "observacao": "qa runtime smoke status"},
            )
            assert status_resp.status_code == 200, status_resp.get_data(as_text=True)

            if base_b_id != base_a_id:
                move_resp = _post_form(
                    client,
                    f"/bases/pilotos/{pilot_id}/mover",
                    csrf_token=html_csrf,
                    data={"base_nova_id": str(base_b_id), "observacao": "qa runtime smoke move"},
                )
                assert move_resp.status_code == 200, move_resp.get_data(as_text=True)

            historico_resp = client.get(f"/bases/pilotos/{pilot_id}/historico")
            assert historico_resp.status_code == 200, historico_resp.get_data(as_text=True)
            assert historico_resp.get_json()["historico"]

            missao_code = f"QA-{suffix[:6].upper()}"
            missao_create = _post_form(
                client,
                "/missoes/novo",
                csrf_token=html_csrf,
                data={
                    "codigo_voo": missao_code,
                    "contratante": "QA Smoke",
                    "data_inicio": str(date.today()),
                    "data_fim": str(date.today()),
                    "origem": "SBSP",
                    "destino": "SBRJ",
                    "tipo_operacao": "Executiva",
                    "tripulante_ids": str(tripulante_id),
                    "observacoes": "qa runtime smoke missao",
                },
            )
            assert missao_create.status_code in {302, 303}, missao_create.status_code
            missao_id = int(_query_value(conn, "SELECT id FROM missoes_operacionais WHERE codigo_voo = %s ORDER BY id DESC LIMIT 1", (missao_code,)))
            state.missao_ids.append(missao_id)

            missao_edit = _post_form(
                client,
                f"/missoes/{missao_id}/editar",
                csrf_token=html_csrf,
                data={
                    "codigo_voo": missao_code,
                    "contratante": "QA Smoke Updated",
                    "data_inicio": str(date.today()),
                    "data_fim": str(date.today()),
                    "origem": "SBSP",
                    "destino": "SBRJ",
                    "tipo_operacao": "Executiva",
                    "tripulante_ids": str(tripulante_id),
                    "observacoes": "qa runtime smoke missao updated",
                },
            )
            assert missao_edit.status_code in {302, 303}, missao_edit.status_code

            pernoite_create = _post_form(
                client,
                "/pernoites/novo",
                csrf_token=html_csrf,
                data={
                    "tripulante_id": str(tripulante_id),
                    "missao_id": str(missao_id),
                    "data_pernoite": str(date.today()),
                    "tipo_pernoite": "cobertura_base",
                    "quantidade": "1",
                    "observacoes": "qa runtime smoke pernoite",
                },
            )
            assert pernoite_create.status_code in {302, 303}, pernoite_create.status_code
            pernoite_id = int(_query_value(conn, "SELECT id FROM pernoites_operacionais WHERE tripulante_id = %s ORDER BY id DESC LIMIT 1", (tripulante_id,)))
            state.pernoite_ids.append(pernoite_id)

            pernoite_edit = _post_form(
                client,
                f"/pernoites/{pernoite_id}/editar",
                csrf_token=html_csrf,
                data={
                    "tripulante_id": str(tripulante_id),
                    "missao_id": str(missao_id),
                    "data_pernoite": str(date.today()),
                    "tipo_pernoite": "operacional_comum",
                    "quantidade": "2",
                    "observacoes": "qa runtime smoke pernoite updated",
                },
            )
            assert pernoite_edit.status_code in {302, 303}, pernoite_edit.status_code

            notif_new_page = client.get("/notificacoes-email/novo")
            assert notif_new_page.status_code == 200, notif_new_page.status_code
            notif_csrf = _extract_csrf(notif_new_page.get_data(as_text=True))
            notif_email = f"notify.{suffix}@example.com"
            notif_create = _post_form(
                client,
                "/notificacoes-email/novo",
                csrf_token=notif_csrf,
                data={"email_destinatario": notif_email, "ativo": "on"},
            )
            assert notif_create.status_code in {302, 303}, notif_create.status_code
            notificacao_id = int(_query_value(conn, "SELECT id FROM notificacoes_email WHERE email_destinatario = %s", (notif_email,)))
            state.notificacao_ids.append(notificacao_id)

            notif_edit = _post_form(
                client,
                f"/notificacoes-email/{notificacao_id}/editar",
                csrf_token=notif_csrf,
                data={"email_destinatario": notif_email, "ativo": "on"},
            )
            assert notif_edit.status_code in {302, 303}, notif_edit.status_code

            before_backup_jobs = int(_query_value(conn, "SELECT COUNT(*) FROM background_jobs WHERE job_type = %s", ("run_backup",)))
            backup_run = _post_form(client, "/backups/executar", csrf_token=html_csrf, data={}, follow_redirects=False)
            assert backup_run.status_code in {302, 303}, backup_run.status_code
            after_backup_jobs = int(_query_value(conn, "SELECT COUNT(*) FROM background_jobs WHERE job_type = %s", ("run_backup",)))
            assert after_backup_jobs == before_backup_jobs + 1, (before_backup_jobs, after_backup_jobs)
            if after_backup_jobs > before_backup_jobs:
                backup_row = _query_row(conn, "SELECT id FROM background_jobs WHERE job_type = %s ORDER BY id DESC LIMIT 1", ("run_backup",))
                if backup_row:
                    state.background_job_ids.append(int(backup_row["id"]))

            with app.app_context():
                notification_readiness = validate_notification_dispatch_readiness()
            before_notification_jobs = int(_query_value(conn, "SELECT COUNT(*) FROM background_jobs WHERE job_type = %s", ("send_daily_notifications",)))
            notif_manual = _post_form(client, "/notificacoes-email/disparo-manual", csrf_token=notif_csrf, data={}, follow_redirects=False)
            assert notif_manual.status_code in {302, 303}, notif_manual.status_code
            after_notification_jobs = int(_query_value(conn, "SELECT COUNT(*) FROM background_jobs WHERE job_type = %s", ("send_daily_notifications",)))
            if notification_readiness.get("email_ready"):
                assert after_notification_jobs == before_notification_jobs + 1, (before_notification_jobs, after_notification_jobs)
            else:
                assert after_notification_jobs == before_notification_jobs, (before_notification_jobs, after_notification_jobs)
            if after_notification_jobs > before_notification_jobs:
                notif_job = _query_row(conn, "SELECT id FROM background_jobs WHERE job_type = %s ORDER BY id DESC LIMIT 1", ("send_daily_notifications",))
                if notif_job:
                    state.background_job_ids.append(int(notif_job["id"]))

            pernoite_delete = _post_form(client, f"/pernoites/{pernoite_id}/excluir", csrf_token=html_csrf, data={})
            assert pernoite_delete.status_code in {302, 303}, pernoite_delete.status_code
            state.pernoite_ids.clear()

            missao_delete = _post_form(client, f"/missoes/{missao_id}/excluir", csrf_token=html_csrf, data={})
            assert missao_delete.status_code in {302, 303}, missao_delete.status_code
            state.missao_ids.clear()

            training_delete = client.delete(f"/api/v1/treinamentos-tripulantes/{training_id}", headers={"X-CSRFToken": api_csrf})
            assert training_delete.status_code == 200, training_delete.get_data(as_text=True)
            state.training_ids.clear()

            hour_delete = client.delete(f"/api/v1/treinamento-raiz/horas-voo/{hour_id}", headers={"X-CSRFToken": api_csrf})
            assert hour_delete.status_code == 200, hour_delete.get_data(as_text=True)
            state.hour_ids.clear()

            segment_delete = client.delete(f"/api/v1/treinamento-raiz/segmentos/{segment_id}", headers={"X-CSRFToken": api_csrf})
            assert segment_delete.status_code == 200, segment_delete.get_data(as_text=True)
            state.segment_ids.clear()

            type_delete = client.delete(f"/api/v1/treinamento-raiz/tipos/{tipo_id}", headers={"X-CSRFToken": api_csrf})
            assert type_delete.status_code == 200, type_delete.get_data(as_text=True)
            state.type_ids.clear()

            trip_delete = client.delete(f"/api/v1/tripulantes/{tripulante_id}", headers={"X-CSRFToken": api_csrf})
            assert trip_delete.status_code == 200, trip_delete.get_data(as_text=True)
            state.tripulante_ids.clear()

            restricted = app.test_client()
            _login_html(restricted, login=operador_login, senha=password)
            forbidden = restricted.get("/usuarios", follow_redirects=False)
            assert forbidden.status_code == 403, forbidden.status_code
            assert "Acesso negado" in forbidden.get_data(as_text=True)
    finally:
        with _connect(db_url) as cleanup_conn:
            _cleanup(cleanup_conn, state)

    result = {
        "ok": True,
        "environment": "hml",
        "validated": {
            "tripulantes": True,
            "training_master": True,
            "training_batch": True,
            "pdf_exports": True,
            "bases_mutation": True,
            "missoes_mutation": True,
            "pernoites_mutation": True,
            "backups_enqueue": True,
            "notifications_manual_route": bool(notification_readiness.get("email_ready")),
            "notifications_blocked_by_config": not bool(notification_readiness.get("email_ready")),
            "html_forbidden_403": True,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
