from __future__ import annotations

import io
import json
import os
import re
import uuid
from base64 import b64decode

import psycopg2
import pytest
from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.constants import LOGIN_MAX_ATTEMPTS
from backend.src.controle_treinamentos.core.rate_limit import login_limiter

CSRF_RE = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
PNG_1X1_BASE64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="


def _required_env(name: str) -> str:
    value = (os.getenv(name, "") or "").strip()
    if not value:
        pytest.skip(f"{name} não configurada para E2E de homologação")
    return value


def _extract_csrf_token(html: str) -> str:
    match = CSRF_RE.search(html)
    if not match:
        raise AssertionError("Token CSRF não encontrado na página.")
    return match.group(1)


def _pdf_bytes(label: str) -> bytes:
    body = f"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Producer ({label}) >>\nendobj\n%%EOF"
    return body.encode("utf-8")


def _png_bytes() -> bytes:
    return b64decode(PNG_1X1_BASE64)


def _png_data_uri() -> str:
    return f"data:image/png;base64,{PNG_1X1_BASE64}"


def _db_connect():
    return psycopg2.connect(_required_env("E2E_DATABASE_URL"))


def _ensure_e2e_user():
    login = _required_env("E2E_LOGIN")
    password = _required_env("E2E_PASSWORD")
    email = f"{login}@e2e.test"
    password_hash = generate_password_hash(password, method="pbkdf2:sha256")
    with _db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO usuarios (nome, login, email, senha_hash, perfil, ativo, permissao_modulos_json)
                VALUES (%s, %s, %s, %s, %s, 1, %s)
                ON CONFLICT (login) DO UPDATE
                SET
                    email = EXCLUDED.email,
                    senha_hash = EXCLUDED.senha_hash,
                    ativo = 1
                """,
                ("E2E Release Bot", login, email, password_hash, "gestora", "[]"),
            )
        conn.commit()


def _ensure_e2e_schema_compat():
    with _db_connect() as conn:
        with conn.cursor() as cur:
            # Compatibilidade para bancos de homologação ainda não migrados.
            cur.execute(
                "ALTER TABLE tripulantes ADD COLUMN IF NOT EXISTS possui_foto BOOLEAN NOT NULL DEFAULT FALSE"
            )
        conn.commit()


def _random_digits(size: int) -> str:
    return "".join(ch for ch in uuid.uuid4().hex if ch.isdigit())[:size].ljust(size, "7")


def _create_tripulante(conn, *, name_prefix: str) -> int:
    cpf = _random_digits(11)
    anac = f"ANAC-{uuid.uuid4().hex[:8].upper()}"
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
            (nome, cpf, anac, f"{nome.lower()}@e2e.test", "11999999999", "E2E"),
        )
        return int(cur.fetchone()[0])


def _create_equipamento(conn, *, nome: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO equipamentos (nome, tipo, ativo) VALUES (%s, %s, 1) RETURNING id",
            (nome, "E2E"),
        )
        return int(cur.fetchone()[0])


def _create_tipo_treinamento(conn, *, nome: str, periodicidade: int = 12) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tipos_treinamento (nome, periodicidade_meses, exige_equipamento, ativo)
            VALUES (%s, %s, 1, 1)
            RETURNING id
            """,
            (nome, periodicidade),
        )
        return int(cur.fetchone()[0])


def _create_treinamento(conn, *, tripulante_id: int, equipamento_id: int, tipo_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO treinamentos (tripulante_id, equipamento_id, tipo_treinamento_id, data_realizacao, data_vencimento, observacao)
            VALUES (%s, %s, %s, CURRENT_DATE, CURRENT_DATE + INTERVAL '365 days', 'E2E')
            RETURNING id
            """,
            (tripulante_id, equipamento_id, tipo_id),
        )
        return int(cur.fetchone()[0])


def _tripulante_name(conn, tripulante_id: int) -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT nome FROM tripulantes WHERE id = %s", (tripulante_id,))
        row = cur.fetchone()
        assert row is not None
        return str(row[0])


def _cleanup_entities(
    conn,
    *,
    user_login: str | None = None,
    tripulante_ids: list[int] | None = None,
    treinamento_ids: list[int] | None = None,
    equipamento_ids: list[int] | None = None,
    tipo_ids: list[int] | None = None,
):
    with conn.cursor() as cur:
        for treinamento_id in (treinamento_ids or []):
            cur.execute("DELETE FROM treinamento_anexos_pdf WHERE treinamento_id = %s", (treinamento_id,))
            cur.execute("DELETE FROM treinamentos WHERE id = %s", (treinamento_id,))
        for tripulante_id in (tripulante_ids or []):
            cur.execute("DELETE FROM tripulante_arquivos_pdf WHERE tripulante_id = %s", (tripulante_id,))
            cur.execute("DELETE FROM tripulantes WHERE id = %s", (tripulante_id,))
        for equipamento_id in (equipamento_ids or []):
            cur.execute("DELETE FROM equipamentos WHERE id = %s", (equipamento_id,))
        for tipo_id in (tipo_ids or []):
            cur.execute("DELETE FROM tipos_treinamento WHERE id = %s", (tipo_id,))
        if user_login:
            cur.execute("DELETE FROM usuarios WHERE login = %s", (user_login,))
    conn.commit()


@pytest.fixture
def e2e_client(monkeypatch):
    db_url = _required_env("E2E_DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("SECRET_KEY", "e2e-secret")
    _ensure_e2e_schema_compat()
    _ensure_e2e_user()
    app = create_app()
    return app.test_client(), app


def _login(client, *, login: str | None = None, password: str | None = None):
    login_value = login or _required_env("E2E_LOGIN")
    password_value = password or _required_env("E2E_PASSWORD")
    # Evita falso negativo em rodadas E2E longas por rate-limit local compartilhado.
    login_limiter.reset("127.0.0.1")
    login_limiter.reset("unknown")
    login_limiter.reset(f"127.0.0.1:{login_value.strip().lower()}")
    login_limiter.reset(f"unknown:{login_value.strip().lower()}")
    page = client.get("/login")
    assert page.status_code == 200
    csrf = _extract_csrf_token(page.get_data(as_text=True))

    resp = client.post(
        "/login",
        data={
            "csrf_token": csrf,
            "login": login_value,
            "senha": password_value,
        },
        follow_redirects=False,
    )
    assert resp.status_code in {302, 303}
    return resp


def _api_csrf(client) -> str:
    response = client.get("/api/v1/session")
    assert response.status_code == 200
    token = response.get_json()["csrf_token"]
    assert token
    return token


def _expire_authenticated_session(client):
    with client.session_transaction() as sess:
        sess.clear()
    # O app usa login_user(..., remember=True). Sem limpar esse cookie, o usuário
    # pode ser reautenticado automaticamente no próximo request.
    remember_names = {
        "remember_token",  # nome padrão do Flask-Login
        "controle_treinamentos_remember",  # default atual do app
        (os.getenv("REMEMBER_COOKIE_NAME", "") or "").strip(),
    }
    remember_names = {name for name in remember_names if name}
    for domain in ("localhost", "127.0.0.1"):
        for cookie_name in remember_names:
            try:
                client.set_cookie(domain, cookie_name, "", expires=0)
            except TypeError:
                # Compatibilidade com assinatura alternativa de set_cookie em versões
                # diferentes do Werkzeug/Flask test client.
                client.set_cookie(cookie_name, "", domain=domain, expires=0)


@pytest.mark.e2e
def test_e2e_login_invalid_shows_expected_feedback(e2e_client):
    client, _app = e2e_client
    login_value = _required_env("E2E_LOGIN")
    page = client.get("/login")
    assert page.status_code == 200
    csrf = _extract_csrf_token(page.get_data(as_text=True))

    response = client.post(
        "/login",
        data={
            "csrf_token": csrf,
            "login": login_value,
            "senha": "senha-incorreta-e2e",
        },
        follow_redirects=False,
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Login inválido." in body


@pytest.mark.e2e
def test_e2e_login_logout(e2e_client):
    client, _app = e2e_client
    _login(client)

    dash = client.get("/dashboard")
    assert dash.status_code == 200

    csrf = _extract_csrf_token(dash.get_data(as_text=True))
    logout = client.post("/logout", data={"csrf_token": csrf}, follow_redirects=False)
    assert logout.status_code in {302, 303}


@pytest.mark.e2e
def test_e2e_login_redirect_next_and_session_reload(e2e_client):
    client, _app = e2e_client

    protected = client.get("/tripulantes?page=2", follow_redirects=False)
    assert protected.status_code in {302, 303}
    login_url = protected.headers.get("Location", "") or ""
    assert "/login" in login_url
    assert "next=" in login_url

    login_page = client.get(login_url)
    assert login_page.status_code == 200
    csrf = _extract_csrf_token(login_page.get_data(as_text=True))

    post_login = client.post(
        "/login",
        data={
            "csrf_token": csrf,
            "login": _required_env("E2E_LOGIN"),
            "senha": _required_env("E2E_PASSWORD"),
            "next": "/tripulantes?page=2",
        },
        follow_redirects=False,
    )
    assert post_login.status_code in {302, 303}
    redirected = post_login.headers.get("Location", "") or ""
    assert redirected.endswith("/tripulantes?page=2")

    first = client.get("/dashboard")
    second = client.get("/dashboard")
    assert first.status_code == 200
    assert second.status_code == 200


@pytest.mark.e2e
def test_e2e_multiple_tabs_keep_same_authenticated_session(e2e_client):
    client, app = e2e_client
    _login(client)

    first_tab = client.get("/dashboard")
    assert first_tab.status_code == 200

    second_client = app.test_client()
    for cookie in client._cookies.values():
        try:
            second_client.set_cookie(
                key=cookie.key,
                value=cookie.value,
                domain=cookie.domain,
                path=cookie.path,
            )
        except TypeError:
            # Compatibilidade com assinatura antiga do Werkzeug.
            second_client.set_cookie(
                cookie.domain,
                cookie.key,
                cookie.value,
                path=cookie.path,
            )

    second_tab = second_client.get("/tripulantes")
    assert second_tab.status_code == 200

    back_to_first = client.get("/treinamentos")
    assert back_to_first.status_code == 200


@pytest.mark.e2e
def test_e2e_mobile_user_agent_authenticated_flow(e2e_client):
    client, _app = e2e_client
    _login(client)

    mobile_headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    }

    html_mobile = client.get("/dashboard", headers={"User-Agent": mobile_headers["User-Agent"]})
    assert html_mobile.status_code == 200

    api_mobile = client.get("/bases/api/dados?status=ativo", headers=mobile_headers)
    assert api_mobile.status_code == 200
    assert api_mobile.content_type.startswith("application/json")


@pytest.mark.e2e
def test_e2e_short_inactivity_does_not_logout_user(e2e_client):
    client, _app = e2e_client
    _login(client)

    first = client.get("/dashboard")
    assert first.status_code == 200

    # Simula retorno após curta inatividade.
    import time
    time.sleep(2)

    resumed = client.get("/tripulantes")
    assert resumed.status_code == 200


@pytest.mark.e2e
def test_e2e_equipamento_crud(e2e_client):
    client, app = e2e_client
    _login(client)

    form = client.get("/equipamentos/novo")
    if form.status_code == 403:
        pytest.skip("Usuário E2E sem permissão de equipamentos:create")
    assert form.status_code == 200

    csrf = _extract_csrf_token(form.get_data(as_text=True))
    nome = f"E2E-EQUIP-{uuid.uuid4().hex[:10]}"

    create_resp = client.post(
        "/equipamentos/novo",
        data={
            "csrf_token": csrf,
            "nome": nome,
            "tipo": "E2E",
            "ativo": "1",
        },
        follow_redirects=False,
    )
    assert create_resp.status_code in {302, 303}

    with app.app_context():
        db = psycopg2.connect(_required_env("E2E_DATABASE_URL"))
        try:
            with db.cursor() as cur:
                cur.execute("SELECT id FROM equipamentos WHERE nome = %s ORDER BY id DESC LIMIT 1", (nome,))
                row = cur.fetchone()
                assert row is not None
                equipamento_id = int(row[0])
        finally:
            db.close()

    list_page = client.get("/equipamentos")
    assert list_page.status_code == 200
    delete_csrf = _extract_csrf_token(list_page.get_data(as_text=True))

    delete_resp = client.post(
        f"/equipamentos/{equipamento_id}/excluir",
        data={"csrf_token": delete_csrf},
        follow_redirects=False,
    )
    assert delete_resp.status_code in {302, 303}


@pytest.mark.e2e
def test_e2e_manual_backup_enqueues_job(e2e_client):
    client, app = e2e_client
    _login(client)

    page = client.get("/backups")
    if page.status_code == 403:
        pytest.skip("Usuário E2E sem permissão de backups:run")
    assert page.status_code == 200

    csrf = _extract_csrf_token(page.get_data(as_text=True))
    post = client.post("/backups/executar", data={"csrf_token": csrf}, follow_redirects=False)
    assert post.status_code in {302, 303}

    with app.app_context():
        db = psycopg2.connect(_required_env("E2E_DATABASE_URL"))
        try:
            with db.cursor() as cur:
                cur.execute(
                    """
                    SELECT status
                    FROM background_jobs
                    WHERE job_type = 'run_backup'
                    ORDER BY id DESC
                    LIMIT 1
                    """
                )
                row = cur.fetchone()
                assert row is not None
                assert row[0] in {"queued", "running", "succeeded"}
        finally:
            db.close()


@pytest.mark.e2e
def test_e2e_file_tab_end_to_end_with_replace_and_delete(e2e_client):
    client, _app = e2e_client
    _login(client)

    db = _db_connect()
    tripulante_id = _create_tripulante(db, name_prefix="E2E-FILE")
    db.commit()

    try:
        tab = client.get(f"/tripulantes/{tripulante_id}/file")
        assert tab.status_code == 200
        csrf = _extract_csrf_token(tab.get_data(as_text=True))

        upload = client.post(
            f"/tripulantes/{tripulante_id}/file/upload",
            data={
                "csrf_token": csrf,
                "tipo_documento": "cma",
                "arquivos_pdf": (io.BytesIO(_pdf_bytes("file-v1")), "doc_file_v1.pdf"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert upload.status_code in {302, 303}

        with db.cursor() as cur:
            cur.execute(
                """
                SELECT id, status
                FROM tripulante_arquivos_pdf
                WHERE tripulante_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (tripulante_id,),
            )
            row = cur.fetchone()
            assert row is not None
            original_id = int(row[0])
            assert row[1] == "ativo"

        download = client.get(f"/tripulantes/{tripulante_id}/file/origem/tripulante_file/{original_id}?download=1")
        assert download.status_code == 200
        assert download.mimetype == "application/pdf"

        replace = client.post(
            f"/tripulantes/{tripulante_id}/file/{original_id}/substituir",
            data={
                "csrf_token": csrf,
                "tipo_documento": "cma",
                "arquivo_pdf": (io.BytesIO(_pdf_bytes("file-v2")), "doc_file_v2.pdf"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert replace.status_code in {302, 303}

        with db.cursor() as cur:
            cur.execute(
                """
                SELECT id, status
                FROM tripulante_arquivos_pdf
                WHERE tripulante_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (tripulante_id,),
            )
            row = cur.fetchone()
            assert row is not None
            replaced_id = int(row[0])
            assert row[1] == "ativo"
            assert replaced_id != original_id

            cur.execute("SELECT status FROM tripulante_arquivos_pdf WHERE id = %s", (original_id,))
            old_row = cur.fetchone()
            assert old_row is not None
            assert old_row[0] == "substituido"

        remove = client.post(
            f"/tripulantes/{tripulante_id}/file/{replaced_id}/excluir",
            data={"csrf_token": csrf},
            follow_redirects=False,
        )
        assert remove.status_code in {302, 303}

        with db.cursor() as cur:
            cur.execute("SELECT status FROM tripulante_arquivos_pdf WHERE id = %s", (replaced_id,))
            removed = cur.fetchone()
            assert removed is not None
            assert removed[0] == "removido"
    finally:
        _cleanup_entities(db, tripulante_ids=[tripulante_id])
        db.close()


@pytest.mark.e2e
def test_e2e_training_attachment_is_visible_on_file_tab(e2e_client):
    client, _app = e2e_client
    _login(client)

    db = _db_connect()
    tripulante_id = _create_tripulante(db, name_prefix="E2E-INTEGR")
    equipamento_id = _create_equipamento(db, nome=f"E2E-EQ-{uuid.uuid4().hex[:6]}")
    tipo_id = _create_tipo_treinamento(db, nome=f"E2E-TT-{uuid.uuid4().hex[:6]}")
    treinamento_id = _create_treinamento(
        db,
        tripulante_id=tripulante_id,
        equipamento_id=equipamento_id,
        tipo_id=tipo_id,
    )
    db.commit()

    try:
        edit = client.get(f"/treinamentos/{treinamento_id}/editar")
        assert edit.status_code == 200
        csrf = _extract_csrf_token(edit.get_data(as_text=True))

        upload = client.post(
            f"/treinamentos/{treinamento_id}/anexos/upload",
            data={
                "csrf_token": csrf,
                "arquivo_pdf": (io.BytesIO(_pdf_bytes("trein-v1")), "doc_treinamento.pdf"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert upload.status_code in {302, 303}

        with db.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM treinamento_anexos_pdf
                WHERE treinamento_id = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (treinamento_id,),
            )
            row = cur.fetchone()
            assert row is not None
            anexo_id = int(row[0])

        file_tab = client.get(f"/tripulantes/{tripulante_id}/file")
        assert file_tab.status_code == 200
        html = file_tab.get_data(as_text=True)
        assert "doc_treinamento.pdf" in html
        assert "Treinamento" in html

        consolidated_download = client.get(
            f"/tripulantes/{tripulante_id}/file/origem/treinamento/{anexo_id}?download=1"
        )
        assert consolidated_download.status_code == 200
        assert consolidated_download.mimetype == "application/pdf"
    finally:
        _cleanup_entities(
            db,
            tripulante_ids=[tripulante_id],
            treinamento_ids=[treinamento_id],
            equipamento_ids=[equipamento_id],
            tipo_ids=[tipo_id],
        )
        db.close()


@pytest.mark.e2e
def test_e2e_tripulante_photo_api_and_ssr_download_flow(e2e_client):
    client, _app = e2e_client
    _login(client)

    db = _db_connect()
    tripulante_id = _create_tripulante(db, name_prefix="E2E-PHOTO")
    db.commit()

    try:
        csrf = _api_csrf(client)
        upload = client.post(
            f"/api/v1/tripulantes/{tripulante_id}/photo",
            json={"foto_base64": _png_data_uri()},
            headers={"X-CSRFToken": csrf, "Accept": "application/json"},
            follow_redirects=False,
        )
        if upload.status_code == 403:
            pytest.skip("Usuário E2E sem permissão de tripulantes:edit")
        assert upload.status_code == 200
        payload = upload.get_json()
        assert payload["code"] == "tripulante_photo_saved"
        assert payload["photo"]["has_photo"] is True

        api_photo = client.get(f"/api/v1/tripulantes/{tripulante_id}/photo")
        assert api_photo.status_code == 200
        assert api_photo.mimetype == "image/png"
        assert api_photo.get_data() == _png_bytes()

        ssr_photo = client.get(f"/tripulantes/{tripulante_id}/foto")
        assert ssr_photo.status_code == 200
        assert ssr_photo.mimetype == "image/png"
        assert ssr_photo.get_data() == _png_bytes()

        delete = client.delete(
            f"/api/v1/tripulantes/{tripulante_id}/photo",
            headers={"X-CSRFToken": _api_csrf(client), "Accept": "application/json"},
            follow_redirects=False,
        )
        assert delete.status_code == 200
        assert delete.get_json()["code"] == "tripulante_photo_deleted"

        missing = client.get(f"/api/v1/tripulantes/{tripulante_id}/photo")
        assert missing.status_code == 404
    finally:
        _cleanup_entities(db, tripulante_ids=[tripulante_id])
        db.close()


@pytest.mark.e2e
def test_e2e_file_upload_rejects_invalid_pdf(e2e_client):
    client, _app = e2e_client
    _login(client)

    db = _db_connect()
    tripulante_id = _create_tripulante(db, name_prefix="E2E-BADPDF")
    db.commit()

    try:
        tab = client.get(f"/tripulantes/{tripulante_id}/file")
        assert tab.status_code == 200
        csrf = _extract_csrf_token(tab.get_data(as_text=True))

        bad_upload = client.post(
            f"/tripulantes/{tripulante_id}/file/upload",
            data={
                "csrf_token": csrf,
                "tipo_documento": "geral",
                "arquivos_pdf": (io.BytesIO(b"not_a_pdf"), "nao_valido.pdf"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert bad_upload.status_code in {302, 303}

        with db.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM tripulante_arquivos_pdf WHERE tripulante_id = %s",
                (tripulante_id,),
            )
            count = int(cur.fetchone()[0])
            assert count == 0
    finally:
        _cleanup_entities(db, tripulante_ids=[tripulante_id])
        db.close()


@pytest.mark.e2e
def test_e2e_permission_profile_real_forbidden_on_admin_users(e2e_client):
    client, _app = e2e_client
    db = _db_connect()

    restricted_login = f"e2e_restricted_{uuid.uuid4().hex[:8]}"
    restricted_password = "E2E-Restricted-123!"
    permission_json = json.dumps(["dashboard:view"])
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO usuarios (nome, login, email, senha_hash, perfil, ativo, permissao_modulos_json)
            VALUES (%s, %s, %s, %s, 'operador', 1, %s)
            """,
            (
                "E2E Restricted",
                restricted_login,
                f"{restricted_login}@e2e.test",
                generate_password_hash(restricted_password, method="pbkdf2:sha256"),
                permission_json,
            ),
        )
    db.commit()

    try:
        _login(client, login=restricted_login, password=restricted_password)
        dashboard = client.get("/dashboard")
        assert dashboard.status_code == 200

        forbidden = client.get("/usuarios", follow_redirects=False)
        assert forbidden.status_code == 403
        assert (forbidden.headers.get("Location", "") or "") == ""
        assert "Acesso negado" in forbidden.get_data(as_text=True)
        forbidden_json = client.get(
            "/usuarios",
            headers={"Accept": "application/json"},
            follow_redirects=False,
        )
        assert forbidden_json.status_code == 403
    finally:
        _cleanup_entities(db, user_login=restricted_login)
        db.close()


@pytest.mark.e2e
def test_e2e_limited_user_without_dashboard_permission_redirects_to_allowed_landing(e2e_client):
    client, _app = e2e_client
    db = _db_connect()

    restricted_login = f"e2e_landing_{uuid.uuid4().hex[:8]}"
    restricted_password = "E2E-Landing-123!"
    permission_json = json.dumps(["tripulantes:view"])
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO usuarios (nome, login, email, senha_hash, perfil, ativo, permissao_modulos_json)
            VALUES (%s, %s, %s, %s, 'operador', 1, %s)
            """,
            (
                "E2E Landing Restricted",
                restricted_login,
                f"{restricted_login}@e2e.test",
                generate_password_hash(restricted_password, method="pbkdf2:sha256"),
                permission_json,
            ),
        )
    db.commit()

    try:
        login_resp = _login(client, login=restricted_login, password=restricted_password)
        location = (login_resp.headers.get("Location", "") or "").strip()
        assert "/tripulantes" in location
    finally:
        _cleanup_entities(db, user_login=restricted_login)
        db.close()


@pytest.mark.e2e
def test_e2e_session_expired_redirects_to_login(e2e_client):
    client, _app = e2e_client
    _login(client)
    _expire_authenticated_session(client)

    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code in {302, 303}
    assert "/login" in (response.headers.get("Location", "") or "")


@pytest.mark.e2e
def test_e2e_programmatic_protected_routes_without_session_return_json_401(e2e_client):
    client, _app = e2e_client

    html_route = client.get("/dashboard", follow_redirects=False)
    assert html_route.status_code in {302, 303}
    assert "/login" in (html_route.headers.get("Location", "") or "")

    programmatic = client.get(
        "/bases/api/dados",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )
    assert programmatic.status_code == 401
    assert programmatic.content_type.startswith("application/json")
    payload = programmatic.get_json()
    assert payload["code"] == "auth_required"


@pytest.mark.e2e
def test_e2e_session_expired_on_programmatic_route_returns_json_401(e2e_client):
    client, _app = e2e_client
    _login(client)
    _expire_authenticated_session(client)

    response = client.get(
        "/bases/api/dados",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )
    assert response.status_code == 401
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["code"] == "auth_required"


@pytest.mark.e2e
def test_e2e_login_rate_limit_on_fast_retries(e2e_client):
    client, _app = e2e_client
    login_value = _required_env("E2E_LOGIN")
    rate_key = f"127.0.0.1:{login_value.strip().lower()}"
    login_limiter.reset(rate_key)

    limited = False
    for _ in range(LOGIN_MAX_ATTEMPTS + 2):
        page = client.get("/login")
        csrf = _extract_csrf_token(page.get_data(as_text=True))
        response = client.post(
            "/login",
            data={
                "csrf_token": csrf,
                "login": login_value,
                "senha": "senha-incorreta-e2e",
            },
            follow_redirects=False,
        )
        if response.status_code == 429:
            limited = True
            break
    assert limited is True


@pytest.mark.e2e
def test_e2e_login_csrf_error_contract(e2e_client):
    client, _app = e2e_client
    response = client.post(
        "/api/v1/session/login",
        json={
            "login": _required_env("E2E_LOGIN"),
            "senha": _required_env("E2E_PASSWORD"),
        },
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["code"] == "csrf_error"


@pytest.mark.e2e
def test_e2e_dashboard_listings_filters_and_programmatic_endpoints(e2e_client):
    client, _app = e2e_client
    _login(client)

    pages = [
        "/dashboard",
        "/tripulantes?nome=e2e",
        "/treinamentos?status=vencido&periodo=30",
        "/treinamentos/consolidado?ordenacao=criticidade",
    ]
    for path in pages:
        resp = client.get(path)
        assert resp.status_code == 200

    programmatic = [
        "/bases/api/dados?status=ativo",
    ]
    for path in programmatic:
        resp = client.get(path)
        assert resp.status_code == 200
        assert resp.content_type.startswith("application/json")


@pytest.mark.e2e
def test_e2e_habilitacoes_exports_generate_csv_and_pdf(e2e_client):
    client, _app = e2e_client
    _login(client)

    db = _db_connect()
    tripulante_id = _create_tripulante(db, name_prefix="E2E-EXPORT")
    equipamento_id = _create_equipamento(db, nome=f"E2E-EXPORT-EQ-{uuid.uuid4().hex[:6]}")
    tipo_id = _create_tipo_treinamento(db, nome=f"E2E-EXPORT-TT-{uuid.uuid4().hex[:6]}")
    treinamento_id = _create_treinamento(
        db,
        tripulante_id=tripulante_id,
        equipamento_id=equipamento_id,
        tipo_id=tipo_id,
    )
    tripulante_nome = _tripulante_name(db, tripulante_id)
    db.commit()

    try:
        csv_export = client.get(
            "/treinamentos/consolidado/export.csv?base=E2E&ordenacao=vencimento",
            follow_redirects=False,
        )
        if csv_export.status_code == 403:
            pytest.skip("Usuário E2E sem permissão de relatorio_habilitacoes:view")
        assert csv_export.status_code == 200
        assert csv_export.content_type.startswith("text/csv")
        assert "attachment;" in (csv_export.headers.get("Content-Disposition", "") or "")
        csv_body = csv_export.get_data(as_text=True)
        assert "Tripulante;Base;Funcao/Cargo;Habilitacao;Data de vencimento;Dias restantes;Status" in csv_body
        assert tripulante_nome in csv_body

        pdf_export = client.get(
            "/treinamentos/consolidado/export.pdf?base=E2E&ordenacao=vencimento",
            follow_redirects=False,
        )
        assert pdf_export.status_code == 200
        assert pdf_export.mimetype == "application/pdf"
        assert pdf_export.get_data().startswith(b"%PDF")
        assert "attachment;" in (pdf_export.headers.get("Content-Disposition", "") or "")
        assert pdf_export.headers.get("X-Document-Policy") == "habilitacoes_export_pdf"
        assert pdf_export.headers.get("X-Document-Kind") == "pdf_export"
    finally:
        _cleanup_entities(
            db,
            tripulante_ids=[tripulante_id],
            treinamento_ids=[treinamento_id],
            equipamento_ids=[equipamento_id],
            tipo_ids=[tipo_id],
        )
        db.close()
