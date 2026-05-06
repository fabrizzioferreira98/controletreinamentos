from __future__ import annotations

import json
import re

from backend.src.controle_treinamentos import create_app
from backend.src.controle_treinamentos.repositories import user_repository as user_repo_module
from werkzeug.security import generate_password_hash

CSRF_RE = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


class _EmptyCursor:
    def fetchone(self):
        return None


class _SingleCursor:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeDB:
    def execute(self, _query, _params):
        return _EmptyCursor()


class _InactiveUserDB:
    def execute(self, _query, _params):
        return _SingleCursor(
            {
                "id": 1,
                "nome": "User Inativo",
                "login": "inativo",
                "email": "inativo@local.test",
                "perfil": "operador",
                "ativo": 0,
                "permissao_modulos_json": "[]",
                "senha_hash": "",
            }
        )


class _SingleUserDB:
    def __init__(self, row):
        self._row = row

    def execute(self, _query, _params):
        return _SingleCursor(self._row)


def _extract_csrf_token(html: str) -> str:
    match = CSRF_RE.search(html)
    if not match:
        raise AssertionError("Token CSRF não encontrado na tela de login.")
    return match.group(1)


def test_login_returns_503_when_database_is_unavailable(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("SECRET_KEY", "test-login-secret")
    app = create_app()
    client = app.test_client()

    def _raise_db_error():
        raise RuntimeError("database_unavailable")

    monkeypatch.setattr(user_repo_module, "get_db", _raise_db_error)

    page = client.get("/login")
    csrf = _extract_csrf_token(page.get_data(as_text=True))
    response = client.post(
        "/login",
        data={"csrf_token": csrf, "login": "admin", "senha": "secret"},
        follow_redirects=False,
    )

    body = response.get_data(as_text=True)
    assert response.status_code == 503
    assert "autenticação" in body.lower()
    assert "erro interno" not in body.lower()


def test_login_invalid_credentials_does_not_raise_internal_error(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("SECRET_KEY", "test-login-secret")
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(user_repo_module, "get_db", lambda: _FakeDB())

    page = client.get("/login")
    csrf = _extract_csrf_token(page.get_data(as_text=True))
    response = client.post(
        "/login",
        data={"csrf_token": csrf, "login": "invalido", "senha": "invalida"},
        follow_redirects=False,
    )

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Login inválido." in body
    assert "erro interno" not in body.lower()


def test_login_returns_503_with_configuration_message_for_structural_db_error(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("SECRET_KEY", "test-login-secret")
    app = create_app()
    client = app.test_client()

    def _raise_config_error():
        raise RuntimeError("DATABASE_URL inválida para conexão")

    monkeypatch.setattr(user_repo_module, "get_db", _raise_config_error)

    page = client.get("/login")
    csrf = _extract_csrf_token(page.get_data(as_text=True))
    response = client.post(
        "/login",
        data={"csrf_token": csrf, "login": "admin", "senha": "secret"},
        follow_redirects=False,
    )

    body = response.get_data(as_text=True)
    assert response.status_code == 503
    assert "erro de configuração do ambiente" in body.lower()


def test_login_inactive_user_returns_specific_message(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("SECRET_KEY", "test-login-secret")
    app = create_app()
    client = app.test_client()

    monkeypatch.setattr(user_repo_module, "get_db", lambda: _InactiveUserDB())

    page = client.get("/login")
    csrf = _extract_csrf_token(page.get_data(as_text=True))
    response = client.post(
        "/login",
        data={"csrf_token": csrf, "login": "inativo", "senha": "secret"},
        follow_redirects=False,
    )

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "Usuário inativo." in body


def test_login_redirects_to_first_permitted_landing_when_dashboard_not_allowed(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("SECRET_KEY", "test-login-secret")
    app = create_app()
    client = app.test_client()

    row = {
        "id": 1,
        "nome": "User Limitado",
        "login": "limitado",
        "email": "limitado@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": json.dumps(["tripulantes:view"]),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }
    monkeypatch.setattr(user_repo_module, "get_db", lambda: _SingleUserDB(row))

    page = client.get("/login")
    csrf = _extract_csrf_token(page.get_data(as_text=True))
    response = client.post(
        "/login",
        data={"csrf_token": csrf, "login": "limitado", "senha": "secret"},
        follow_redirects=False,
    )

    assert response.status_code in {302, 303}
    assert "/tripulantes" in (response.headers.get("Location", "") or "")


def test_login_retries_once_on_transient_db_failure(monkeypatch):
    monkeypatch.setenv("APP_ENV", "testing")
    monkeypatch.setenv("SECRET_KEY", "test-login-secret")
    app = create_app()
    client = app.test_client()

    row = {
        "id": 1,
        "nome": "User Retry",
        "login": "retry_user",
        "email": "retry@local.test",
        "perfil": "operador",
        "ativo": 1,
        "permissao_modulos_json": json.dumps(["dashboard:view"]),
        "senha_hash": generate_password_hash("secret", method="pbkdf2:sha256"),
    }
    calls = {"count": 0}

    def _get_db():
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("temporary_db_failure")
        return _SingleUserDB(row)

    monkeypatch.setattr(user_repo_module, "get_db", _get_db)

    page = client.get("/login")
    csrf = _extract_csrf_token(page.get_data(as_text=True))
    response = client.post(
        "/login",
        data={"csrf_token": csrf, "login": "retry_user", "senha": "secret"},
        follow_redirects=False,
    )

    assert response.status_code in {302, 303}
    assert calls["count"] == 2
