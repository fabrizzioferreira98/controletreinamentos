from __future__ import annotations

import tarfile
from pathlib import Path

from flask import Flask

from backend.src.controle_treinamentos.infra.backup import (
    _config_paths,
    _include_paths,
    _validate_backup_scope,
)
from ops.scripts.backup.backup_restore_drill import _collect_table_counts


def _app() -> Flask:
    root = Path(__file__).resolve().parents[1] / "src" / "app"
    app = Flask("backup-tests", root_path=str(root))
    app.config["APP_ENV"] = "production"
    return app


def _write_tar_gz(target: Path, members: dict[str, str]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_root = target.parent / f"{target.stem}_src"
    temp_root.mkdir(parents=True, exist_ok=True)
    for name, contents in members.items():
        path = temp_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    with tarfile.open(target, "w:gz") as tar:
        for item in temp_root.rglob("*"):
            tar.add(item, arcname=str(item.relative_to(temp_root)).replace("\\", "/"))


def test_secure_defaults_infer_operational_expectations(monkeypatch):
    monkeypatch.delenv("BACKUP_INCLUDE_PATHS", raising=False)
    monkeypatch.delenv("BACKUP_CONFIG_PATHS", raising=False)

    app = _app()
    with app.app_context():
        include_paths, missing_include, include_specs = _include_paths()
        config_paths, missing_config, config_specs = _config_paths()

    assert any(path.name == "static" for path in include_paths)
    assert any("uploads" in spec.lower() for spec in include_specs)
    assert missing_include
    assert any("caddy" in spec.lower() for spec in config_specs)
    assert any("tasks" in spec.lower() for spec in config_specs)
    assert config_specs
    assert all(path.exists() for path in config_paths)


def test_secure_scope_validation_rejects_missing_uploads_and_example_only_configs(tmp_path):
    assets_file = tmp_path / "assets.tar.gz"
    config_file = tmp_path / "config.tar.gz"
    _write_tar_gz(
        assets_file,
        {
            "static/styles.css": "body {}",
        },
    )
    _write_tar_gz(
        config_file,
        {
            "env/prod.env.example": "DATABASE_URL=postgresql://example",
            "caddy/Caddyfile": ":80",
            "tasks/backup-prod.ps1": "Write-Host backup",
        },
    )

    app = _app()
    with app.app_context():
        ok, issues = _validate_backup_scope(
            include_specs=[r"D:\srv-data\controle-treinamentos\prod\uploads"],
            missing_include_specs=[],
            assets_file=assets_file,
            config_specs=[
                r"C:\srv\controle-treinamentos\env",
                r"C:\srv\controle-treinamentos\caddy",
                r"C:\srv\controle-treinamentos\tasks",
            ],
            missing_config_specs=[],
            config_file=config_file,
        )

    assert ok is False
    assert any("uploads" in issue.lower() for issue in issues)
    assert any("apenas arquivos .example" in issue.lower() for issue in issues)


class _FakeCursor:
    def __init__(self, counts: dict[str, int], failing_tables: set[str] | None = None):
        self._counts = counts
        self._failing_tables = failing_tables or set()
        self._current_table = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query: str):
        self._current_table = query.split('"')[1]
        if self._current_table in self._failing_tables:
            raise RuntimeError("missing table")

    def fetchone(self):
        return [self._counts[self._current_table]]


class _FakeConn:
    def __init__(self, counts: dict[str, int], failing_tables: set[str] | None = None):
        self._counts = counts
        self._failing_tables = failing_tables or set()
        self.rollbacks = 0

    def cursor(self):
        return _FakeCursor(self._counts, self._failing_tables)

    def rollback(self):
        self.rollbacks += 1


def test_collect_table_counts_marks_missing_tables_without_crashing():
    conn = _FakeConn({"usuarios": 2, "tripulantes": 10}, failing_tables={"treinamentos"})
    counts = _collect_table_counts(conn, tables=("usuarios", "treinamentos", "tripulantes"))

    assert counts["usuarios"] == 2
    assert counts["tripulantes"] == 10
    assert counts["treinamentos"] is None
    assert conn.rollbacks == 1
