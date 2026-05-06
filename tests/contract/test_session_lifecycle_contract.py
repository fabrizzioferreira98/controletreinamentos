from __future__ import annotations

import time
from urllib.parse import parse_qs, urlparse

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app


class _Cursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _DB:
    def __init__(self, row):
        self._row = row

    def execute(self, _query, _params):
        return _Cursor(self._row)


class _MappedDB:
    def __init__(self, rows):
        self._by_login = {row["login"]: row for row in rows}
        self._by_id = {str(row["id"]): row for row in rows}

    def execute(self, query, params):
        value = str(params[0])
        if "WHERE login = %s" in query:
            return _Cursor(self._by_login.get(value))
        return _Cursor(self._by_id.get(value))


def _user_row(*, user_id: int = 31, login: str = "session_user"):
    return {
        "id": user_id,
        "nome": f"Session User {user_id}",
        "login": login,
        "email": f"{login}@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": '["dashboard:view","tripulantes:view"]',
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _csrf(client) -> str:
    response = client.get("/api/v1/session")
    assert response.status_code == 200
    return response.get_json()["csrf_token"]


def _api_login(client, *, login: str = "session_user", remember=None):
    payload = {"login": login, "senha": "secret"}
    if remember is not None:
        payload["remember"] = remember
    return client.post(
        "/api/v1/session/login",
        json=payload,
        headers={"X-CSRFToken": _csrf(client)},
        follow_redirects=False,
    )


def _seed_auth_session(client, *, user_id: int, expires_delta: int = 3600, remember: bool = False, snapshot=None):
    now = int(time.time())
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
        sess.permanent = remember
        sess["auth_session_id"] = f"seeded-{user_id}"
        sess["auth_session_created_at"] = now - 120
        sess["auth_session_last_seen_at"] = now - 120
        sess["auth_session_expires_at"] = now + expires_delta
        sess["auth_session_mode"] = "permanent" if remember else "browser"
        sess["auth_session_remember"] = remember
        if snapshot is not None:
            sess["auth_user_snapshot"] = snapshot
            sess["auth_user_snapshot_ts"] = snapshot.get("captured_at")
    return {
        "id": f"seeded-{user_id}",
        "last_seen_at": now - 120,
        "expires_at": now + expires_delta,
    }


def _assert_json_error(response, *, status: int, code: str):
    assert response.status_code == status
    assert response.content_type.startswith("application/json")
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == status
    assert payload["code"] == code
    return payload


def _assert_session_cleared(client):
    with client.session_transaction() as sess:
        assert sess.get("_user_id") is None
        assert sess.get("auth_session_id") is None
        assert sess.get("auth_session_expires_at") is None


def _cookie_headers(response, name: str) -> list[str]:
    return [header for header in response.headers.getlist("Set-Cookie") if header.startswith(f"{name}=")]


def _cookie_is_cleared(header: str) -> bool:
    return "Max-Age=0" in header or "Expires=Thu, 01 Jan 1970" in header


def test_valid_session_is_backend_verified_and_renews_expiration(monkeypatch):
    app = create_app()
    client = app.test_client()
    row = _user_row(user_id=31)
    fake_db = _DB(row)
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    login_response = _api_login(client, remember=True)
    assert login_response.status_code == 200
    login_payload = login_response.get_json()
    assert login_payload["session"]["state"] == "authenticated"
    assert login_payload["session"]["mode"] == "permanent"
    assert login_payload["session"]["remember"] is True

    now = int(time.time())
    with client.session_transaction() as sess:
        session_id = sess["auth_session_id"]
        sess["auth_session_last_seen_at"] = now - 120
        sess["auth_session_expires_at"] = now + 60
        old_last_seen = sess["auth_session_last_seen_at"]
        old_expires_at = sess["auth_session_expires_at"]

    response = client.get("/api/v1/session", follow_redirects=False)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["authenticated"] is True
    assert payload["session"]["state"] == "authenticated"
    assert payload["session"]["backend_verified"] is True
    assert payload["session"]["snapshot"]["used"] is False
    assert payload["session"]["remember"] is True
    with client.session_transaction() as sess:
        assert sess.get("_user_id") == "31"
        assert sess.get("auth_session_id") == session_id
        assert sess.get("auth_session_last_seen_at") >= old_last_seen
        assert sess.get("auth_session_expires_at") > old_expires_at


def test_expired_session_is_distinct_from_missing_and_skips_backend_validation(monkeypatch):
    app = create_app()
    client = app.test_client()

    def _backend_must_not_be_called():
        raise AssertionError("expired session must be rejected before backend validation")

    monkeypatch.setattr("src.app.models.get_db", _backend_must_not_be_called)
    _seed_auth_session(client, user_id=32, expires_delta=-1)

    response = client.get("/api/v1/session", follow_redirects=False)

    _assert_json_error(response, status=401, code="auth_session_expired")
    _assert_session_cleared(client)


def test_revoked_backend_session_with_cookie_is_invalid_not_anonymous(monkeypatch):
    app = create_app()
    client = app.test_client()
    monkeypatch.setattr("src.app.models.get_db", lambda: _DB(None))
    _seed_auth_session(client, user_id=404, expires_delta=3600)

    response = client.get("/api/v1/session", follow_redirects=False)

    payload = _assert_json_error(response, status=401, code="auth_session_invalid")
    assert payload["code"] not in {"auth_required", "auth_session_expired"}
    _assert_session_cleared(client)


def test_missing_session_keeps_anonymous_probe_but_protected_api_requires_auth():
    app = create_app()
    client = app.test_client()

    session_response = client.get("/api/v1/session", follow_redirects=False)
    assert session_response.status_code == 200
    session_payload = session_response.get_json()
    assert session_payload["authenticated"] is False
    assert session_payload["session"]["state"] == "anonymous"
    assert session_payload["session"]["backend_verified"] is False

    protected_response = client.get("/api/v1/me", follow_redirects=False)
    _assert_json_error(protected_response, status=401, code="auth_required")


def test_remember_me_active_and_absent_have_explicit_cookie_and_session_contracts(monkeypatch):
    app = create_app()
    client = app.test_client()
    row = _user_row(user_id=33)
    fake_db = _DB(row)
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    remember_response = _api_login(client, remember=True)
    assert remember_response.status_code == 200
    remember_payload = remember_response.get_json()
    assert remember_payload["session"]["mode"] == "permanent"
    assert remember_payload["session"]["remember"] is True
    assert remember_payload["session"]["permanent"] is True
    remember_cookie_name = app.config["REMEMBER_COOKIE_NAME"]
    remember_cookie_headers = _cookie_headers(remember_response, remember_cookie_name)
    assert remember_cookie_headers
    assert not any(_cookie_is_cleared(header) for header in remember_cookie_headers)

    logout_response = client.post("/api/v1/session/logout", follow_redirects=False)
    assert logout_response.status_code == 200
    assert any(_cookie_is_cleared(header) for header in _cookie_headers(logout_response, remember_cookie_name))

    browser_response = _api_login(client)
    assert browser_response.status_code == 200
    browser_payload = browser_response.get_json()
    assert browser_payload["session"]["mode"] == "browser"
    assert browser_payload["session"]["remember"] is False
    assert browser_payload["session"]["permanent"] is False
    browser_remember_headers = _cookie_headers(browser_response, remember_cookie_name)
    assert browser_remember_headers
    assert all(_cookie_is_cleared(header) for header in browser_remember_headers)
    with client.session_transaction() as sess:
        assert sess.permanent is False
        assert sess.get("auth_session_remember") is False


def test_logout_with_already_invalid_backend_session_is_idempotent_and_clears_state(monkeypatch):
    app = create_app()
    client = app.test_client()

    def _backend_must_not_be_called():
        raise AssertionError("logout must not validate backend before clearing session")

    monkeypatch.setattr("src.app.models.get_db", _backend_must_not_be_called)
    _seed_auth_session(client, user_id=405, expires_delta=3600)

    response = client.post("/api/v1/session/logout", follow_redirects=False)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["code"] == "logout_ok"
    assert payload["authenticated"] is False
    assert payload["session"]["state"] == "terminated"
    _assert_session_cleared(client)


def test_html_logout_with_invalid_session_redirects_and_clears_without_backend_validation(monkeypatch):
    app = create_app()
    client = app.test_client()

    def _backend_must_not_be_called():
        raise AssertionError("html logout must not validate backend before clearing session")

    monkeypatch.setattr("src.app.models.get_db", _backend_must_not_be_called)
    _seed_auth_session(client, user_id=406, expires_delta=3600)

    response = client.post("/logout", follow_redirects=False)

    assert response.status_code in {302, 303}
    assert "/login" in (response.headers.get("Location", "") or "")
    _assert_session_cleared(client)


def test_reentry_after_logout_allocates_new_session_and_replaces_snapshot(monkeypatch):
    app = create_app()
    client = app.test_client()
    first_row = _user_row(user_id=34, login="session_first")
    second_row = _user_row(user_id=35, login="session_second")
    fake_db = _MappedDB([first_row, second_row])
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)

    first_login = _api_login(client, login="session_first", remember=True)
    assert first_login.status_code == 200
    with client.session_transaction() as sess:
        first_session_id = sess["auth_session_id"]
        assert sess["auth_user_snapshot"]["id"] == "34"

    logout_response = client.post("/api/v1/session/logout", follow_redirects=False)
    assert logout_response.status_code == 200
    _assert_session_cleared(client)

    second_login = _api_login(client, login="session_second")
    assert second_login.status_code == 200
    second_payload = second_login.get_json()
    assert second_payload["user"]["id"] == "35"
    assert second_payload["session"]["mode"] == "browser"
    with client.session_transaction() as sess:
        assert sess.get("_user_id") == "35"
        assert sess.get("auth_session_id") != first_session_id
        assert sess["auth_user_snapshot"]["id"] == "35"
        assert sess.permanent is False


def test_concurrent_sessions_have_independent_logout_and_reentry_boundaries(monkeypatch):
    app = create_app()
    row = _user_row(user_id=36)
    fake_db = _DB(row)
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: fake_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: fake_db)
    first_client = app.test_client()
    second_client = app.test_client()

    assert _api_login(first_client, remember=True).status_code == 200
    assert _api_login(second_client, remember=True).status_code == 200
    with first_client.session_transaction() as sess:
        first_session_id = sess["auth_session_id"]
    with second_client.session_transaction() as sess:
        second_session_id = sess["auth_session_id"]
    assert first_session_id != second_session_id

    logout_response = first_client.post("/api/v1/session/logout", follow_redirects=False)
    assert logout_response.status_code == 200
    _assert_session_cleared(first_client)

    second_state = second_client.get("/api/v1/session", follow_redirects=False)
    assert second_state.status_code == 200
    second_payload = second_state.get_json()
    assert second_payload["authenticated"] is True
    assert second_payload["session"]["state"] == "authenticated"
    with second_client.session_transaction() as sess:
        assert sess.get("_user_id") == "36"
        assert sess.get("auth_session_id") == second_session_id


def test_expired_session_has_coherent_api_error_and_ssr_redirect(monkeypatch):
    app = create_app()
    client = app.test_client()

    def _backend_must_not_be_called():
        raise AssertionError("expired session must be rejected before endpoint permission checks")

    monkeypatch.setattr("src.app.models.get_db", _backend_must_not_be_called)
    _seed_auth_session(client, user_id=37, expires_delta=-1)

    api_response = client.get(
        "/tripulantes",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )
    _assert_json_error(api_response, status=401, code="auth_session_expired")
    _assert_session_cleared(client)

    _seed_auth_session(client, user_id=37, expires_delta=-1)
    ssr_response = client.get("/tripulantes?page=2", follow_redirects=False)
    assert ssr_response.status_code in {302, 303}
    location = ssr_response.headers.get("Location", "") or ""
    assert "/login" in location
    query = parse_qs(urlparse(location).query)
    assert query.get("auth_issue") == ["session_expired"]
    _assert_session_cleared(client)


def test_stale_snapshot_does_not_keep_spa_session_when_backend_cannot_validate(monkeypatch):
    app = create_app()
    client = app.test_client()

    def _backend_unavailable():
        raise RuntimeError("temporary_db_unavailable")

    stale_captured_at = int(time.time()) - 9999
    monkeypatch.setattr("src.app.models.get_db", _backend_unavailable)
    _seed_auth_session(
        client,
        user_id=38,
        expires_delta=3600,
        snapshot={
            "id": "38",
            "nome": "Stale Snapshot",
            "login": "stale_snapshot",
            "email": "stale.snapshot@local.test",
            "perfil": "operador",
            "ativo": 1,
            "permissao_modulos_json": '["dashboard:view"]',
            "captured_at": stale_captured_at,
        },
    )

    response = client.get("/api/v1/session", follow_redirects=False)

    _assert_json_error(response, status=503, code="auth_backend_unavailable")
    with client.session_transaction() as sess:
        assert sess.get("_user_id") == "38"
        assert sess.get("auth_session_id") == "seeded-38"
