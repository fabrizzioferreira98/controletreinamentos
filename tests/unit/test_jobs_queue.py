import json
import sys
import types
from datetime import datetime

import pytest

from backend.src.controle_treinamentos.infra import jobs as jobs_module
from backend.src.controle_treinamentos.infra.jobs import (
    build_bucketed_idempotency_key,
    collect_in_flight_jobs_by_type,
    collect_job_queue_snapshot,
    enqueue_background_job,
    requeue_dead_letter_job,
)


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        if not self._rows:
            return None
        return self._rows[0]

    def fetchall(self):
        return list(self._rows)


class _FakeDB:
    def __init__(self):
        self.jobs = []
        self.next_id = 1

    def execute(self, query, params=()):
        compact = " ".join(query.split())
        if "SELECT COUNT(*) AS total FROM background_jobs WHERE job_type = %s AND status IN (%s, %s)" in compact:
            job_type = params[0]
            active = [item for item in self.jobs if item["job_type"] == job_type and item["status"] in {"queued", "running"}]
            return _FakeCursor([{"total": len(active)}])
        if "SELECT status, COUNT(*) AS total, MIN(created_at) AS oldest_created_at" in compact:
            job_type = params[0]
            rows = []
            for status in ("queued", "running"):
                active = [
                    item
                    for item in self.jobs
                    if item["job_type"] == job_type and item["status"] == status
                ]
                if active:
                    rows.append(
                        {
                            "status": status,
                            "total": len(active),
                            "oldest_created_at": min(item["created_at"] for item in active),
                        }
                    )
            return _FakeCursor(rows)
        if "SELECT id, status, job_type, idempotency_key FROM background_jobs" in compact:
            key = params[0]
            matches = [item for item in self.jobs if item["idempotency_key"] == key]
            row = matches[-1] if matches else None
            return _FakeCursor([row] if row else [])
        if compact.startswith("SAVEPOINT ") or compact.startswith("RELEASE SAVEPOINT ") or compact.startswith("ROLLBACK TO SAVEPOINT "):
            return _FakeCursor([])
        if "INSERT INTO background_jobs" in compact:
            row = {
                "id": self.next_id,
                "payload": json.loads(params[1]),
                "status": params[2],
                "job_type": params[0],
                "idempotency_key": params[5],
                "origin_request_id": params[7],
                "created_at": datetime(2026, 3, 25, 14, 37),
            }
            self.next_id += 1
            self.jobs.append(row)
            return _FakeCursor([row])
        raise AssertionError(f"Unexpected query in fake DB: {query}")


class _QueueSnapshotDB:
    def __init__(self, *, queued=0, running=0, succeeded=0, dead_letter=0, stale_running=0, oldest_queued_minutes=None):
        self.values = {
            "queued": queued,
            "running": running,
            "succeeded": succeeded,
            "dead_letter": dead_letter,
            "stale_running": stale_running,
            "oldest_queued_minutes": oldest_queued_minutes,
        }

    def execute(self, query, params=()):
        compact = " ".join(query.split()).lower()
        if "where status = %s" in compact and "count(*)" in compact and "locked_at" not in compact:
            status = params[0]
            key = {
                "queued": "queued",
                "running": "running",
                "succeeded": "succeeded",
                "dead_letter": "dead_letter",
            }[status]
            return _FakeCursor([{"total": self.values[key]}])
        if "locked_at" in compact and "count(*)" in compact:
            return _FakeCursor([{"total": self.values["stale_running"]}])
        if "extract(epoch from (current_timestamp - min(scheduled_for))) / 60.0 as minutes" in compact:
            return _FakeCursor([{"minutes": self.values["oldest_queued_minutes"]}])
        raise AssertionError(f"Unexpected snapshot query: {query}")


class _RequeueDB:
    def __init__(self, should_update=True):
        self.should_update = should_update

    def execute(self, query, params=()):
        compact = " ".join(query.split()).lower()
        if "update background_jobs" in compact and "returning id" in compact:
            if self.should_update:
                return _FakeCursor([{"id": params[1]}])
            return _FakeCursor([])
        raise AssertionError(f"Unexpected requeue query: {query}")


class _CleanupDB:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()), params))
        return _FakeCursor([])


class _FailureDB:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=()):
        self.calls.append((" ".join(query.split()), params))
        return _FakeCursor([])


def test_enqueue_background_job_uses_idempotency_key_to_prevent_duplicates():
    db = _FakeDB()

    first = enqueue_background_job(
        db,
        job_type="send_daily_notifications",
        payload={"source": "manual"},
        idempotency_key="manual:20260325",
    )
    second = enqueue_background_job(
        db,
        job_type="send_daily_notifications",
        payload={"source": "manual"},
        idempotency_key="manual:20260325",
    )

    assert first.created is True
    assert second.created is False
    assert first.job_id == second.job_id
    assert len(db.jobs) == 1


def test_enqueue_background_job_preserves_trace_context_in_payload():
    db = _FakeDB()

    enqueue_background_job(
        db,
        job_type="run_backup",
        payload={"source": "manual"},
        idempotency_key="backup:trace",
        request_id="req-job-123",
        correlation_id="corr-job-456",
    )

    assert db.jobs[0]["origin_request_id"] == "req-job-123"
    assert db.jobs[0]["payload"]["_trace"]["correlation_id"] == "corr-job-456"


def test_build_bucketed_idempotency_key_supports_granularity():
    reference = datetime(2026, 3, 25, 14, 37)

    day_key = build_bucketed_idempotency_key("cron-notifications", granularity="day", now=reference)
    hour_key = build_bucketed_idempotency_key("cron-backup", granularity="hour", now=reference)
    minute_key = build_bucketed_idempotency_key("manual-notifications", granularity="minute", now=reference, suffix="42")

    assert day_key == "cron-notifications:20260325"
    assert hour_key == "cron-backup:2026032514"
    assert minute_key == "manual-notifications:202603251437:42"


def test_enqueue_background_job_rejects_when_queue_is_saturated(monkeypatch):
    db = _FakeDB()
    monkeypatch.setenv("JOB_MAX_IN_FLIGHT_PER_TYPE", "1")

    first = enqueue_background_job(
        db,
        job_type="send_daily_notifications",
        payload={"source": "manual"},
        idempotency_key="manual:20260325:1",
    )
    assert first.created is True

    with pytest.raises(RuntimeError, match="Fila de jobs saturada"):
        enqueue_background_job(
            db,
            job_type="send_daily_notifications",
            payload={"source": "manual"},
            idempotency_key="manual:20260325:2",
        )


def test_collect_in_flight_jobs_by_type_summarizes_script_guard_state():
    db = _FakeDB()
    enqueue_background_job(db, job_type="run_backup", payload={"source": "manual"}, idempotency_key="backup:1")
    db.jobs[0]["status"] = "running"
    enqueue_background_job(db, job_type="run_backup", payload={"source": "cron"}, idempotency_key="backup:2")

    snapshot = collect_in_flight_jobs_by_type(db, job_type="run_backup")

    assert snapshot["job_type"] == "run_backup"
    assert snapshot["running"] == 1
    assert snapshot["queued"] == 1
    assert snapshot["total"] == 2
    assert snapshot["oldest_created_at"] == "2026-03-25T14:37:00"


def test_job_worker_deadline_is_configurable(monkeypatch):
    monkeypatch.setenv("JOB_WORKER_JOB_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("JOB_STALE_LOCK_SECONDS", "900")

    assert jobs_module._job_timeout_seconds() == 7
    assert jobs_module._effective_stale_lock_seconds() == 60

    monkeypatch.setenv("JOB_WORKER_JOB_TIMEOUT_SECONDS", "0")

    assert jobs_module._job_timeout_seconds() == 0
    assert jobs_module._effective_stale_lock_seconds() == 900


def test_collect_job_queue_snapshot_returns_consistent_counts():
    db = _QueueSnapshotDB(queued=7, running=2, succeeded=11, dead_letter=1, stale_running=1, oldest_queued_minutes=14.5)

    snapshot = collect_job_queue_snapshot(db, stale_lock_seconds=120)

    assert snapshot["queued"] == 7
    assert snapshot["running"] == 2
    assert snapshot["succeeded"] == 11
    assert snapshot["dead_letter"] == 1
    assert snapshot["stale_running"] == 1
    assert snapshot["oldest_queued_minutes"] == 14.5


def test_mark_job_as_failure_clears_idempotency_for_dead_letter():
    db = _FailureDB()
    job_row = {"id": 901, "max_attempts": 2}

    status = jobs_module._mark_job_as_failure(db, job_row=job_row, attempt=2, error="boom")

    assert status == jobs_module.JOB_STATUS_DEAD_LETTER
    assert db.calls
    executed_sql = db.calls[0][0]
    assert "idempotency_key = NULL" in executed_sql


def test_set_sentry_request_tag_tolerates_missing_sdk(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)
    jobs_module._set_sentry_request_tag("req-123")


def test_set_sentry_request_tag_sets_tag_when_sdk_available(monkeypatch):
    captured = {}

    def _set_tag(key, value):
        captured["key"] = key
        captured["value"] = value

    fake_sdk = types.SimpleNamespace(set_tag=_set_tag)
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake_sdk)

    jobs_module._set_sentry_request_tag("req-456")

    assert captured == {"key": "request_id", "value": "req-456"}


def test_requeue_dead_letter_job_only_returns_true_when_job_updated():
    updated = requeue_dead_letter_job(_RequeueDB(should_update=True), job_id=101)
    not_updated = requeue_dead_letter_job(_RequeueDB(should_update=False), job_id=102)

    assert updated is True
    assert not_updated is False


def test_cleanup_old_job_history_respects_flag(monkeypatch):
    db = _CleanupDB()
    monkeypatch.setenv("JOB_AUTO_CLEANUP_ENABLED", "0")

    jobs_module._cleanup_old_job_history(db)

    assert db.calls == []


def test_cleanup_old_job_history_executes_retention_queries(monkeypatch):
    db = _CleanupDB()
    monkeypatch.setenv("JOB_AUTO_CLEANUP_ENABLED", "1")
    monkeypatch.setenv("JOB_SUCCESS_RETENTION_DAYS", "10")
    monkeypatch.setenv("JOB_FAILED_RETENTION_DAYS", "20")
    monkeypatch.setenv("JOB_EXECUTION_RETENTION_DAYS", "30")

    jobs_module._cleanup_old_job_history(db)

    assert len(db.calls) == 3
    assert "DELETE FROM background_job_executions" in db.calls[0][0]
    assert "DELETE FROM background_jobs" in db.calls[1][0]
    assert "DELETE FROM background_jobs" in db.calls[2][0]
