from __future__ import annotations

from werkzeug.security import generate_password_hash

from backend.src.controle_treinamentos import create_app


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
    assert payload["user"]["login"] == "operador_api"
    assert "dashboard:view" in payload["capabilities"]["granted_permissions"]
    assert payload["capabilities"]["landing_url"].startswith("/")

    session_state = client.get("/api/v1/session")
    session_payload = session_state.get_json()
    assert session_payload["authenticated"] is True
    assert session_payload["user"]["login"] == "operador_api"


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
