from __future__ import annotations

import time

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.blueprints.auth import routes as auth_routes


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


class _EmptyCursor:
    def fetchone(self):
        return None


class _EmptyDB:
    def execute(self, _query, _params):
        return _EmptyCursor()


def _make_user_row(*, user_id: int = 11):
    return {
        "id": user_id,
        "nome": "Operador API",
        "login": "operador_api",
        "email": "operador.api@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": '["dashboard:view","tripulantes:view"]',
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def test_api_session_state_unauthenticated_exposes_contract():
    app = create_app()
    client = app.test_client()

    response = client.get("/api/v1/session")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "session_state_ok"
    assert payload["authenticated"] is False
    assert payload["session"]["state"] == "anonymous"
    assert payload["session"]["backend_verified"] is False
    assert payload["user"] is None
    assert payload["capabilities"] is None
    assert isinstance(payload["csrf_token"], str)
    assert payload["csrf_token"]


def test_api_me_requires_authenticated_session():
    app = create_app()
    client = app.test_client()

    response = client.get("/api/v1/me")

    assert response.status_code == 401
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["code"] == "auth_required"


def test_api_session_login_accepts_json_and_returns_identity_and_capabilities(monkeypatch):
    app = create_app()
    client = app.test_client()
    row = _make_user_row()
    fake_db = _SingleUserDB(row)

    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    session_probe = client.get("/api/v1/session")
    csrf_token = session_probe.get_json()["csrf_token"]

    response = client.post(
        "/api/v1/session/login",
        json={"login": "operador_api", "senha": "secret", "remember": True},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "auth_ok"
    assert payload["authenticated"] is True
    assert payload["session"]["state"] == "authenticated"
    assert payload["session"]["mode"] == "permanent"
    assert payload["session"]["remember"] is True
    assert payload["session"]["permanent"] is True
    assert payload["session"]["backend_verified"] is True
    assert payload["user"]["login"] == "operador_api"
    assert "dashboard:view" in payload["capabilities"]["granted_permissions"]
    assert payload["capabilities"]["landing_url"].startswith("/")

    session_state = client.get("/api/v1/session")
    session_payload = session_state.get_json()
    assert session_payload["authenticated"] is True
    assert session_payload["session"]["state"] == "authenticated"
    assert session_payload["session"]["remember"] is True
    assert session_payload["user"]["login"] == "operador_api"


def test_api_session_login_invalid_credentials_stays_json_with_html_accept(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: _EmptyDB())

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "nao_existe", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token, "Accept": "text/html"},
        follow_redirects=False,
    )

    assert response.status_code == 401
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == 401
    assert payload["code"] == "auth_invalid_credentials"


def test_api_session_login_without_remember_uses_browser_session_and_clears_stale_remember(monkeypatch):
    app = create_app()
    client = app.test_client()
    row = _make_user_row(user_id=15)
    fake_db = _SingleUserDB(row)

    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "operador_api", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["session"]["mode"] == "browser"
    assert payload["session"]["remember"] is False
    assert payload["session"]["permanent"] is False
    with client.session_transaction() as sess:
        assert sess.get("auth_session_mode") == "browser"
        assert sess.get("auth_session_remember") is False
        assert sess.permanent is False
        assert sess.get("_user_id") == "15"


def test_api_session_login_does_not_delegate_to_html_login_handler(monkeypatch):
    app = create_app()
    client = app.test_client()
    row = _make_user_row(user_id=14)
    fake_db = _SingleUserDB(row)

    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    def _html_login_should_not_run():
        raise AssertionError("/api/v1/session/login delegated to the SSR login handler")

    monkeypatch.setattr(auth_routes, "login", _html_login_should_not_run)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/login",
        json={"login": "operador_api", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token, "Accept": "text/html"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "auth_ok"


def test_html_login_invalid_credentials_ignores_programmatic_accept_and_keeps_html_contract(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: _EmptyDB())

    page = client.get("/login")
    html = page.get_data(as_text=True)
    marker = 'name="csrf_token" value="'
    csrf = html.split(marker, 1)[1].split('"', 1)[0]

    response = client.post(
        "/login",
        data={"csrf_token": csrf, "login": "nao_existe", "senha": "secret"},
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.content_type.startswith("text/html")
    assert response.get_json(silent=True) is None


def test_api_capabilities_returns_grouped_permissions_for_authenticated_user(monkeypatch):
    app = create_app()
    client = app.test_client()
    row = _make_user_row(user_id=12)
    fake_db = _SingleUserDB(row)

    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    login_response = client.post(
        "/api/v1/session/login",
        json={"login": "operador_api", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert login_response.status_code == 200

    response = client.get("/api/v1/capabilities")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "capabilities_ok"
    groups = payload["capabilities"]["groups"]
    assert groups
    dashboards_group = next(group for group in groups if group["key"] == "dashboards")
    assert any(item["key"] == "dashboard:view" and item["granted"] is True for item in dashboards_group["items"])


def test_api_session_logout_clears_authenticated_session(monkeypatch):
    app = create_app()
    client = app.test_client()
    row = _make_user_row(user_id=13)
    fake_db = _SingleUserDB(row)

    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    csrf_token = client.get("/api/v1/session").get_json()["csrf_token"]
    login_response = client.post(
        "/api/v1/session/login",
        json={"login": "operador_api", "senha": "secret"},
        headers={"X-CSRFToken": csrf_token},
        follow_redirects=False,
    )
    assert login_response.status_code == 200

    logout_csrf = client.get("/api/v1/session").get_json()["csrf_token"]
    response = client.post(
        "/api/v1/session/logout",
        headers={"X-CSRFToken": logout_csrf},
        follow_redirects=False,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "logout_ok"
    assert payload["authenticated"] is False

    session_state = client.get("/api/v1/session")
    session_payload = session_state.get_json()
    assert session_payload["authenticated"] is False


def test_api_session_logout_is_idempotent_for_expired_session():
    app = create_app()
    client = app.test_client()

    response = client.post("/api/v1/session/logout", follow_redirects=False)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "logout_ok"
    assert payload["authenticated"] is False


def test_api_session_state_clears_cookie_with_backend_invalid_session(monkeypatch):
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr("src.app.models.get_db", lambda: _EmptyDB())
    with client.session_transaction() as sess:
        sess["_user_id"] = "404"
        sess["_fresh"] = True
        sess["auth_session_created_at"] = int(time.time())
        sess["auth_session_last_seen_at"] = int(time.time())
        sess["auth_session_expires_at"] = int(time.time()) + 3600
        sess["auth_session_mode"] = "browser"
        sess["auth_session_remember"] = False

    response = client.get("/api/v1/session", follow_redirects=False)

    assert response.status_code == 401
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["code"] == "auth_session_invalid"
    with client.session_transaction() as sess:
        assert sess.get("_user_id") is None
        assert sess.get("auth_session_expires_at") is None


def test_api_session_state_clears_locally_expired_session_before_backend_validation(monkeypatch):
    app = create_app()
    client = app.test_client()
    row = _make_user_row(user_id=16)
    fake_db = _SingleUserDB(row)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    with client.session_transaction() as sess:
        sess["_user_id"] = "16"
        sess["_fresh"] = True
        sess["auth_session_created_at"] = int(time.time()) - 7200
        sess["auth_session_last_seen_at"] = int(time.time()) - 7200
        sess["auth_session_expires_at"] = int(time.time()) - 1
        sess["auth_session_mode"] = "browser"
        sess["auth_session_remember"] = False

    response = client.get("/api/v1/session", follow_redirects=False)

    assert response.status_code == 401
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["code"] == "auth_session_expired"
    with client.session_transaction() as sess:
        assert sess.get("_user_id") is None
        assert sess.get("auth_session_expires_at") is None


def test_api_session_state_rejects_snapshot_as_backend_verified_truth(monkeypatch):
    app = create_app()
    client = app.test_client()

    def _boom():
        raise RuntimeError("temporary_db_unavailable")

    monkeypatch.setattr("src.app.models.get_db", _boom)
    with client.session_transaction() as sess:
        sess["_user_id"] = "17"
        sess["_fresh"] = True
        sess["auth_session_created_at"] = int(time.time())
        sess["auth_session_last_seen_at"] = int(time.time())
        sess["auth_session_expires_at"] = int(time.time()) + 3600
        sess["auth_session_mode"] = "browser"
        sess["auth_session_remember"] = False
        sess["auth_user_snapshot"] = {
            "id": "17",
            "nome": "Snapshot API",
            "login": "snapshot_api",
            "email": "snapshot.api@local.test",
            "perfil": "operador",
            "ativo": 1,
            "permissao_modulos_json": '["dashboard:view"]',
            "captured_at": int(time.time()),
        }
        sess["auth_user_snapshot_ts"] = int(time.time())

    response = client.get("/api/v1/session", follow_redirects=False)

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["code"] == "auth_backend_unavailable"
    with client.session_transaction() as sess:
        assert sess.get("_user_id") == "17"


def test_form_logout_without_csrf_does_not_render_error_page():
    app = create_app()
    client = app.test_client()

    response = client.post("/logout", follow_redirects=False)

    assert response.status_code in {302, 303}
    assert "/login" in response.headers["Location"] or response.headers["Location"].endswith("/")
