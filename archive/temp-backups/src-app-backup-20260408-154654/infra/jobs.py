from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

try:
    import psycopg2
except ImportError:
    psycopg2 = None  # type: ignore[assignment]
from flask import current_app

from ..core.utils import env_int as _env_int
from ..db import get_db

JOB_TYPE_SEND_DAILY_NOTIFICATIONS = "send_daily_notifications"
JOB_TYPE_RUN_BACKUP = "run_backup"

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_SUCCEEDED = "succeeded"
JOB_STATUS_DEAD_LETTER = "dead_letter"


@dataclass(frozen=True)
class JobEnqueueResult:
    job_id: int
    status: str
    created: bool
    job_type: str
    idempotency_key: str | None


@dataclass(frozen=True)
class JobProcessResult:
    job_id: int
    processed: bool
    success: bool
    status: str
    error: str | None = None
    details: dict[str, Any] | None = None





def _safe_json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)


def _count_in_flight_jobs_by_type(db, *, job_type: str) -> int:
    row = db.execute(
        """
        SELECT COUNT(*) AS total
        FROM background_jobs
        WHERE job_type = %s
          AND status IN (%s, %s)
        """,
        (job_type, JOB_STATUS_QUEUED, JOB_STATUS_RUNNING),
    ).fetchone()
    if row is None:
        return 0
    if hasattr(row, "keys"):
        return int(row.get("total", 0) or 0)
    return int(row[0] or 0)


def _job_relevant_for_dedup(status: str | None) -> bool:
    return status in {JOB_STATUS_QUEUED, JOB_STATUS_RUNNING, JOB_STATUS_SUCCEEDED}


def build_bucketed_idempotency_key(
    prefix: str,
    *,
    granularity: str = "minute",
    now: datetime | None = None,
    suffix: str | None = None,
) -> str:
    reference = now or datetime.utcnow()
    key_granularity = (granularity or "").strip().lower()
    if key_granularity == "day":
        stamp = reference.strftime("%Y%m%d")
    elif key_granularity == "hour":
        stamp = reference.strftime("%Y%m%d%H")
    else:
        stamp = reference.strftime("%Y%m%d%H%M")
    parts = [prefix.strip() or "job", stamp]
    if suffix:
        parts.append((suffix or "").strip())
    return ":".join(parts)


def enqueue_background_job(
    db,
    *,
    job_type: str,
    payload: dict[str, Any] | None = None,
    priority: int = 100,
    max_attempts: int = 3,
    idempotency_key: str | None = None,
    requested_by: int | None = None,
    request_id: str | None = None,
) -> JobEnqueueResult:
    safe_job_type = (job_type or "").strip()
    if not safe_job_type:
        raise ValueError("job_type é obrigatório para enfileirar tarefa.")

    safe_idempotency_key = (idempotency_key or "").strip() or None
    safe_payload = payload or {}
    safe_priority = max(1, int(priority))
    safe_max_attempts = max(1, int(max_attempts))
    max_in_flight_per_type = _env_int("JOB_MAX_IN_FLIGHT_PER_TYPE", 0, minimum=0)

    if max_in_flight_per_type > 0:
        in_flight = _count_in_flight_jobs_by_type(db, job_type=safe_job_type)
        if in_flight >= max_in_flight_per_type:
            raise RuntimeError(
                "Fila de jobs saturada para este tipo. "
                f"job_type={safe_job_type} in_flight={in_flight} limit={max_in_flight_per_type}"
            )

    if safe_idempotency_key:
        existing = db.execute(
            """
            SELECT id, status, job_type, idempotency_key
            FROM background_jobs
            WHERE idempotency_key = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (safe_idempotency_key,),
        ).fetchone()
        if existing and _job_relevant_for_dedup(existing["status"]):
            return JobEnqueueResult(
                job_id=int(existing["id"]),
                status=existing["status"],
                created=False,
                job_type=existing["job_type"],
                idempotency_key=existing["idempotency_key"],
            )

    db.execute("SAVEPOINT enqueue_background_job_sp")
    try:
        row = db.execute(
            """
            INSERT INTO background_jobs
            (job_type, payload, status, priority, max_attempts, idempotency_key, requested_by, origin_request_id)
            VALUES (%s, %s::jsonb, %s, %s, %s, %s, %s, %s)
            RETURNING id, status, job_type, idempotency_key
            """,
            (
                safe_job_type,
                _safe_json(safe_payload),
                JOB_STATUS_QUEUED,
                safe_priority,
                safe_max_attempts,
                safe_idempotency_key,
                requested_by,
                request_id,
            ),
        ).fetchone()
        db.execute("RELEASE SAVEPOINT enqueue_background_job_sp")
        return JobEnqueueResult(
            job_id=int(row["id"]),
            status=row["status"],
            created=True,
            job_type=row["job_type"],
            idempotency_key=row["idempotency_key"],
        )
    except psycopg2.IntegrityError:
        db.execute("ROLLBACK TO SAVEPOINT enqueue_background_job_sp")
        if not safe_idempotency_key:
            raise
        existing = db.execute(
            """
            SELECT id, status, job_type, idempotency_key
            FROM background_jobs
            WHERE idempotency_key = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (safe_idempotency_key,),
        ).fetchone()
        if not existing:
            raise
        return JobEnqueueResult(
            job_id=int(existing["id"]),
            status=existing["status"],
            created=False,
            job_type=existing["job_type"],
            idempotency_key=existing["idempotency_key"],
        )


def enqueue_notifications_job(
    db,
    *,
    source: str,
    requested_by: int | None = None,
    idempotency_key: str | None = None,
    request_id: str | None = None,
) -> JobEnqueueResult:
    return enqueue_background_job(
        db,
        job_type=JOB_TYPE_SEND_DAILY_NOTIFICATIONS,
        payload={"source": (source or "").strip() or "manual"},
        priority=40,
        max_attempts=3,
        idempotency_key=idempotency_key,
        requested_by=requested_by,
        request_id=request_id,
    )


def enqueue_backup_job(
    db,
    *,
    source: str,
    backup_type: str = "agendado",
    requested_by: int | None = None,
    idempotency_key: str | None = None,
    request_id: str | None = None,
) -> JobEnqueueResult:
    return enqueue_background_job(
        db,
        job_type=JOB_TYPE_RUN_BACKUP,
        payload={
            "source": (source or "").strip() or "manual",
            "backup_type": (backup_type or "").strip() or "agendado",
        },
        priority=30,
        max_attempts=2,
        idempotency_key=idempotency_key,
        requested_by=requested_by,
        request_id=request_id,
    )


def _requeue_stale_running_jobs(db, *, stale_lock_seconds: int) -> None:
    if stale_lock_seconds <= 0:
        return
    db.execute(
        """
        UPDATE background_jobs
        SET
            status = %s,
            locked_by = NULL,
            locked_at = NULL,
            updated_at = CURRENT_TIMESTAMP,
            last_error = COALESCE(last_error, '') || CASE
                WHEN COALESCE(last_error, '') = '' THEN 'Reenfileirado por lock expirado.'
                ELSE ' | Reenfileirado por lock expirado.'
            END
        WHERE status = %s
          AND locked_at IS NOT NULL
          AND locked_at < (CURRENT_TIMESTAMP - (%s * INTERVAL '1 second'))
        """,
        (JOB_STATUS_QUEUED, JOB_STATUS_RUNNING, stale_lock_seconds),
    )


def _claim_next_job(db, *, worker_id: str):
    return db.execute(
        """
        WITH candidate AS (
            SELECT id
            FROM background_jobs
            WHERE status = %s
              AND scheduled_for <= CURRENT_TIMESTAMP
            ORDER BY priority ASC, scheduled_for ASC, id ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        UPDATE background_jobs j
        SET
            status = %s,
            locked_by = %s,
            locked_at = CURRENT_TIMESTAMP,
            started_at = COALESCE(j.started_at, CURRENT_TIMESTAMP),
            updated_at = CURRENT_TIMESTAMP
        FROM candidate
        WHERE j.id = candidate.id
        RETURNING j.*
        """,
        (JOB_STATUS_QUEUED, JOB_STATUS_RUNNING, worker_id),
    ).fetchone()


def _claim_job_by_id(db, *, job_id: int, worker_id: str):
    return db.execute(
        """
        UPDATE background_jobs
        SET
            status = %s,
            locked_by = %s,
            locked_at = CURRENT_TIMESTAMP,
            started_at = COALESCE(started_at, CURRENT_TIMESTAMP),
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
          AND status = %s
          AND scheduled_for <= CURRENT_TIMESTAMP
        RETURNING *
        """,
        (JOB_STATUS_RUNNING, worker_id, job_id, JOB_STATUS_QUEUED),
    ).fetchone()


def _create_execution_log(db, *, job_id: int, attempt: int, worker_id: str):
    row = db.execute(
        """
        INSERT INTO background_job_executions
        (job_id, attempt, status, worker_id)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (job_id, attempt, JOB_STATUS_RUNNING, worker_id),
    ).fetchone()
    return int(row["id"])


def _finalize_execution_log(
    db,
    *,
    execution_id: int,
    status: str,
    duration_ms: int,
    error: str | None = None,
    result_payload: dict[str, Any] | None = None,
):
    db.execute(
        """
        UPDATE background_job_executions
        SET
            status = %s,
            finished_at = CURRENT_TIMESTAMP,
            duration_ms = %s,
            error = %s,
            result_payload = %s::jsonb
        WHERE id = %s
        """,
        (
            status,
            max(0, int(duration_ms)),
            (error or "").strip()[:1000] or None,
            _safe_json(result_payload or {}),
            execution_id,
        ),
    )


def _run_handler(app, job_row) -> tuple[bool, dict[str, Any]]:
    from .backup import run_backup_job
    from .mailer import send_daily_notifications

    payload = job_row["payload"] if isinstance(job_row["payload"], dict) else {}
    job_type = job_row["job_type"]

    if job_type == JOB_TYPE_SEND_DAILY_NOTIFICATIONS:
        result = send_daily_notifications(app)
        success = bool(result.sent or result.reason in {"no_due_items", "no_recipients"})
        details = {
            "sent": bool(result.sent),
            "reason": result.reason,
            "error": result.error,
        }
        return success, details

    if job_type == JOB_TYPE_RUN_BACKUP:
        backup_type = (payload.get("backup_type") or "agendado").strip()
        result = run_backup_job(backup_type=backup_type)
        details = {
            "success": bool(result.success),
            "status": result.status,
            "message": result.message,
            "file_path": result.file_path,
            "duration_ms": result.duration_ms,
        }
        return bool(result.success), details

    raise RuntimeError(f"Tipo de job não suportado: {job_type}")


def _retry_delay_seconds(attempt: int) -> int:
    # Backoff exponencial curto para evitar loop agressivo em falha persistente.
    return min(900, max(10, (2 ** max(0, attempt - 1)) * 15))


def _mark_job_as_success(db, *, job_id: int, attempt: int):
    db.execute(
        """
        UPDATE background_jobs
        SET
            status = %s,
            attempts = %s,
            locked_by = NULL,
            locked_at = NULL,
            last_error = NULL,
            finished_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (JOB_STATUS_SUCCEEDED, attempt, job_id),
    )


def _mark_job_as_failure(db, *, job_row, attempt: int, error: str):
    max_attempts = max(1, int(job_row["max_attempts"] or 1))
    normalized_error = (error or "Falha sem detalhe.").strip()[:1000]
    if attempt >= max_attempts:
        db.execute(
            """
            UPDATE background_jobs
            SET
                status = %s,
                attempts = %s,
                locked_by = NULL,
                locked_at = NULL,
                idempotency_key = NULL,
                last_error = %s,
                finished_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (JOB_STATUS_DEAD_LETTER, attempt, normalized_error, int(job_row["id"])),
        )
        return JOB_STATUS_DEAD_LETTER

    delay_seconds = _retry_delay_seconds(attempt)
    db.execute(
        """
        UPDATE background_jobs
        SET
            status = %s,
            attempts = %s,
            locked_by = NULL,
            locked_at = NULL,
            scheduled_for = CURRENT_TIMESTAMP + (%s * INTERVAL '1 second'),
            last_error = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (JOB_STATUS_QUEUED, attempt, delay_seconds, normalized_error, int(job_row["id"])),
    )
    return JOB_STATUS_QUEUED


def _set_sentry_request_tag(request_id: str | None) -> None:
    if not request_id:
        return
    try:
        import sentry_sdk  # type: ignore
    except Exception:
        return
    try:
        set_tag = getattr(sentry_sdk, "set_tag", None)
        if callable(set_tag):
            set_tag("request_id", request_id)
    except Exception:
        # Observabilidade não deve derrubar processamento assíncrono.
        return


def _process_claimed_job(app, db, *, claimed_job, worker_id: str) -> JobProcessResult:
    origin_request_id = claimed_job.get("origin_request_id")
    _set_sentry_request_tag(origin_request_id)

    app.logger.info(
        "Initiating processing of background job.",
        extra={
            "job_id": int(claimed_job["id"]),
            "job_type": claimed_job["job_type"],
            "origin_request_id": origin_request_id,
        }
    )

    attempt = int(claimed_job["attempts"] or 0) + 1
    execution_id = _create_execution_log(
        db,
        job_id=int(claimed_job["id"]),
        attempt=attempt,
        worker_id=worker_id,
    )
    db.commit()

    started = time.monotonic()
    try:
        success, details = _run_handler(app, claimed_job)
        duration_ms = int((time.monotonic() - started) * 1000)
        if success:
            _mark_job_as_success(db, job_id=int(claimed_job["id"]), attempt=attempt)
            _finalize_execution_log(
                db,
                execution_id=execution_id,
                status=JOB_STATUS_SUCCEEDED,
                duration_ms=duration_ms,
                result_payload=details,
            )
            db.commit()
            return JobProcessResult(
                job_id=int(claimed_job["id"]),
                processed=True,
                success=True,
                status=JOB_STATUS_SUCCEEDED,
                details=details,
            )

        failure_reason = (details or {}).get("error") or (details or {}).get("reason") or "job_failed"
        job_status = _mark_job_as_failure(
            db,
            job_row=claimed_job,
            attempt=attempt,
            error=failure_reason,
        )
        _finalize_execution_log(
            db,
            execution_id=execution_id,
            status="failed",
            duration_ms=duration_ms,
            error=failure_reason,
            result_payload=details,
        )
        db.commit()
        return JobProcessResult(
            job_id=int(claimed_job["id"]),
            processed=True,
            success=False,
            status=job_status,
            error=str(failure_reason),
            details=details,
        )
    except Exception as exc:
        db.conn.rollback()
        duration_ms = int((time.monotonic() - started) * 1000)
        error_text = str(exc)[:1000] or "unexpected_error"
        try:
            job_status = _mark_job_as_failure(
                db,
                job_row=claimed_job,
                attempt=attempt,
                error=error_text,
            )
            _finalize_execution_log(
                db,
                execution_id=execution_id,
                status="failed",
                duration_ms=duration_ms,
                error=error_text,
                result_payload={"error": error_text},
            )
            db.commit()
        except Exception:
            db.conn.rollback()
            job_status = JOB_STATUS_RUNNING
        current_app.logger.exception(
            "Falha inesperada no processamento de background job.",
            extra={
                "job_id": int(claimed_job["id"]),
                "job_type": claimed_job["job_type"],
                "origin_request_id": claimed_job.get("origin_request_id"),
            },
        )
        return JobProcessResult(
            job_id=int(claimed_job["id"]),
            processed=True,
            success=False,
            status=job_status,
            error=error_text,
            details={"error": error_text},
        )


def process_background_job_by_id(
    app,
    job_id: int,
    *,
    worker_id: str | None = None,
) -> JobProcessResult:
    with app.app_context():
        db = get_db()
        stale_lock_seconds = _env_int("JOB_STALE_LOCK_SECONDS", 14400, minimum=60)
        _requeue_stale_running_jobs(db, stale_lock_seconds=stale_lock_seconds)
        claimed_job = _claim_job_by_id(
            db,
            job_id=int(job_id),
            worker_id=(worker_id or f"worker:{os.getpid()}"),
        )
        db.commit()
        if not claimed_job:
            row = db.execute(
                "SELECT id, status FROM background_jobs WHERE id = %s",
                (int(job_id),),
            ).fetchone()
            status = row["status"] if row else "missing"
            return JobProcessResult(
                job_id=int(job_id),
                processed=False,
                success=status == JOB_STATUS_SUCCEEDED,
                status=status,
            )
        return _process_claimed_job(
            app,
            db,
            claimed_job=claimed_job,
            worker_id=(worker_id or f"worker:{os.getpid()}"),
        )


def process_background_jobs(
    app,
    *,
    max_jobs: int = 5,
    worker_id: str | None = None,
) -> dict[str, int]:
    summary = {"processed": 0, "succeeded": 0, "failed": 0, "dead_letter": 0}
    with app.app_context():
        db = get_db()
        stale_lock_seconds = _env_int("JOB_STALE_LOCK_SECONDS", 14400, minimum=60)
        _requeue_stale_running_jobs(db, stale_lock_seconds=stale_lock_seconds)
        db.commit()

        effective_worker = worker_id or f"worker:{os.getpid()}"
        for _ in range(max(1, int(max_jobs))):
            claimed_job = _claim_next_job(db, worker_id=effective_worker)
            db.commit()
            if not claimed_job:
                break
            result = _process_claimed_job(app, db, claimed_job=claimed_job, worker_id=effective_worker)
            summary["processed"] += 1
            if result.success:
                summary["succeeded"] += 1
            else:
                summary["failed"] += 1
                if result.status == JOB_STATUS_DEAD_LETTER:
                    summary["dead_letter"] += 1
        _cleanup_old_job_history(db)
        db.commit()
    return summary


def collect_job_queue_snapshot(
    db,
    *,
    stale_lock_seconds: int | None = None,
) -> dict[str, int | float | None]:
    stale_seconds = max(60, int(stale_lock_seconds or _env_int("JOB_STALE_LOCK_SECONDS", 14400, minimum=60)))
    queued, _ = _safe_int_scalar(db, "SELECT COUNT(*) AS total FROM background_jobs WHERE status = %s", (JOB_STATUS_QUEUED,))
    running, _ = _safe_int_scalar(db, "SELECT COUNT(*) AS total FROM background_jobs WHERE status = %s", (JOB_STATUS_RUNNING,))
    succeeded, _ = _safe_int_scalar(db, "SELECT COUNT(*) AS total FROM background_jobs WHERE status = %s", (JOB_STATUS_SUCCEEDED,))
    dead_letter, _ = _safe_int_scalar(db, "SELECT COUNT(*) AS total FROM background_jobs WHERE status = %s", (JOB_STATUS_DEAD_LETTER,))
    stale_running, _ = _safe_int_scalar(
        db,
        """
        SELECT COUNT(*) AS total
        FROM background_jobs
        WHERE status = %s
          AND locked_at IS NOT NULL
          AND locked_at < (CURRENT_TIMESTAMP - (%s * INTERVAL '1 second'))
        """,
        (JOB_STATUS_RUNNING, stale_seconds),
    )
    oldest_queued_minutes, _ = _safe_float_scalar(
        db,
        """
        SELECT EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - MIN(scheduled_for))) / 60.0 AS minutes
        FROM background_jobs
        WHERE status = %s
        """,
        (JOB_STATUS_QUEUED,),
    )
    return {
        "queued": int(queued or 0),
        "running": int(running or 0),
        "succeeded": int(succeeded or 0),
        "dead_letter": int(dead_letter or 0),
        "stale_running": int(stale_running or 0),
        "oldest_queued_minutes": float(oldest_queued_minutes) if oldest_queued_minutes is not None else None,
    }


def requeue_dead_letter_job(db, *, job_id: int) -> bool:
    row = db.execute(
        """
        UPDATE background_jobs
        SET
            status = %s,
            scheduled_for = CURRENT_TIMESTAMP,
            locked_by = NULL,
            locked_at = NULL,
            attempts = 0,
            finished_at = NULL,
            updated_at = CURRENT_TIMESTAMP,
            last_error = COALESCE(last_error, '') || CASE
                WHEN COALESCE(last_error, '') = '' THEN 'Reprocessamento manual solicitado.'
                ELSE ' | Reprocessamento manual solicitado.'
            END
        WHERE id = %s
          AND status = %s
        RETURNING id
        """,
        (JOB_STATUS_QUEUED, int(job_id), JOB_STATUS_DEAD_LETTER),
    ).fetchone()
    return bool(row)


def _safe_int_scalar(db, query: str, params: tuple = ()) -> tuple[int | None, str | None]:
    try:
        row = db.execute(query, params).fetchone()
        if row is None:
            return 0, None
        value = row[0] if not hasattr(row, "keys") else row[next(iter(row.keys()))]
        return int(value or 0), None
    except Exception as exc:
        return None, str(exc)


def _safe_float_scalar(db, query: str, params: tuple = ()) -> tuple[float | None, str | None]:
    try:
        row = db.execute(query, params).fetchone()
        if row is None:
            return None, None
        value = row[0] if not hasattr(row, "keys") else row[next(iter(row.keys()))]
        return (None if value is None else float(value)), None
    except Exception as exc:
        return None, str(exc)


def _cleanup_old_job_history(db) -> None:
    enabled = (os.getenv("JOB_AUTO_CLEANUP_ENABLED", "1") or "").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return

    succeeded_retention_days = max(1, _env_int("JOB_SUCCESS_RETENTION_DAYS", 30, minimum=1))
    failed_retention_days = max(1, _env_int("JOB_FAILED_RETENTION_DAYS", 90, minimum=1))
    execution_retention_days = max(1, _env_int("JOB_EXECUTION_RETENTION_DAYS", 30, minimum=1))

    db.execute(
        """
        DELETE FROM background_job_executions
        WHERE started_at < (CURRENT_TIMESTAMP - (%s * INTERVAL '1 day'))
        """,
        (execution_retention_days,),
    )
    db.execute(
        """
        DELETE FROM background_jobs
        WHERE status = %s
          AND finished_at IS NOT NULL
          AND finished_at < (CURRENT_TIMESTAMP - (%s * INTERVAL '1 day'))
        """,
        (JOB_STATUS_SUCCEEDED, succeeded_retention_days),
    )
    db.execute(
        """
        DELETE FROM background_jobs
        WHERE status = %s
          AND finished_at IS NOT NULL
          AND finished_at < (CURRENT_TIMESTAMP - (%s * INTERVAL '1 day'))
        """,
        (JOB_STATUS_DEAD_LETTER, failed_retention_days),
    )
