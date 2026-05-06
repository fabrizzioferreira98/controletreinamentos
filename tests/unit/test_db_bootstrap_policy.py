from flask import Flask

from backend.src.controle_treinamentos import db as db_module


def test_init_app_never_bootstraps_schema_automatically(monkeypatch):
    app = Flask(__name__)
    app.config["TESTING"] = False
    app.config["APP_ENV"] = "production"

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/app")
    monkeypatch.setenv("AUTO_MIGRATE_ON_BOOT", "1")
    called = {"execute_script": False}

    def _fake_execute_script():
        called["execute_script"] = True

    monkeypatch.setattr(db_module, "execute_script", _fake_execute_script)

    db_module.init_app(app)

    assert called["execute_script"] is False
