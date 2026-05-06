from flask import Flask

from backend.src.controle_treinamentos import db as db_module


def _make_app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


def test_build_pool_config_uses_safe_defaults(monkeypatch):
    app = _make_app()
    with app.app_context():
        monkeypatch.delenv("DB_POOL_MIN_CONN", raising=False)
        monkeypatch.delenv("DB_POOL_MAX_CONN", raising=False)
        monkeypatch.delenv("DB_CONNECT_TIMEOUT_SECONDS", raising=False)
        monkeypatch.delenv("DB_STATEMENT_TIMEOUT_MS", raising=False)

        config = db_module._build_pool_config("postgresql://user:pass@localhost:5432/app")

    assert config["min_conn"] == 1
    assert config["max_conn"] == 20
    assert config["connect_kwargs"]["connect_timeout"] == 8
    assert config["connect_kwargs"]["options"] == "-c statement_timeout=8000"


def test_build_pool_config_swaps_invalid_min_max(monkeypatch):
    app = _make_app()
    with app.app_context():
        monkeypatch.setenv("DB_POOL_MIN_CONN", "40")
        monkeypatch.setenv("DB_POOL_MAX_CONN", "12")

        config = db_module._build_pool_config("postgresql://user:pass@localhost:5432/app")

    assert config["min_conn"] == 12
    assert config["max_conn"] == 40


def test_build_pool_config_respects_statement_timeout_unless_url_has_options(monkeypatch):
    app = _make_app()
    with app.app_context():
        monkeypatch.setenv("DB_STATEMENT_TIMEOUT_MS", "5000")
        config_plain = db_module._build_pool_config("postgresql://user:pass@localhost:5432/app")
        config_with_options = db_module._build_pool_config(
            "postgresql://user:pass@localhost:5432/app?options=-c%20statement_timeout%3D1000"
        )

    assert config_plain["connect_kwargs"]["options"] == "-c statement_timeout=5000"
    assert "options" not in config_with_options["connect_kwargs"]
