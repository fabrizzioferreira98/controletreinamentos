from __future__ import annotations

import argparse
import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path

import psycopg2
from werkzeug.security import generate_password_hash


PNG_1X1_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
DEFAULT_E2E_LOGIN = "qa_release_e2e"


class E2EFailure(RuntimeError):
    pass


@dataclass
class StepResult:
    name: str
    ok: bool
    duration_ms: int
    detail: str


@dataclass
class CleanupState:
    user_login: str = ""
    tripulante_ids: list[int] | None = None
    treinamento_ids: list[int] | None = None
    equipamento_ids: list[int] | None = None
    tipo_ids: list[int] | None = None
    treinamento_anexo_ids: list[int] | None = None
    tripulante_file_ids: list[int] | None = None

    def __post_init__(self) -> None:
        self.tripulante_ids = self.tripulante_ids or []
        self.treinamento_ids = self.treinamento_ids or []
        self.equipamento_ids = self.equipamento_ids or []
        self.tipo_ids = self.tipo_ids or []
        self.treinamento_anexo_ids = self.treinamento_anexo_ids or []
        self.tripulante_file_ids = self.tripulante_file_ids or []


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_env(name: str) -> str:
    value = (os.getenv(name, "") or "").strip()
    if not value:
        raise E2EFailure(f"missing_env:{name}")
    return value


def _db_connect():
    return psycopg2.connect(_require_env("DATABASE_URL"))


def _pdf_base64(label: str) -> str:
    body = f"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Producer ({label}) >>\nendobj\n%%EOF"
    return base64.b64encode(body.encode("utf-8")).decode("ascii")


def _png_data_uri() -> str:
    return f"data:image/png;base64,{PNG_1X1_BASE64}"


def _png_bytes() -> bytes:
    return base64.b64decode(PNG_1X1_BASE64)


def _build_opener(cookie_jar: CookieJar | None = None) -> urllib.request.OpenerDirector:
    jar = cookie_jar or CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def _clone_cookie_jar(source: CookieJar) -> CookieJar:
    cloned = CookieJar()
    for cookie in source:
        cloned.set_cookie(cookie)
    return cloned


def _cookie_jar_from_opener(opener: urllib.request.OpenerDirector) -> CookieJar:
    for handler in opener.handlers:
        if isinstance(handler, urllib.request.HTTPCookieProcessor):
            return handler.cookiejar
    raise E2EFailure("cookie_jar_missing")


def _request(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json_payload: dict | None = None,
) -> tuple[int, bytes, dict[str, str], str]:
    body_bytes = None
    request_headers = dict(headers or {})
    if json_payload is not None:
        body_bytes = json.dumps(json_payload).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request_headers.setdefault("Accept", "application/json")
    request_headers.setdefault("User-Agent", "controle-treinamentos-release-e2e")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        method=method,
        headers=request_headers,
        data=body_bytes,
    )
    try:
        with opener.open(request, timeout=20) as response:
            return response.status, response.read(), dict(response.headers), response.geturl()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers), exc.geturl()
    except urllib.error.URLError as exc:
        raise E2EFailure(f"network_error:{path}:{exc.reason}") from exc


def _json_request(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    json_payload: dict | None = None,
) -> tuple[int, dict, dict[str, str], str]:
    status, body, response_headers, final_url = _request(
        opener,
        base_url,
        path,
        method=method,
        headers=headers,
        json_payload=json_payload,
    )
    try:
        payload = json.loads(body.decode("utf-8", "ignore") or "{}")
    except json.JSONDecodeError as exc:
        raise E2EFailure(f"invalid_json_response:{path}:{status}") from exc
    if not isinstance(payload, dict):
        raise E2EFailure(f"unexpected_json_shape:{path}:{status}")
    return status, payload, response_headers, final_url


def _assert_status(status: int, expected: set[int], *, label: str) -> None:
    if status not in expected:
        raise E2EFailure(f"{label}:unexpected_status:{status}:expected:{sorted(expected)}")


def _assert_json_true(payload: dict, field: str, *, label: str) -> None:
    if not bool(payload.get(field)):
        raise E2EFailure(f"{label}:{field}_false")


def _active_base_name(conn) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT nome FROM bases WHERE ativa = TRUE ORDER BY nome LIMIT 1")
        row = cur.fetchone()
    if row is None:
        raise E2EFailure("active_base_missing")
    return str(row[0])


def _insert_release_user(conn, *, login: str, password: str) -> None:
    email = f"{login}@example.com"
    password_hash = generate_password_hash(password, method="pbkdf2:sha256")
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
            ("QA Release E2E", login, email, password_hash, "gestora", "[]"),
        )
    conn.commit()


def _random_digits(size: int) -> str:
    digits = "".join(ch for ch in uuid.uuid4().hex if ch.isdigit())
    return digits[:size].ljust(size, "7")


def _create_tripulante(conn, *, name_prefix: str, base_name: str) -> int:
    nome = f"{name_prefix}-{uuid.uuid4().hex[:6]}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tripulantes
                (nome, cpf, licenca_anac, email, telefone, base, status, ativo)
            VALUES
                (%s, %s, %s, %s, %s, %s, 'Ativo', 1)
            RETURNING id
            """,
            (nome, _random_digits(11), f"ANAC-{uuid.uuid4().hex[:8].upper()}", f"{nome.lower()}@example.com", "11999999999", base_name),
        )
        return int(cur.fetchone()[0])


def _create_equipamento(conn, *, nome: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO equipamentos (nome, tipo, ativo) VALUES (%s, %s, 1) RETURNING id",
            (nome, "E2E"),
        )
        return int(cur.fetchone()[0])


def _create_tipo_treinamento(conn, *, nome: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tipos_treinamento (nome, periodicidade_meses, exige_equipamento, ativo)
            VALUES (%s, %s, 1, 1)
            RETURNING id
            """,
            (nome, 12),
        )
        return int(cur.fetchone()[0])


def _create_treinamento(conn, *, tripulante_id: int, equipamento_id: int, tipo_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO treinamentos (
                tripulante_id,
                equipamento_id,
                tipo_treinamento_id,
                data_realizacao,
                data_vencimento,
                observacao
            )
            VALUES (%s, %s, %s, CURRENT_DATE, CURRENT_DATE + INTERVAL '365 days', 'release e2e')
            RETURNING id
            """,
            (tripulante_id, equipamento_id, tipo_id),
        )
        return int(cur.fetchone()[0])


def _tripulante_nome(conn, tripulante_id: int) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT nome FROM tripulantes WHERE id = %s", (tripulante_id,))
        row = cur.fetchone()
    if row is None:
        raise E2EFailure(f"tripulante_not_found:{tripulante_id}")
    return str(row[0])


def _cleanup(conn, state: CleanupState) -> None:
    with conn.cursor() as cur:
        if state.treinamento_anexo_ids:
            cur.execute("DELETE FROM treinamento_anexos_pdf WHERE id = ANY(%s)", (state.treinamento_anexo_ids,))
        if state.treinamento_ids:
            cur.execute("DELETE FROM treinamento_anexos_pdf WHERE treinamento_id = ANY(%s)", (state.treinamento_ids,))
            cur.execute("DELETE FROM treinamentos WHERE id = ANY(%s)", (state.treinamento_ids,))
        if state.tripulante_file_ids:
            cur.execute("DELETE FROM tripulante_arquivos_pdf WHERE id = ANY(%s)", (state.tripulante_file_ids,))
        if state.tripulante_ids:
            cur.execute("DELETE FROM tripulante_arquivos_pdf WHERE tripulante_id = ANY(%s)", (state.tripulante_ids,))
            cur.execute("DELETE FROM tripulantes WHERE id = ANY(%s)", (state.tripulante_ids,))
        if state.equipamento_ids:
            cur.execute("DELETE FROM equipamentos WHERE id = ANY(%s)", (state.equipamento_ids,))
        if state.tipo_ids:
            cur.execute("DELETE FROM tipos_treinamento WHERE id = ANY(%s)", (state.tipo_ids,))
        if state.user_login:
            cur.execute("DELETE FROM usuarios WHERE login = %s", (state.user_login,))
    conn.commit()


def _current_csrf(opener: urllib.request.OpenerDirector, base_url: str) -> str:
    status, payload, _, _ = _json_request(opener, base_url, "/api/v1/session")
    _assert_status(status, {200}, label="session_state")
    token = str(payload.get("csrf_token", "") or "").strip()
    if not token:
        raise E2EFailure("session_state:csrf_missing")
    return token


def _api_login(opener: urllib.request.OpenerDirector, base_url: str, *, login: str, password: str) -> dict:
    csrf = _current_csrf(opener, base_url)
    status, payload, _, _ = _json_request(
        opener,
        base_url,
        "/api/v1/session/login",
        method="POST",
        headers={"X-CSRFToken": csrf},
        json_payload={"login": login, "senha": password},
    )
    _assert_status(status, {200}, label="api_login")
    if str(payload.get("code", "")) != "auth_ok":
        raise E2EFailure(f"api_login:unexpected_code:{payload.get('code')}")
    _assert_json_true(payload, "authenticated", label="api_login")
    return payload


def _api_logout(opener: urllib.request.OpenerDirector, base_url: str) -> dict:
    csrf = _current_csrf(opener, base_url)
    status, payload, _, _ = _json_request(
        opener,
        base_url,
        "/api/v1/session/logout",
        method="POST",
        headers={"X-CSRFToken": csrf},
        json_payload={},
    )
    _assert_status(status, {200}, label="api_logout")
    if str(payload.get("code", "")) != "logout_ok":
        raise E2EFailure(f"api_logout:unexpected_code:{payload.get('code')}")
    return payload


def _step(results: list[StepResult], name: str, fn) -> None:
    start = time.monotonic()
    detail = ""
    try:
        maybe_detail = fn()
        detail = str(maybe_detail or "ok")
        results.append(
            StepResult(
                name=name,
                ok=True,
                duration_ms=int((time.monotonic() - start) * 1000),
                detail=detail,
            )
        )
    except Exception as exc:
        results.append(
            StepResult(
                name=name,
                ok=False,
                duration_ms=int((time.monotonic() - start) * 1000),
                detail=str(exc),
            )
        )
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa uma rodada real de e2e_homolog contra o runtime vivo de homolog.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--round-index", type=int, default=1)
    parser.add_argument("--login", default="")
    parser.add_argument("--password", default="")
    args = parser.parse_args()

    base_url = (args.base_url or "").strip().rstrip("/")
    login = (args.login or "").strip() or (os.getenv("E2E_LOGIN", "") or "").strip() or DEFAULT_E2E_LOGIN
    password = (args.password or "").strip() or (os.getenv("E2E_PASSWORD", "") or "").strip() or f"QaRelease#{uuid.uuid4().hex[:8]}"

    started_at = _utc_now()
    results: list[StepResult] = []
    cleanup_state = CleanupState(user_login=login)
    opener = _build_opener()
    cookie_jar = _cookie_jar_from_opener(opener)

    try:
        with _db_connect() as conn:
            base_name = _active_base_name(conn)
            _insert_release_user(conn, login=login, password=password)

            _step(
                results,
                "session_state_anonymous",
                lambda: (
                    _assert_status(
                        _json_request(opener, base_url, "/api/v1/session")[0],
                        {200},
                        label="session_state_anonymous",
                    ),
                    "anonymous_session_ok",
                )[1],
            )

            _step(
                results,
                "api_login_success",
                lambda: (
                    _api_login(opener, base_url, login=login, password=password),
                    f"login={login}",
                )[1],
            )

            def session_authenticated_detail() -> str:
                status, session_payload, _, _ = _json_request(opener, base_url, "/api/v1/session")
                _assert_status(status, {200}, label="session_state_authenticated")
                _assert_json_true(session_payload, "authenticated", label="session_state_authenticated")
                status_me, me_payload, _, _ = _json_request(opener, base_url, "/api/v1/me")
                _assert_status(status_me, {200}, label="api_me")
                if str(me_payload.get("code", "")) != "me_ok":
                    raise E2EFailure(f"api_me:unexpected_code:{me_payload.get('code')}")
                status_caps, caps_payload, _, _ = _json_request(opener, base_url, "/api/v1/capabilities")
                _assert_status(status_caps, {200}, label="api_capabilities")
                if str(caps_payload.get("code", "")) != "capabilities_ok":
                    raise E2EFailure(f"api_capabilities:unexpected_code:{caps_payload.get('code')}")
                return f"user={me_payload['user']['login']}"

            _step(results, "session_authenticated_and_capabilities", session_authenticated_detail)

            def second_opener_detail() -> str:
                second = _build_opener(_clone_cookie_jar(cookie_jar))
                status, me_payload, _, _ = _json_request(second, base_url, "/api/v1/me")
                _assert_status(status, {200}, label="api_me_second_opener")
                if str(me_payload.get("code", "")) != "me_ok":
                    raise E2EFailure(f"api_me_second_opener:unexpected_code:{me_payload.get('code')}")
                return "second_opener_authenticated"

            _step(results, "second_opener_same_session", second_opener_detail)

            def programmatic_routes_detail() -> str:
                endpoints = (
                    "/api/v1/dashboard/summary",
                    "/api/v1/dashboard/calendar",
                    "/api/v1/dashboard/critical-trainings",
                    "/bases/api/dados?status=ativo",
                )
                for path in endpoints:
                    status, payload, _, _ = _json_request(opener, base_url, path)
                    _assert_status(status, {200}, label=f"programmatic:{path}")
                    if not isinstance(payload, dict):
                        raise E2EFailure(f"programmatic:{path}:non_dict_payload")
                return f"endpoints={len(endpoints)}"

            _step(results, "programmatic_routes_json", programmatic_routes_detail)

            def mobile_detail() -> str:
                headers = {
                    "User-Agent": (
                        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
                    )
                }
                status, payload, _, _ = _json_request(opener, base_url, "/bases/api/dados?status=ativo", headers=headers)
                _assert_status(status, {200}, label="mobile_programmatic")
                if not isinstance(payload, dict):
                    raise E2EFailure("mobile_programmatic:non_dict_payload")
                return "mobile_route_ok"

            _step(results, "mobile_user_agent_programmatic_route", mobile_detail)

            def tripulante_crud_detail() -> str:
                csrf = _current_csrf(opener, base_url)
                payload = {
                    "nome": f"QA API Trip {uuid.uuid4().hex[:6]}",
                    "cpf": _random_digits(11),
                    "licenca_anac": _random_digits(6),
                    "email": f"trip.{uuid.uuid4().hex[:6]}@example.com",
                    "telefone": "11999999999",
                    "base": base_name,
                    "status": "Ativo",
                    "funcao_operacional": "copiloto",
                    "categoria_operacional": "A",
                    "observacoes": "release e2e",
                    "ativo": True,
                    "sdea_ativo": False,
                    "instrutor_ativo": False,
                    "checador_ativo": False,
                    "elegivel_adicional_excepcional": False,
                }
                status, created, _, _ = _json_request(
                    opener,
                    base_url,
                    "/api/v1/tripulantes",
                    method="POST",
                    headers={"X-CSRFToken": csrf},
                    json_payload=payload,
                )
                _assert_status(status, {201}, label="tripulante_create")
                tripulante_id = int(created["tripulante"]["id"])
                cleanup_state.tripulante_ids.append(tripulante_id)
                payload["observacoes"] = "release e2e updated"
                status, updated, _, _ = _json_request(
                    opener,
                    base_url,
                    f"/api/v1/tripulantes/{tripulante_id}",
                    method="PUT",
                    headers={"X-CSRFToken": _current_csrf(opener, base_url)},
                    json_payload=payload,
                )
                _assert_status(status, {200}, label="tripulante_update")
                if str(updated.get("code", "")) != "tripulante_updated":
                    raise E2EFailure(f"tripulante_update:unexpected_code:{updated.get('code')}")
                status, deleted, _, _ = _json_request(
                    opener,
                    base_url,
                    f"/api/v1/tripulantes/{tripulante_id}",
                    method="DELETE",
                    headers={"X-CSRFToken": _current_csrf(opener, base_url)},
                    json_payload={},
                )
                _assert_status(status, {200}, label="tripulante_delete")
                if str(deleted.get("code", "")) not in {"tripulante_deleted", "tripulante_inactivated"}:
                    raise E2EFailure(f"tripulante_delete:unexpected_code:{deleted.get('code')}")
                cleanup_state.tripulante_ids.remove(tripulante_id)
                return f"tripulante_id={tripulante_id}"

            _step(results, "tripulante_crud_via_api", tripulante_crud_detail)

            def file_flow_detail() -> str:
                tripulante_id = _create_tripulante(conn, name_prefix="E2E-FILE", base_name=base_name)
                cleanup_state.tripulante_ids.append(tripulante_id)
                conn.commit()
                status, created, _, _ = _json_request(
                    opener,
                    base_url,
                    f"/api/v1/tripulantes/{tripulante_id}/files",
                    method="POST",
                    headers={"X-CSRFToken": _current_csrf(opener, base_url)},
                    json_payload={
                        "filename": "doc_file_v1.pdf",
                        "content_type": "application/pdf",
                        "arquivo_base64": _pdf_base64("file-v1"),
                        "tipo_documento": "cma",
                    },
                )
                _assert_status(status, {201}, label="tripulante_file_create")
                original_id = int(created["file"]["id"])
                cleanup_state.tripulante_file_ids.append(original_id)
                status, download_bytes, response_headers, _ = _request(
                    opener,
                    base_url,
                    f"/api/v1/tripulantes/{tripulante_id}/files/{original_id}?download=1",
                    headers={"Accept": "application/pdf"},
                )
                _assert_status(status, {200}, label="tripulante_file_download")
                if not response_headers.get("Content-Type", "").startswith("application/pdf"):
                    raise E2EFailure("tripulante_file_download:content_type_invalid")
                status, replaced, _, _ = _json_request(
                    opener,
                    base_url,
                    f"/api/v1/tripulantes/{tripulante_id}/files",
                    method="POST",
                    headers={"X-CSRFToken": _current_csrf(opener, base_url)},
                    json_payload={
                        "filename": "doc_file_v2.pdf",
                        "content_type": "application/pdf",
                        "arquivo_base64": _pdf_base64("file-v2"),
                        "tipo_documento": "cma",
                        "substitui_arquivo_id": original_id,
                    },
                )
                _assert_status(status, {201}, label="tripulante_file_replace")
                replaced_id = int(replaced["file"]["id"])
                cleanup_state.tripulante_file_ids.append(replaced_id)
                with conn.cursor() as cur:
                    cur.execute("SELECT status FROM tripulante_arquivos_pdf WHERE id = %s", (original_id,))
                    old_row = cur.fetchone()
                    cur.execute("SELECT status FROM tripulante_arquivos_pdf WHERE id = %s", (replaced_id,))
                    new_row = cur.fetchone()
                if old_row is None or str(old_row[0]) != "substituido":
                    raise E2EFailure("tripulante_file_replace:old_status_not_substituido")
                if new_row is None or str(new_row[0]) != "ativo":
                    raise E2EFailure("tripulante_file_replace:new_status_not_ativo")
                status, deleted, _, _ = _json_request(
                    opener,
                    base_url,
                    f"/api/v1/tripulantes/{tripulante_id}/files/{replaced_id}",
                    method="DELETE",
                    headers={"X-CSRFToken": _current_csrf(opener, base_url)},
                    json_payload={},
                )
                _assert_status(status, {200}, label="tripulante_file_delete")
                if str(deleted.get("code", "")) != "tripulante_file_deleted":
                    raise E2EFailure(f"tripulante_file_delete:unexpected_code:{deleted.get('code')}")
                with conn.cursor() as cur:
                    cur.execute("SELECT status FROM tripulante_arquivos_pdf WHERE id = %s", (replaced_id,))
                    removed = cur.fetchone()
                if removed is None or str(removed[0]) != "removido":
                    raise E2EFailure("tripulante_file_delete:status_not_removido")
                return f"tripulante_id={tripulante_id};download_bytes={len(download_bytes)}"

            _step(results, "tripulante_file_api_upload_download_replace_delete", file_flow_detail)

            def training_attachment_detail() -> str:
                tripulante_id = _create_tripulante(conn, name_prefix="E2E-INTEGR", base_name=base_name)
                equipamento_id = _create_equipamento(conn, nome=f"E2E-EQ-{uuid.uuid4().hex[:6]}")
                tipo_id = _create_tipo_treinamento(conn, nome=f"E2E-TIPO-{uuid.uuid4().hex[:6]}")
                treinamento_id = _create_treinamento(
                    conn,
                    tripulante_id=tripulante_id,
                    equipamento_id=equipamento_id,
                    tipo_id=tipo_id,
                )
                cleanup_state.tripulante_ids.append(tripulante_id)
                cleanup_state.equipamento_ids.append(equipamento_id)
                cleanup_state.tipo_ids.append(tipo_id)
                cleanup_state.treinamento_ids.append(treinamento_id)
                conn.commit()
                status, created, _, _ = _json_request(
                    opener,
                    base_url,
                    f"/api/v1/treinamentos/{treinamento_id}/attachments",
                    method="POST",
                    headers={"X-CSRFToken": _current_csrf(opener, base_url)},
                    json_payload={
                        "filename": "doc_treinamento.pdf",
                        "content_type": "application/pdf",
                        "arquivo_base64": _pdf_base64("training-v1"),
                    },
                )
                _assert_status(status, {201}, label="treinamento_attachment_create")
                attachment_id = int(created["attachment"]["id"])
                cleanup_state.treinamento_anexo_ids.append(attachment_id)
                status, html_bytes, response_headers, _ = _request(
                    opener,
                    base_url,
                    f"/tripulantes/{tripulante_id}/file",
                    headers={"Accept": "text/html"},
                )
                _assert_status(status, {200}, label="tripulante_file_tab")
                html = html_bytes.decode("utf-8", "ignore")
                if "doc_treinamento.pdf" not in html or "Treinamento" not in html:
                    raise E2EFailure("tripulante_file_tab:training_attachment_missing")
                status, attachment_bytes, attachment_headers, _ = _request(
                    opener,
                    base_url,
                    f"/tripulantes/{tripulante_id}/file/origem/treinamento/{attachment_id}?download=1",
                    headers={"Accept": "application/pdf"},
                )
                _assert_status(status, {200}, label="tripulante_file_training_download")
                if not attachment_headers.get("Content-Type", "").startswith("application/pdf"):
                    raise E2EFailure("tripulante_file_training_download:content_type_invalid")
                return f"tripulante_id={tripulante_id};attachment_bytes={len(attachment_bytes)}"

            _step(results, "training_attachment_visible_on_file_tab", training_attachment_detail)

            def photo_detail() -> str:
                tripulante_id = _create_tripulante(conn, name_prefix="E2E-PHOTO", base_name=base_name)
                cleanup_state.tripulante_ids.append(tripulante_id)
                conn.commit()
                status, created, _, _ = _json_request(
                    opener,
                    base_url,
                    f"/api/v1/tripulantes/{tripulante_id}/photo",
                    method="POST",
                    headers={"X-CSRFToken": _current_csrf(opener, base_url)},
                    json_payload={"foto_base64": _png_data_uri()},
                )
                _assert_status(status, {200}, label="tripulante_photo_create")
                if str(created.get("code", "")) != "tripulante_photo_saved":
                    raise E2EFailure(f"tripulante_photo_create:unexpected_code:{created.get('code')}")
                status, api_bytes, api_headers, _ = _request(
                    opener,
                    base_url,
                    f"/api/v1/tripulantes/{tripulante_id}/photo",
                    headers={"Accept": "image/png"},
                )
                _assert_status(status, {200}, label="tripulante_photo_api_get")
                if api_bytes != _png_bytes():
                    raise E2EFailure("tripulante_photo_api_get:payload_mismatch")
                status, ssr_bytes, ssr_headers, _ = _request(
                    opener,
                    base_url,
                    f"/tripulantes/{tripulante_id}/foto",
                    headers={"Accept": "image/png"},
                )
                _assert_status(status, {200}, label="tripulante_photo_ssr_get")
                if ssr_bytes != _png_bytes():
                    raise E2EFailure("tripulante_photo_ssr_get:payload_mismatch")
                status, deleted, _, _ = _json_request(
                    opener,
                    base_url,
                    f"/api/v1/tripulantes/{tripulante_id}/photo",
                    method="DELETE",
                    headers={"X-CSRFToken": _current_csrf(opener, base_url)},
                    json_payload={},
                )
                _assert_status(status, {200}, label="tripulante_photo_delete")
                if str(deleted.get("code", "")) != "tripulante_photo_deleted":
                    raise E2EFailure(f"tripulante_photo_delete:unexpected_code:{deleted.get('code')}")
                status, _, _, _ = _request(opener, base_url, f"/api/v1/tripulantes/{tripulante_id}/photo")
                if status != 404:
                    raise E2EFailure(f"tripulante_photo_missing:unexpected_status:{status}")
                return f"tripulante_id={tripulante_id};content_type={api_headers.get('Content-Type','')}"

            _step(results, "tripulante_photo_api_and_ssr_download", photo_detail)

            def invalid_pdf_detail() -> str:
                tripulante_id = _create_tripulante(conn, name_prefix="E2E-BADPDF", base_name=base_name)
                cleanup_state.tripulante_ids.append(tripulante_id)
                conn.commit()
                status, payload, _, _ = _json_request(
                    opener,
                    base_url,
                    f"/api/v1/tripulantes/{tripulante_id}/files",
                    method="POST",
                    headers={"X-CSRFToken": _current_csrf(opener, base_url)},
                    json_payload={
                        "filename": "nao_valido.pdf",
                        "content_type": "application/pdf",
                        "arquivo_base64": base64.b64encode(b"not_a_pdf").decode("ascii"),
                        "tipo_documento": "geral",
                    },
                )
                if status == 201:
                    raise E2EFailure("tripulante_invalid_pdf:unexpected_success")
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM tripulante_arquivos_pdf WHERE tripulante_id = %s", (tripulante_id,))
                    count = int(cur.fetchone()[0])
                if count != 0:
                    raise E2EFailure(f"tripulante_invalid_pdf:rows_present:{count}")
                return f"status={status};code={payload.get('code','')}"

            _step(results, "invalid_pdf_rejected_via_file_api", invalid_pdf_detail)

            def exports_detail() -> str:
                tripulante_id = _create_tripulante(conn, name_prefix="E2E-EXPORT", base_name=base_name)
                equipamento_id = _create_equipamento(conn, nome=f"E2E-EXPORT-EQ-{uuid.uuid4().hex[:6]}")
                tipo_id = _create_tipo_treinamento(conn, nome=f"E2E-EXPORT-TIPO-{uuid.uuid4().hex[:6]}")
                treinamento_id = _create_treinamento(
                    conn,
                    tripulante_id=tripulante_id,
                    equipamento_id=equipamento_id,
                    tipo_id=tipo_id,
                )
                cleanup_state.tripulante_ids.append(tripulante_id)
                cleanup_state.equipamento_ids.append(equipamento_id)
                cleanup_state.tipo_ids.append(tipo_id)
                cleanup_state.treinamento_ids.append(treinamento_id)
                conn.commit()
                tripulante_nome = _tripulante_nome(conn, tripulante_id)
                status, csv_bytes, csv_headers, _ = _request(
                    opener,
                    base_url,
                    f"/treinamentos/consolidado/export.csv?base={urllib.parse.quote(base_name)}&ordenacao=vencimento",
                    headers={"Accept": "text/csv"},
                )
                _assert_status(status, {200}, label="habilitacoes_csv_export")
                if "attachment;" not in (csv_headers.get("Content-Disposition", "") or ""):
                    raise E2EFailure("habilitacoes_csv_export:content_disposition_missing")
                csv_body = csv_bytes.decode("utf-8", "ignore")
                if "Tripulante;Base;Funcao/Cargo;Habilitacao;Data de vencimento;Dias restantes;Status" not in csv_body:
                    raise E2EFailure("habilitacoes_csv_export:header_missing")
                csv_rows = [line for line in csv_body.splitlines() if line.strip()]
                status, pdf_bytes, pdf_headers, _ = _request(
                    opener,
                    base_url,
                    f"/treinamentos/consolidado/export.pdf?base={urllib.parse.quote(base_name)}&ordenacao=vencimento",
                    headers={"Accept": "application/pdf"},
                )
                _assert_status(status, {200}, label="habilitacoes_pdf_export")
                if not pdf_bytes.startswith(b"%PDF"):
                    raise E2EFailure("habilitacoes_pdf_export:not_pdf")
                if pdf_headers.get("X-Document-Policy", "") != "habilitacoes_export_pdf":
                    raise E2EFailure("habilitacoes_pdf_export:policy_header_invalid")
                if pdf_headers.get("X-Document-Kind", "") != "pdf_export":
                    raise E2EFailure("habilitacoes_pdf_export:kind_header_invalid")
                return (
                    f"tripulante_visible={str(tripulante_nome in csv_body).lower()};"
                    f"csv_rows={len(csv_rows)};csv_bytes={len(csv_bytes)};pdf_bytes={len(pdf_bytes)}"
                )

            _step(results, "habilitacoes_exports_csv_pdf", exports_detail)

            def logout_detail() -> str:
                payload = _api_logout(opener, base_url)
                status, session_payload, _, _ = _json_request(opener, base_url, "/api/v1/session")
                _assert_status(status, {200}, label="session_state_after_logout")
                if bool(session_payload.get("authenticated")):
                    raise E2EFailure("session_state_after_logout:authenticated_true")
                return payload.get("message", "") or "logout_ok"

            _step(results, "api_logout_and_session_terminated", logout_detail)

    finally:
        try:
            with _db_connect() as cleanup_conn:
                _cleanup(cleanup_conn, cleanup_state)
        except Exception:
            pass

    finished_at = _utc_now()
    passed_steps = sum(1 for item in results if item.ok)
    payload = {
        "success": all(item.ok for item in results),
        "environment": "homolog",
        "base_url": base_url,
        "round_index": max(1, int(args.round_index)),
        "login": login,
        "started_at": started_at,
        "finished_at": finished_at,
        "passed_steps": passed_steps,
        "failed_steps": sum(1 for item in results if not item.ok),
        "steps": [
            {
                "name": item.name,
                "ok": item.ok,
                "duration_ms": item.duration_ms,
                "detail": item.detail,
            }
            for item in results
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
