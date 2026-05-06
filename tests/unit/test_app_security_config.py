import pytest

from backend.src.controle_treinamentos import create_app


def test_create_app_requires_secret_key_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError):
        create_app()


def test_create_app_uses_dev_fallback_secret_outside_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DEV_FALLBACK_SECRET_KEY", "dev-secret-for-tests")

    app = create_app()

    assert app.config["SECRET_KEY"] == "dev-secret-for-tests"


def test_create_app_requires_database_url_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret-for-tests")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError):
        create_app()


def test_create_app_rejects_invalid_app_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("SECRET_KEY", "secret")

    with pytest.raises(RuntimeError):
        create_app()


def test_create_app_defaults_to_development_when_app_env_missing(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DEV_FALLBACK_SECRET_KEY", "dev-secret-for-tests")

    app = create_app()

    assert app.config["APP_ENV"] == "development"


def test_create_app_rejects_secret_fingerprint_mismatch(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret-for-tests")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db.example.com:5432/postgres")
    monkeypatch.setenv("SECRET_KEY_FINGERPRINT", "deadbeef0000")

    with pytest.raises(RuntimeError):
        create_app()


def test_create_app_rejects_weak_secret_key_in_secure_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "short")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db.example.com:5432/postgres")

    with pytest.raises(RuntimeError):
        create_app()


def test_create_app_rejects_invalid_database_url_scheme(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret-long-enough")
    monkeypatch.setenv("DATABASE_URL", "mysql://user:pass@db.example.com:3306/app")

    with pytest.raises(RuntimeError):
        create_app()


def test_create_app_rejects_local_database_in_secure_env_without_explicit_override(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret-long-enough")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@127.0.0.1:5432/postgres")
    monkeypatch.delenv("ALLOW_LOCAL_DATABASE_IN_SECURE_ENV", raising=False)

    with pytest.raises(RuntimeError):
        create_app()


def test_create_app_allows_local_database_in_secure_env_when_explicitly_self_hosted(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SECRET_KEY", "prod-secret-long-enough")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@127.0.0.1:5432/postgres")
    monkeypatch.setenv("ALLOW_LOCAL_DATABASE_IN_SECURE_ENV", "1")

    app = create_app()

    assert app.config["APP_ENV"] == "production"
