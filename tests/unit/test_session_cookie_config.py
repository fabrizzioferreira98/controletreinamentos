from backend.src.controle_treinamentos import create_app
import pytest


def test_cookie_flags_are_secure_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret-key-long")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db.example.com:5432/postgres")
    app = create_app()

    assert app.config["SESSION_COOKIE_SECURE"] is True
    assert app.config["SESSION_COOKIE_HTTPONLY"] is True
    assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert app.config["REMEMBER_COOKIE_SECURE"] is True
    assert app.config["REMEMBER_COOKIE_HTTPONLY"] is True
    assert app.config["REMEMBER_COOKIE_SAMESITE"] == "Lax"
    assert app.config["WTF_CSRF_TIME_LIMIT"] == 3600
    assert app.config["SESSION_COOKIE_NAME"] == "controle_treinamentos_session"
    assert app.config["REMEMBER_COOKIE_NAME"] == "controle_treinamentos_remember"
    assert app.config["SESSION_REFRESH_EACH_REQUEST"] is True
    assert app.config["REMEMBER_COOKIE_REFRESH_EACH_REQUEST"] is True


def test_cookie_flags_are_relaxed_in_development(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", "dev-secret")
    app = create_app()

    assert app.config["SESSION_COOKIE_SECURE"] is False
    assert app.config["REMEMBER_COOKIE_SECURE"] is False


def test_cookie_flags_can_be_relaxed_explicitly_in_secure_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret-key-long")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db.example.com:5432/postgres")
    monkeypatch.setenv("ALLOW_INSECURE_HTTP_IN_SECURE_ENV", "1")
    app = create_app()

    assert app.config["SESSION_COOKIE_SECURE"] is False
    assert app.config["REMEMBER_COOKIE_SECURE"] is False
    assert app.config["PREFERRED_URL_SCHEME"] == "http"
    assert app.config["EMIT_HSTS"] is False


def test_cookie_domain_path_and_csrf_ttl_can_be_configured(monkeypatch):
    monkeypatch.setenv("APP_ENV", "homolog")
    monkeypatch.setenv("SECRET_KEY", "homolog-secret-key-long")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db.example.com:5432/postgres")
    monkeypatch.setenv("COOKIE_DOMAIN", ".example.com")
    monkeypatch.setenv("SESSION_COOKIE_PATH", "/")
    monkeypatch.setenv("REMEMBER_COOKIE_PATH", "/")
    monkeypatch.setenv("SESSION_COOKIE_NAME", "ct_session")
    monkeypatch.setenv("REMEMBER_COOKIE_NAME", "ct_remember")
    monkeypatch.setenv("WTF_CSRF_TIME_LIMIT_SECONDS", "1800")
    app = create_app()

    assert app.config["SESSION_COOKIE_DOMAIN"] == ".example.com"
    assert app.config["REMEMBER_COOKIE_DOMAIN"] == ".example.com"
    assert app.config["SESSION_COOKIE_NAME"] == "ct_session"
    assert app.config["REMEMBER_COOKIE_NAME"] == "ct_remember"
    assert app.config["SESSION_COOKIE_PATH"] == "/"
    assert app.config["REMEMBER_COOKIE_PATH"] == "/"
    assert app.config["WTF_CSRF_TIME_LIMIT"] == 1800


def test_cookie_samesite_can_be_configured(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "homolog-secret-key-long")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db.example.com:5432/postgres")
    monkeypatch.setenv("SESSION_COOKIE_SAMESITE", "Strict")
    app = create_app()

    assert app.config["SESSION_COOKIE_SAMESITE"] == "Strict"
    assert app.config["REMEMBER_COOKIE_SAMESITE"] == "Strict"


def test_cookie_samesite_none_is_rejected_without_secure_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("SECRET_KEY", "dev-secret")
    monkeypatch.setenv("SESSION_COOKIE_SAMESITE", "None")

    with pytest.raises(RuntimeError):
        create_app()


def test_cookie_domain_with_protocol_is_rejected(monkeypatch):
    monkeypatch.setenv("APP_ENV", "homolog")
    monkeypatch.setenv("SECRET_KEY", "homolog-secret-key-long")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db.example.com:5432/postgres")
    monkeypatch.setenv("COOKIE_DOMAIN", "https://example.com")

    with pytest.raises(RuntimeError):
        create_app()


def test_cookie_path_must_start_with_slash(monkeypatch):
    monkeypatch.setenv("APP_ENV", "homolog")
    monkeypatch.setenv("SECRET_KEY", "homolog-secret-key-long")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db.example.com:5432/postgres")
    monkeypatch.setenv("SESSION_COOKIE_PATH", "app")

    with pytest.raises(RuntimeError):
        create_app()
