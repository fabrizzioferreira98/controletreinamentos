from ops.scripts.backup import run_backups
from ops.scripts.jobs import run_notifications


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _App:
    def app_context(self):
        return _Context()


def test_backup_direct_guard_blocks_when_queue_has_run_backup(monkeypatch):
    monkeypatch.delenv("BACKUP_DIRECT_ALLOW_IN_FLIGHT", raising=False)
    monkeypatch.setattr(run_backups, "get_db", lambda: object())
    monkeypatch.setattr(
        run_backups,
        "collect_in_flight_jobs_by_type",
        lambda db, job_type: {"job_type": job_type, "queued": 1, "running": 0, "total": 1},
    )

    guard = run_backups._direct_execution_guard(_App())

    assert guard["checked"] is True
    assert guard["blocked"] is True
    assert guard["status"] == "blocked"


def test_notifications_direct_guard_allows_explicit_override(monkeypatch):
    monkeypatch.setenv("NOTIFICATIONS_DIRECT_ALLOW_IN_FLIGHT", "1")
    monkeypatch.setattr(run_notifications, "get_db", lambda: object())
    monkeypatch.setattr(
        run_notifications,
        "collect_in_flight_jobs_by_type",
        lambda db, job_type: {"job_type": job_type, "queued": 0, "running": 1, "total": 1},
    )

    guard = run_notifications._direct_execution_guard(_App())

    assert guard["checked"] is True
    assert guard["blocked"] is False
    assert guard["status"] == "override"
    assert guard["override_env"] == "NOTIFICATIONS_DIRECT_ALLOW_IN_FLIGHT"
