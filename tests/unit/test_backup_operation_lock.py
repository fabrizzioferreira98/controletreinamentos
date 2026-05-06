from datetime import datetime, timedelta

from flask import Flask

from backend.src.controle_treinamentos.infra import backup as backup_module


def test_backup_operation_lock_blocks_second_execution(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_OPERATION_LOCK_STALE_SECONDS", "3600")
    app = Flask(__name__)
    app.config["APP_ENV"] = "test"

    with app.app_context():
        lock_file, lock_payload, existing_lock = backup_module._acquire_backup_operation_lock(
            tmp_path,
            backup_type="manual",
        )
        assert lock_payload is not None
        assert existing_lock is None

        second_file, second_payload, second_existing = backup_module._acquire_backup_operation_lock(
            tmp_path,
            backup_type="agendado",
        )

        assert second_file == lock_file
        assert second_payload is None
        assert second_existing["token"] == lock_payload["token"]

        backup_module._release_backup_operation_lock(lock_file, lock_payload)

        _, third_payload, third_existing = backup_module._acquire_backup_operation_lock(
            tmp_path,
            backup_type="agendado",
        )
        assert third_payload is not None
        assert third_existing is None

        backup_module._release_backup_operation_lock(lock_file, third_payload)


def test_backup_operation_lock_recovers_stale_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKUP_OPERATION_LOCK_STALE_SECONDS", "60")
    app = Flask(__name__)
    app.config["APP_ENV"] = "test"
    lock_file = tmp_path / ".run_backup.lock"
    stale_created_at = (datetime.utcnow() - timedelta(minutes=10)).isoformat(timespec="seconds") + "Z"
    lock_file.write_text(
        (
            "{"
            '"lock": "run_backup",'
            '"token": "stale-token",'
            f'"created_at": "{stale_created_at}"'
            "}"
        ),
        encoding="utf-8",
    )

    with app.app_context():
        _, lock_payload, existing_lock = backup_module._acquire_backup_operation_lock(
            tmp_path,
            backup_type="agendado",
        )

        assert lock_payload is not None
        assert lock_payload["token"] != "stale-token"
        assert existing_lock is None

        backup_module._release_backup_operation_lock(lock_file, lock_payload)
