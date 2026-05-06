from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app


CSRF_RE = re.compile(r'name="csrf_token"\s+value="([^"]+)"')

AUTH_REQUIRED_MESSAGE = "Autentica\u00e7\u00e3o obrigat\u00f3ria ou sess\u00e3o expirada."
INVALID_CREDENTIALS_MESSAGE = "Login inv\u00e1lido."
INACTIVE_USER_MESSAGE = "Usu\u00e1rio inativo. Contate o administrador."
CSRF_MESSAGE = "CSRF inv\u00e1lido ou sess\u00e3o expirada. Atualize a p\u00e1gina e tente novamente."
AUTH_BACKEND_UNAVAILABLE_MESSAGE = (
    "Autentica\u00e7\u00e3o indispon\u00edvel por falha tempor\u00e1ria no backend de sess\u00e3o."
)
AUTH_SESSION_INVALID_MESSAGE = "Sessao invalida ou revogada. Entre novamente para continuar."
FORBIDDEN_MESSAGE = "Acesso negado para esta opera\u00e7\u00e3o."


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


def _user_row(
    *,
    user_id: int = 91,
    login: str = "auth_contract_user",
    active: bool = True,
    permissions: str = '["dashboard:view"]',
):
    return {
        "id": user_id,
        "nome": "Auth Contract User",
        "login": login,
        "email": f"{login}@local.test",
        "perfil": "operador",
        "ativo": 1 if active else 0,
        "permissao_modulos_json": permissions,
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }


def _csrf_from_login(client) -> str:
    response = client.get("/login")
    html = response.get_data(as_text=True)
    match = CSRF_RE.search(html)
    if not match:
        raise AssertionError("Token CSRF nao encontrado na tela de login.")
    return match.group(1)


def _csrf_from_api_session(client) -> str:
    response = client.get("/api/v1/session")
    assert response.status_code == 200
    return response.get_json()["csrf_token"]


def _assert_json_error(response, *, status: int, code: str, message: str):
    assert response.status_code == status
    assert response.content_type.startswith("application/json")
    assert (response.headers.get("Location", "") or "") == ""
    payload = response.get_json()
    assert payload["success"] is False
    assert payload["status"] == status
    assert payload["code"] == code
    assert payload["message"] == message
    assert "request_id" in payload
    return payload


def _assert_login_redirect(response, *, next_url: str | None = None, auth_issue: str | None = None):
    assert response.status_code in {302, 303}
    assert response.get_json(silent=True) is None
    location = response.headers.get("Location", "") or ""
    assert "/login" in location
    parsed = urlparse(location)
    query = parse_qs(parsed.query)
    if next_url is not None:
        assert query.get("next") == [next_url]
    if auth_issue is not None:
        assert query.get("auth_issue") == [auth_issue]
    else:
        assert "auth_issue" not in query
    return location, query


def test_without_session_has_auth_required_contract_for_api_and_login_redirect_for_ssr():
    app = create_app()
    client = app.test_client()

    api_response = client.get(
        "/tripulantes",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )
    _assert_json_error(
        api_response,
        status=401,
        code="auth_required",
        message=AUTH_REQUIRED_MESSAGE,
    )

    ssr_response = client.get("/tripulantes?page=2", follow_redirects=False)
    _assert_login_redirect(ssr_response, next_url="/tripulantes?page=2")


def test_backend_invalid_session_is_not_inactive_or_forbidden(monkeypatch):
    app = create_app()
    client = app.test_client()
    monkeypatch.setattr("src.app.models.get_db", lambda: _DB(None))

    with client.session_transaction() as sess:
        sess["_user_id"] = "404"
        sess["_fresh"] = True

    api_response = client.get(
        "/tripulantes",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )
    payload = _assert_json_error(
        api_response,
        status=401,
        code="auth_session_invalid",
        message=AUTH_SESSION_INVALID_MESSAGE,
    )
    assert payload["code"] not in {"auth_user_inactive", "forbidden", "csrf_error"}

    with client.session_transaction() as sess:
        sess["_user_id"] = "404"
        sess["_fresh"] = True

    ssr_response = client.get("/tripulantes?page=2", follow_redirects=False)
    _assert_login_redirect(ssr_response, auth_issue="session_invalid")


def test_invalid_credentials_are_401_json_for_api_and_html_flash_for_ssr(monkeypatch):
    app = create_app()
    client = app.test_client()
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: _DB(None))

    api_response = client.post(
        "/api/v1/session/login",
        json={"login": "auth_contract_invalid", "senha": "wrong"},
        headers={"X-CSRFToken": _csrf_from_api_session(client), "Accept": "text/html"},
        follow_redirects=False,
    )
    _assert_json_error(
        api_response,
        status=401,
        code="auth_invalid_credentials",
        message=INVALID_CREDENTIALS_MESSAGE,
    )

    ssr_response = client.post(
        "/login",
        data={
            "csrf_token": _csrf_from_login(client),
            "login": "auth_contract_invalid_html",
            "senha": "wrong",
        },
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )
    assert ssr_response.status_code == 200
    assert ssr_response.content_type.startswith("text/html")
    assert (ssr_response.headers.get("Location", "") or "") == ""
    assert ssr_response.get_json(silent=True) is None
    assert INVALID_CREDENTIALS_MESSAGE in ssr_response.get_data(as_text=True)


def test_inactive_user_is_403_not_auth_required_for_login_and_existing_session(monkeypatch):
    app = create_app()
    client = app.test_client()
    inactive_db = _DB(_user_row(user_id=92, login="auth_contract_inactive", active=False))
    monkeypatch.setattr("src.app.repositories.user_repository.get_db", lambda: inactive_db)
    monkeypatch.setattr("src.app.models.get_db", lambda: inactive_db)

    login_response = client.post(
        "/api/v1/session/login",
        json={"login": "auth_contract_inactive", "senha": "secret"},
        headers={"X-CSRFToken": _csrf_from_api_session(client)},
        follow_redirects=False,
    )
    _assert_json_error(
        login_response,
        status=403,
        code="auth_user_inactive",
        message=INACTIVE_USER_MESSAGE,
    )

    with client.session_transaction() as sess:
        sess["_user_id"] = "92"
        sess["_fresh"] = True

    api_response = client.get(
        "/tripulantes",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )
    _assert_json_error(
        api_response,
        status=403,
        code="auth_user_inactive",
        message=INACTIVE_USER_MESSAGE,
    )
    with client.session_transaction() as sess:
        assert sess.get("_user_id") is None

    with client.session_transaction() as sess:
        sess["_user_id"] = "92"
        sess["_fresh"] = True

    ssr_response = client.get("/tripulantes?page=2", follow_redirects=False)
    _assert_login_redirect(ssr_response, auth_issue="user_inactive")
    with client.session_transaction() as sess:
        assert ("error", INACTIVE_USER_MESSAGE) in sess.get("_flashes", [])
        assert sess.get("_user_id") is None


def test_invalid_csrf_has_own_contract_and_is_not_used_for_missing_auth():
    app = create_app()
    client = app.test_client()

    csrf_response = client.post(
        "/api/v1/session/login",
        json={"login": "auth_contract_user", "senha": "secret"},
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )
    _assert_json_error(
        csrf_response,
        status=400,
        code="csrf_error",
        message=CSRF_MESSAGE,
    )

    ssr_response = client.post(
        "/login",
        data={"login": "auth_contract_user", "senha": "secret"},
        headers={"Accept": "text/html"},
        follow_redirects=False,
    )
    _assert_login_redirect(ssr_response)
    with client.session_transaction() as sess:
        flashes = sess.get("_flashes", [])
        assert any("p\u00e1gina ficou desatualizada" in message for _kind, message in flashes)

    auth_response = client.post("/jobs/1/reativar", follow_redirects=False)
    _assert_json_error(
        auth_response,
        status=401,
        code="auth_required",
        message=AUTH_REQUIRED_MESSAGE,
    )


def test_auth_backend_unavailable_is_503_json_and_predictable_ssr_redirect(monkeypatch):
    app = create_app()
    client = app.test_client()

    def _boom():
        raise RuntimeError("db_unavailable")

    monkeypatch.setattr("src.app.models.get_db", _boom)

    with client.session_transaction() as sess:
        sess["_user_id"] = "93"
        sess["_fresh"] = True

    api_response = client.get(
        "/tripulantes",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )
    _assert_json_error(
        api_response,
        status=503,
        code="auth_backend_unavailable",
        message=AUTH_BACKEND_UNAVAILABLE_MESSAGE,
    )
    with client.session_transaction() as sess:
        assert sess.get("_user_id") == "93"

    ssr_response = client.get("/tripulantes?page=2", follow_redirects=False)
    _assert_login_redirect(
        ssr_response,
        next_url="/tripulantes?page=2",
        auth_issue="backend_unavailable",
    )
    with client.session_transaction() as sess:
        assert sess.get("_user_id") == "93"


def test_user_without_permission_is_authorization_forbidden_not_authentication(monkeypatch):
    app = create_app()
    client = app.test_client()
    restricted_db = _DB(_user_row(user_id=94, login="auth_contract_restricted", permissions='["dashboard:view"]'))
    monkeypatch.setattr("src.app.models.get_db", lambda: restricted_db)

    with client.session_transaction() as sess:
        sess["_user_id"] = "94"
        sess["_fresh"] = True

    api_response = client.get(
        "/usuarios",
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        follow_redirects=False,
    )
    _assert_json_error(
        api_response,
        status=403,
        code="forbidden",
        message=FORBIDDEN_MESSAGE,
    )

    ssr_response = client.get("/usuarios", follow_redirects=False)
    assert ssr_response.status_code == 403
    assert ssr_response.content_type.startswith("text/html")
    assert (ssr_response.headers.get("Location", "") or "") == ""
    assert ssr_response.get_json(silent=True) is None
    body = ssr_response.get_data(as_text=True)
    assert "Acesso negado" in body
    assert "/login" not in (ssr_response.headers.get("Location", "") or "")
